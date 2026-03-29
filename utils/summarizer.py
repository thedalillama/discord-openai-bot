# utils/summarizer.py
# Version 2.2.0
"""
Summarization pipeline orchestrator. Both cold starts and incremental
updates use the three-pass Secretary → Structurer → Classifier pipeline
via summarizer_authoring.py.

CHANGES v2.2.0: Batched cold start
- MODIFIED: summarize_channel() now slices cold start to effective_batch
  before calling cold_start_pipeline(); remaining messages continue through
  _incremental_loop(); prevents 65K+ Structurer responses on large initial
  ingest

CHANGES v2.1.0: Incremental path uses three-pass pipeline
- MODIFIED: _incremental_loop() batches messages and delegates each
  batch to incremental_pipeline() instead of single-pass raw-to-JSON
- REMOVED: Direct Gemini calls from incremental path

CHANGES v2.0.0: Migrate incremental path to anyOf schema
CHANGES v1.9.0: Two-pass authoring for cold starts
CHANGES v1.1.0-v1.8.0: Three-layer pipeline, batch loop, noise filters
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import asyncio
import json
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer')


async def summarize_channel(channel_id, batch_size=None):
    """Generate or update the structured summary for a channel."""
    from utils.summary_store import get_channel_summary
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_BATCH_SIZE
    effective_batch = batch_size or SUMMARIZER_BATCH_SIZE
    provider = get_provider(SUMMARIZER_PROVIDER)
    summary_json, last_message_id = await asyncio.to_thread(
        get_channel_summary, channel_id)
    if not summary_json:
        logger.info(f"Cold start for channel {channel_id}")
        from utils.summarizer_authoring import cold_start_pipeline
        from config import SUMMARIZER_MODEL
        all_messages = await _get_unsummarized_messages(
            channel_id, None)
        first_batch = all_messages[:effective_batch]
        logger.info(
            f"Cold start: {len(first_batch)} of {len(all_messages)} msgs "
            f"(batch_size={effective_batch})")
        result = await cold_start_pipeline(
            channel_id, provider, effective_batch,
            SUMMARIZER_PROVIDER, SUMMARIZER_MODEL, first_batch)
        if result.get("error") or len(all_messages) <= effective_batch:
            return result
        remaining = len(all_messages) - len(first_batch)
        logger.info(
            f"Cold start complete. {remaining} msgs remaining "
            f"— continuing incrementally.")
        sj, lmid = await asyncio.to_thread(get_channel_summary, channel_id)
        current = json.loads(sj)
        inc = await _incremental_loop(
            channel_id, provider, effective_batch, current, lmid)
        return _partial(
            result.get("messages_processed", 0) + inc.get("messages_processed", 0),
            inc.get("token_count", 0),
            inc.get("verification", {}),
            inc.get("error"))
    try:
        current = json.loads(summary_json)
    except Exception as e:
        logger.error(f"Failed to parse stored summary: {e}")
        return _partial(0, 0, {}, str(e))
    return await _incremental_loop(
        channel_id, provider, effective_batch,
        current, last_message_id)


async def _incremental_loop(channel_id, provider, batch_size,
                              current, last_message_id):
    """Batch messages and delegate each batch to the pipeline."""
    from utils.summary_store import get_channel_summary
    from utils.summarizer_authoring import incremental_pipeline
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL
    total = 0; last_tc = 0; last_vf = {}; bn = 0
    while True:
        sj, lmid = await asyncio.to_thread(
            get_channel_summary, channel_id)
        if sj:
            try: current = json.loads(sj)
            except Exception:
                return _partial(total, last_tc, last_vf, "Parse error")
            last_message_id = lmid
        msgs = await _get_unsummarized_messages(
            channel_id, last_message_id)
        msgs = msgs[:batch_size]
        if not msgs: break
        bn += 1
        logger.info(f"Incremental batch {bn}: {len(msgs)} msgs")
        result = await incremental_pipeline(
            channel_id, provider,
            SUMMARIZER_PROVIDER, SUMMARIZER_MODEL,
            msgs, current)
        total += result.get("messages_processed", 0)
        last_tc = result.get("token_count", 0)
        last_vf = result.get("verification", {})
        if result.get("error"):
            return _partial(total, last_tc, last_vf,
                            result["error"])
        logger.info(f"Batch {bn}: {len(msgs)} msgs, "
                    f"{last_tc} tokens")
    return _partial(total, last_tc, last_vf, None)


async def _process_response(response_text, pre_state, context_labels,
                              channel_id, provider, prompt_messages,
                              delta_schema, batch_num=0):
    """Parse, classify, normalize, validate. One repair retry."""
    from utils.summary_normalization import (
        parse_json_response, classify_response,
        canonicalize_full_summary, diff_full_to_ops)
    from utils.summary_validation import validate_domain
    errors = []
    for attempt in range(2):
        parsed = parse_json_response(response_text)
        if parsed is None:
            errors.append("Not valid JSON")
            if attempt == 0:
                response_text = await _repair_call(
                    provider, prompt_messages, errors,
                    delta_schema, channel_id)
                continue
            return None, "; ".join(errors)
        kind = classify_response(parsed)
        logger.debug(f"Batch {batch_num} — classified: {kind}")
        if kind == "delta":
            delta = parsed
        elif kind == "full":
            logger.info("Full summary — normalizing to delta")
            ops = diff_full_to_ops(
                pre_state, canonicalize_full_summary(parsed))
            delta = {"schema_version": "delta.v1",
                     "mode": "incremental", "ops": ops}
        else:
            errors.append("Unknown response shape")
            if attempt == 0:
                response_text = await _repair_call(
                    provider, prompt_messages, errors,
                    delta_schema, channel_id)
                continue
            return None, "; ".join(errors)
        before = len(delta.get("ops", []))
        delta["ops"] = validate_domain(
            delta, pre_state, context_labels)
        after = len(delta["ops"])
        logger.debug(f"Batch {batch_num} — {before}→{after} ops")
        return delta, None
    return None, "; ".join(errors)


async def _repair_call(provider, original_messages, errors,
                        delta_schema, channel_id):
    """One repair retry with validation errors appended."""
    repair = ("Your previous output failed validation.\n\n"
              "VALIDATION_ERRORS:\n" +
              "\n".join(f"- {e}" for e in errors) +
              "\n\nReturn ONLY corrected JSON. No other text.")
    try:
        return await provider.generate_ai_response(
            original_messages + [
                {"role": "user", "content": repair}],
            temperature=0, response_mime_type="application/json",
            response_json_schema=delta_schema, use_json_schema=True)
    except Exception as e:
        logger.error(f"Repair call failed: {e}")
        return ""


async def _get_unsummarized_messages(channel_id, last_message_id):
    """Return unsummarized messages, excluding noise."""
    from utils.message_store import get_channel_messages
    from utils.history.message_processing import (
        is_history_output, is_settings_persistence_message,
        is_summary_output)
    all_msgs = await asyncio.to_thread(
        get_channel_messages, channel_id)
    if last_message_id is not None:
        all_msgs = [m for m in all_msgs if m.id > last_message_id]
    return [
        m for m in all_msgs if m.content
        and not m.content.startswith('!')
        and not is_history_output(m.content)
        and not is_settings_persistence_message(m.content)
        and not is_summary_output(m.content)
        and "System prompt updated for" not in m.content]


def _partial(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}
