# utils/summarizer.py
# Version 3.0.0
"""
Summarization pipeline orchestrator.

CHANGES v3.0.0: Route to cluster-based pipeline (SOW v5.3.0)
- MODIFIED: summarize_channel() now delegates to run_cluster_pipeline()
  in cluster_overview.py; executes cluster → per-cluster summarize →
  cross-cluster overview → save to channel_summaries
- RETAINED: v4.x three-pass pipeline functions (_incremental_loop,
  _process_response, _repair_call, _get_unsummarized_messages) are NOT
  called but remain for rollback safety

CHANGES v2.2.0: Batched cold start
- MODIFIED: summarize_channel() now slices cold start to effective_batch
  before calling cold_start_pipeline(); remaining messages continue through
  _incremental_loop(); prevents 65K+ Structurer responses on large initial
  ingest

CHANGES v2.1.0: Incremental path uses three-pass pipeline
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
    """Generate or update the structured summary for a channel.

    v3.0.0: Routes to cluster-based pipeline (cluster_overview.py).
    The v4.x three-pass pipeline functions below are no longer called
    but are retained for rollback safety.

    batch_size is accepted but ignored — the cluster pipeline processes
    all messages on each run.
    """
    from utils.cluster_overview import run_cluster_pipeline
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    provider = get_provider(SUMMARIZER_PROVIDER)
    try:
        return await run_cluster_pipeline(channel_id, provider)
    except Exception as e:
        logger.error(f"Cluster pipeline failed ch:{channel_id}: {e}")
        return {"error": str(e), "messages_processed": 0,
                "cluster_count": 0, "noise_count": 0,
                "overview_generated": False}


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
