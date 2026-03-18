# utils/summarizer.py
# Version 1.9.0
"""
Summarization pipeline orchestrator. Cold starts use two-pass Secretary →
Structurer via summarizer_authoring.py. Incremental updates use single-pass
delta ops with Gemini Structured Outputs + Layer 2/3 enforcement.

CHANGES v1.9.0: Two-pass authoring for cold starts; readable text in snapshots
CHANGES v1.6.0-v1.8.0: Bot [BOT] labels, summary output filter, DEBUG tracing
CHANGES v1.1.0-v1.5.0: Three-layer pipeline, batch loop, noise filters
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import asyncio
import json
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer')


async def summarize_channel(channel_id, batch_size=None):
    """Generate or update the structured summary for a channel."""
    from utils.summary_store import get_channel_summary
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_BATCH_SIZE

    effective_batch = batch_size if batch_size is not None else SUMMARIZER_BATCH_SIZE
    provider = get_provider(SUMMARIZER_PROVIDER)

    summary_json, last_message_id = await asyncio.to_thread(
        get_channel_summary, channel_id
    )

    if not summary_json:
        logger.info(f"Cold start for channel {channel_id}")
        from utils.summarizer_authoring import cold_start_pipeline
        from config import SUMMARIZER_MODEL
        all_messages = await _get_unsummarized_messages(channel_id, None)
        return await cold_start_pipeline(
            channel_id, provider, effective_batch,
            SUMMARIZER_PROVIDER, SUMMARIZER_MODEL, all_messages,
        )

    try:
        current = json.loads(summary_json)
    except Exception as e:
        logger.error(f"Failed to parse stored summary: {e}")
        return _partial(0, 0, {}, str(e))

    return await _incremental_loop(
        channel_id, provider, effective_batch, current, last_message_id,
    )


async def _incremental_loop(channel_id, provider, batch_size,
                              current, last_message_id):
    """Single-pass delta ops for incremental updates."""
    from utils.summary_store import get_channel_summary, save_channel_summary
    from utils.summary_schema import (
        apply_ops, verify_protected_hashes,
        run_source_verification, DELTA_SCHEMA,
    )
    from utils.summary_prompts import build_label_map, build_prompt
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL

    total = 0
    last_tc = 0
    last_vf = {}
    bn = 0

    while True:
        sj, lmid = await asyncio.to_thread(get_channel_summary, channel_id)
        if sj:
            try:
                current = json.loads(sj)
            except Exception:
                return _partial(total, last_tc, last_vf, "Parse error")
            last_message_id = lmid

        msgs = await _get_unsummarized_messages(channel_id, last_message_id)
        msgs = msgs[:batch_size]
        if not msgs:
            break

        bn += 1
        lid, ltxt = build_label_map(msgs)
        clabels = set(lid.keys())
        pm = build_prompt(current, ltxt)

        logger.debug(f"Batch {bn} — USER:\n{pm[1]['content']}")

        try:
            resp = await provider.generate_ai_response(
                pm, temperature=0,
                response_mime_type="application/json",
                response_json_schema=DELTA_SCHEMA,
            )
        except Exception as e:
            logger.error(f"Provider call failed: {e}")
            return _partial(total, last_tc, last_vf, str(e))

        logger.debug(f"Batch {bn} — RESPONSE:\n{resp}")

        delta, err = await _process_response(
            resp, current, clabels, channel_id, provider, pm, DELTA_SCHEMA,
            batch_num=bn,
        )
        if err:
            return _partial(total, last_tc, last_vf, err)

        _translate_labels_to_ids(delta.get("ops", []), lid)
        updated = apply_ops(current, delta)
        mm, vf = verify_protected_hashes(updated, current)
        mbi = {m.id: m.content for m in msgs}
        sp, sf = run_source_verification(updated, mbi)

        tc = estimate_tokens(json.dumps(updated))
        updated["summary_token_count"] = tc
        last_id = msgs[-1].id
        pc = sum(len(updated.get(k, []))
                 for k in ("decisions", "key_facts", "action_items",
                           "pinned_memory"))
        verification = {
            "protected_items_count": pc, "hashes_verified": vf,
            "mismatches": mm, "source_checks_passed": sp,
            "source_checks_failed": sf,
        }
        updated["meta"].update({
            "model": f"{SUMMARIZER_PROVIDER}/{SUMMARIZER_MODEL}",
            "summarized_at": datetime.now(timezone.utc).isoformat(),
            "token_count": tc,
            "message_range": {"first_id": msgs[0].id, "last_id": last_id,
                              "count": len(msgs)},
            "verification": verification,
        })
        prior = current.get("meta", {}).get("message_range", {}).get("count", 0)
        await asyncio.to_thread(save_channel_summary, channel_id,
                                json.dumps(updated), prior + len(msgs), last_id)

        total += len(msgs)
        last_tc, last_vf = tc, verification
        if tc > 2000:
            logger.warning(f"Summary tokens {tc} > 2000")
        logger.info(f"Batch {bn}: {len(msgs)} msgs, {tc} tokens")

    if total == 0:
        logger.info(f"No new messages for channel {channel_id}")
    else:
        logger.info(f"Incremental done: {total} msgs, {bn} batches")
    return _partial(total, last_tc, last_vf, None)


def _partial(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}


async def _process_response(response_text, pre_state, context_labels,
                             channel_id, provider, prompt_messages,
                             delta_schema, batch_num=0):
    """Layer 2 parse + Layer 3 validate. One repair retry."""
    from utils.summary_normalization import (
        parse_json_response, classify_response,
        canonicalize_full_summary, diff_full_to_ops,
    )
    from utils.summary_validation import validate_domain

    errors = []
    for attempt in range(2):
        parsed = parse_json_response(response_text)
        if parsed is None:
            errors.append("Not valid JSON")
            if attempt == 0:
                response_text = await _repair_call(
                    provider, prompt_messages, errors, delta_schema, channel_id)
                continue
            return None, "; ".join(errors)

        kind = classify_response(parsed)
        logger.debug(f"Batch {batch_num} — classified: {kind}")

        if kind == "delta":
            delta = parsed
        elif kind == "full":
            logger.info("Full summary — normalizing to delta")
            ops = diff_full_to_ops(pre_state,
                                   canonicalize_full_summary(parsed))
            delta = {"schema_version": "delta.v1",
                     "mode": "incremental", "ops": ops}
        else:
            errors.append("Unknown response shape")
            if attempt == 0:
                response_text = await _repair_call(
                    provider, prompt_messages, errors, delta_schema, channel_id)
                continue
            return None, "; ".join(errors)

        before = len(delta.get("ops", []))
        delta["ops"] = validate_domain(delta, pre_state, context_labels)
        after = len(delta["ops"])
        logger.debug(f"Batch {batch_num} — {before}→{after} ops")
        return delta, None

    return None, "; ".join(errors)


async def _repair_call(provider, original_messages, errors,
                        delta_schema, channel_id):
    """One repair retry with validation errors appended."""
    repair = ("Your previous output failed validation.\n\nVALIDATION_ERRORS:\n" +
              "\n".join(f"- {e}" for e in errors) +
              "\n\nReturn ONLY corrected JSON. No other text.")
    try:
        return await provider.generate_ai_response(
            original_messages + [{"role": "user", "content": repair}],
            temperature=0, response_mime_type="application/json",
            response_json_schema=delta_schema,
        )
    except Exception as e:
        logger.error(f"Repair call failed: {e}")
        return ""


async def _get_unsummarized_messages(channel_id, last_message_id):
    """Return unsummarized messages, excluding housekeeping noise."""
    from utils.message_store import get_channel_messages
    from utils.history.message_processing import (
        is_history_output, is_settings_persistence_message, is_summary_output,
    )
    all_msgs = await asyncio.to_thread(get_channel_messages, channel_id)
    if last_message_id is not None:
        all_msgs = [m for m in all_msgs if m.id > last_message_id]
    return [
        m for m in all_msgs if m.content
        and not m.content.startswith('!')
        and not is_history_output(m.content)
        and not is_settings_persistence_message(m.content)
        and not is_summary_output(m.content)
        and "System prompt updated for" not in m.content
    ]


def _translate_labels_to_ids(ops, label_to_id):
    """Replace M-labels with snowflake IDs in source_message_ids."""
    for op in ops:
        if "source_message_ids" in op:
            op["source_message_ids"] = [
                label_to_id.get(mid, mid) for mid in op["source_message_ids"]
            ]
