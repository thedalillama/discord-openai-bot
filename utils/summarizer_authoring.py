# utils/summarizer_authoring.py
# Version 1.9.0
"""
Three-pass authoring pipeline for summarization (cold start + incremental).

Pass 1 (Secretary): Natural language minutes authoring/updating.
Pass 2 (Structurer): Converts minutes to JSON delta ops via anyOf schema.
Pass 3 (Classifier): GPT-5.4 nano validates each op — KEEP/DROP/RECLASSIFY.

CHANGES v1.9.0: Pass existing summary to classifier for dedup
- MODIFIED: classify_ops() receives current_json so it can detect ops
  that duplicate existing items by meaning, even with different IDs

CHANGES v1.8.0: Scale Secretary max_tokens with existing minutes size
- MODIFIED: _secretary_max_tokens() uses existing_tokens + 4*msgs + 1024
  for incremental updates. Prevents truncation when rewriting large minutes.

CHANGES v1.7.0: Unified pipeline for cold start and incremental
- ADDED: incremental_pipeline() entry point for incremental updates
- REFACTORED: _run_pipeline() shared by both cold start and incremental
- Incremental path now uses Secretary → Structurer → Classifier instead
  of single-pass raw-to-JSON

CHANGES v1.6.0: anyOf discriminated union schema (SOW v3.5.0)
CHANGES v1.5.0: Diagnostic file saves
CHANGES v1.4.0: Scaled max_output_tokens
CHANGES v1.3.0: Raw Gemini output file + classifier drops in meta
CHANGES v1.1.0: Classifier pass
CREATED v1.0.0: Extracted from summarizer.py v1.9.0
"""
import asyncio
import json
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer.authoring')


async def cold_start_pipeline(channel_id, provider, batch_size,
                               prov_name, model_name, all_messages):
    """Cold start: all messages, no prior summary."""
    return await _run_pipeline(
        channel_id, provider, prov_name, model_name,
        all_messages, current_minutes=None, current_json=None)


async def incremental_pipeline(channel_id, provider, prov_name,
                                model_name, new_messages, current):
    """Incremental: new messages added to existing summary."""
    current_minutes = current.get("meta", {}).get("minutes_text", "")
    return await _run_pipeline(
        channel_id, provider, prov_name, model_name,
        new_messages, current_minutes=current_minutes,
        current_json=current)


async def _run_pipeline(channel_id, provider, prov_name, model_name,
                         messages, current_minutes, current_json):
    """Shared three-pass pipeline: Secretary → Structurer → Classifier.

    Args:
        current_minutes: Existing minutes text (None for cold start)
        current_json: Existing summary dict (None for cold start)
    """
    from utils.summary_store import save_channel_summary
    from utils.summary_schema import (
        make_empty_summary, apply_ops, verify_protected_hashes)
    from utils.summary_delta_schema import STRUCTURER_SCHEMA, translate_ops
    from utils.summary_prompts import build_label_map
    from utils.summary_prompts_authoring import (
        build_secretary_prompt, build_structurer_prompt)

    if not messages:
        logger.info(f"No messages for channel {channel_id}")
        return _result(0, 0, {}, None)

    # --- Pass 1: Secretary ---
    _, labeled_text = build_label_map(messages)
    max_tokens = _secretary_max_tokens(len(messages), current_minutes)
    logger.info(
        f"Secretary: {len(messages)} msgs, max_tokens={max_tokens}")
    prompt = build_secretary_prompt(
        current_minutes or "", labeled_text)
    try:
        minutes_text = await provider.generate_ai_response(
            prompt, temperature=0, max_tokens=max_tokens)
    except Exception as e:
        logger.error(f"Secretary failed: {e}")
        return _result(0, 0, {}, "Secretary pass failed")

    # Save raw Secretary output
    try:
        with open(f"data/secretary_raw_{channel_id}.txt", "w") as f:
            f.write(minutes_text)
    except Exception as e:
        logger.warning(f"Failed to save secretary output: {e}")

    # --- Pass 2: Structurer ---
    logger.info(f"Structurer pass for channel {channel_id}")
    struct_prompt = build_structurer_prompt(
        minutes_text, current_json=current_json)
    try:
        response = await provider.generate_ai_response(
            struct_prompt, temperature=0,
            response_mime_type="application/json",
            response_json_schema=STRUCTURER_SCHEMA,
            use_json_schema=True)
    except Exception as e:
        logger.error(f"Structurer failed: {e}")
        return _result(len(messages), 0, {}, str(e))

    from utils.summarizer import _process_response
    from utils.summary_schema import make_empty_summary as _empty
    base = current_json or _empty(channel_id)
    delta, err = await _process_response(
        response, base, set(), channel_id, provider,
        struct_prompt, STRUCTURER_SCHEMA)
    if err:
        return _result(len(messages), 0, {}, err)

    translate_ops(delta)

    # Save Structurer output
    try:
        with open(f"data/structurer_raw_{channel_id}.json", "w") as f:
            json.dump(delta, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save structurer output: {e}")

    # --- Pass 3: Classifier ---
    ops = delta.get("ops", [])
    pre_count = len(ops)
    classifier_drops = []
    try:
        from utils.summary_classifier import classify_ops, filter_ops
        verdicts = await classify_ops(ops, existing_summary=current_json)
        ops, classifier_drops = filter_ops(ops, verdicts)
        delta["ops"] = ops
        logger.info(f"Classifier: {pre_count} → {len(ops)} ops")
    except Exception as e:
        logger.warning(f"Classifier failed, keeping all ops: {e}")

    # Save Classifier output
    try:
        with open(f"data/classifier_raw_{channel_id}.json", "w") as f:
            json.dump({"kept": [o.get("id") for o in ops],
                       "dropped": [{"id": o.get("id", ""),
                                    "op": o.get("op", ""),
                                    "text": o.get("text", "")
                                        or o.get("title", "")}
                                   for o in classifier_drops]},
                      f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save classifier output: {e}")

    # --- Apply ops and store ---
    base_summary = current_json or make_empty_summary(channel_id)
    updated = apply_ops(base_summary, delta)
    mismatches, verified = verify_protected_hashes(
        updated, base_summary)

    token_count = estimate_tokens(json.dumps(updated))
    updated["summary_token_count"] = token_count
    last_id = messages[-1].id
    mr = base_summary.get("meta", {}).get("message_range", {})
    first_id = mr.get("first_id", messages[0].id)
    prev_count = mr.get("count", 0)

    protected_count = sum(
        len(updated.get(k, []))
        for k in ("decisions", "key_facts", "action_items",
                  "pinned_memory"))
    verification = {
        "protected_items_count": protected_count,
        "hashes_verified": verified, "mismatches": mismatches,
        "source_checks_passed": 0, "source_checks_failed": 0}
    updated["meta"].update({
        "model": f"{prov_name}/{model_name}",
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "token_count": token_count,
        "message_range": {"first_id": first_id, "last_id": last_id,
                          "count": prev_count + len(messages)},
        "verification": verification,
        "minutes_text": minutes_text,
        "classifier_drops": [
            {"id": o.get("id", ""), "op": o.get("op", ""),
             "text": o.get("text", "") or o.get("title", "")}
            for o in classifier_drops]})

    await asyncio.to_thread(
        save_channel_summary, channel_id, json.dumps(updated),
        updated["meta"]["message_range"]["count"], last_id)

    if token_count > 2000:
        logger.warning(f"Token count {token_count} exceeds target")
    logger.info(
        f"Pipeline complete: {len(messages)} msgs, "
        f"{token_count} tokens")
    return _result(len(messages), token_count, verification, None)


def _secretary_max_tokens(msg_count, current_minutes=None):
    """Scale output budget: existing minutes + 4/msg + 1024 headroom.
    Cold start: 1024 + 4*msgs. Incremental: existing + 4*msgs + 1024."""
    existing = estimate_tokens(current_minutes) if current_minutes else 0
    return min(existing + (msg_count * 4) + 1024, 16384)


def _result(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}
