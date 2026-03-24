# utils/summarizer_authoring.py
# Version 1.5.0
"""
Three-pass authoring pipeline for cold start summarization.

Pass 1 (Secretary): Sends all messages in a single pass to write natural
  language minutes. Gemini's 1M context handles full history easily.
Pass 2 (Structurer): Converts the natural language minutes into
  structured JSON delta ops using Gemini Structured Outputs.
Pass 3 (Classifier): GPT-5.4 nano validates each op — KEEP/DROP/RECLASSIFY.
  Removes misclassified items before apply_ops().

CHANGES v1.5.0: Save Structurer and Classifier outputs to data/ files
- ADDED: data/structurer_raw_{channel_id}.json — raw Structurer delta ops
- ADDED: data/classifier_raw_{channel_id}.json — kept IDs and dropped items

CHANGES v1.4.0: Scaled max_output_tokens for Secretary pass
- ADDED: _secretary_max_tokens() scales output budget with message count
  (base 1024 + 4 per message, capped at 16384). Prevents Gemini's known
  repetition loop from burning 32K+ tokens on the ARCHIVED section.
- REMOVED: _dedup_lines() — not approved; output should not be modified

CHANGES v1.3.0: Save raw Gemini output + classifier drops in meta
CHANGES v1.1.0: Add classifier pass (GPT-5.4 nano) after Structurer
CHANGES v1.0.1: Single-pass Secretary for cold starts
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
    """Three-pass pipeline: Secretary → Structurer → Classifier.

    Returns:
        dict: {messages_processed, token_count, verification, error}
    """
    from utils.summary_store import save_channel_summary
    from utils.summary_schema import (
        make_empty_summary, apply_ops, verify_protected_hashes, DELTA_SCHEMA,
    )
    from utils.summary_prompts import build_label_map
    from utils.summary_prompts_authoring import (
        build_secretary_prompt, build_structurer_prompt,
    )

    if not all_messages:
        logger.info(f"No messages to summarize for channel {channel_id}")
        return _result(0, 0, {}, None)

    # --- Pass 1: Secretary ---
    minutes_text, total = await _run_secretary(
        provider, all_messages, build_label_map,
        build_secretary_prompt, channel_id,
    )
    if minutes_text is None:
        return _result(0, 0, {}, "Secretary pass failed")

    # --- Pass 2: Structurer ---
    delta, err = await _run_structurer(
        provider, minutes_text, DELTA_SCHEMA,
        build_structurer_prompt, channel_id,
    )
    if err:
        return _result(total, 0, {}, err)

    # Save Structurer output
    try:
        with open(f"data/structurer_raw_{channel_id}.json", "w") as f:
            json.dump(delta, f, indent=2)
        logger.info(f"Structurer raw output saved: data/structurer_raw_{channel_id}.json")
    except Exception as e:
        logger.warning(f"Failed to save structurer raw output: {e}")

    # --- Pass 3: Classifier ---
    ops = delta.get("ops", [])
    pre_count = len(ops)
    classifier_drops = []
    try:
        from utils.summary_classifier import classify_ops, filter_ops
        verdicts = await classify_ops(ops)
        ops, classifier_drops = filter_ops(ops, verdicts)
        delta["ops"] = ops
        logger.info(
            f"Classifier: {pre_count} → {len(ops)} ops, "
            f"{len(classifier_drops)} dropped for channel {channel_id}")
    except Exception as e:
        logger.warning(f"Classifier failed, keeping all ops: {e}")

    # Save Classifier output
    try:
        classifier_output = {
            "kept": [op.get("id", "") for op in ops],
            "dropped": [
                {"id": op.get("id", ""), "op": op.get("op", ""),
                 "text": op.get("text", "") or op.get("title", "")}
                for op in classifier_drops
            ],
        }
        with open(f"data/classifier_raw_{channel_id}.json", "w") as f:
            json.dump(classifier_output, f, indent=2)
        logger.info(f"Classifier output saved: data/classifier_raw_{channel_id}.json")
    except Exception as e:
        logger.warning(f"Failed to save classifier output: {e}")

    # --- Apply ops and store ---
    empty = make_empty_summary(channel_id)
    updated = apply_ops(empty, delta)
    mismatches, verified = verify_protected_hashes(updated, empty)

    token_count = estimate_tokens(json.dumps(updated))
    updated["summary_token_count"] = token_count
    last_id = all_messages[-1].id

    protected_count = sum(
        len(updated.get(k, []))
        for k in ("decisions", "key_facts", "action_items", "pinned_memory")
    )
    verification = {
        "protected_items_count": protected_count,
        "hashes_verified": verified, "mismatches": mismatches,
        "source_checks_passed": 0, "source_checks_failed": 0,
    }
    updated["meta"].update({
        "model": f"{prov_name}/{model_name}",
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "token_count": token_count,
        "message_range": {
            "first_id": all_messages[0].id, "last_id": last_id,
            "count": len(all_messages),
        },
        "verification": verification,
        "minutes_text": minutes_text,
        "classifier_drops": [
            {"id": op.get("id", ""), "op": op.get("op", ""),
             "text": op.get("text", "") or op.get("title", "")}
            for op in classifier_drops
        ],
    })

    await asyncio.to_thread(
        save_channel_summary, channel_id,
        json.dumps(updated), len(all_messages), last_id,
    )

    if token_count > 2000:
        logger.warning(
            f"Summary token count {token_count} exceeds 2000 target")
    logger.info(
        f"Cold start complete for channel {channel_id}: "
        f"{total} messages, {token_count} summary tokens")
    return _result(total, token_count, verification, None)


async def _run_secretary(provider, all_messages, build_label_map,
                          build_secretary_prompt, channel_id):
    """Pass 1: Send all messages to Secretary in a single pass.
    Output token budget scales with message count to prevent
    Gemini's repetition loop from burning excessive tokens."""
    _, labeled_text = build_label_map(all_messages)

    max_tokens = _secretary_max_tokens(len(all_messages))
    logger.info(
        f"Secretary single-pass: {len(all_messages)} msgs, "
        f"max_output_tokens={max_tokens} "
        f"(ids {all_messages[0].id}..{all_messages[-1].id})")

    prompt = build_secretary_prompt("", labeled_text)
    logger.debug(f"Secretary — PROMPT:\n{prompt[1]['content']}")

    try:
        minutes_text = await provider.generate_ai_response(
            prompt, temperature=0, max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error(f"Secretary pass failed: {e}")
        return None, 0

    # Save raw Gemini output
    try:
        raw_path = f"data/secretary_raw_{channel_id}.txt"
        with open(raw_path, "w") as f:
            f.write(minutes_text)
        logger.info(f"Secretary raw output saved: {raw_path}")
    except Exception as e:
        logger.warning(f"Failed to save secretary raw output: {e}")

    logger.debug(f"Secretary — OUTPUT:\n{minutes_text}")
    logger.info(
        f"Secretary complete for channel {channel_id}: "
        f"{len(all_messages)} msgs in single pass")
    return minutes_text, len(all_messages)


async def _run_structurer(provider, minutes_text, delta_schema,
                           build_structurer_prompt, channel_id):
    """Pass 2: Convert natural language minutes to JSON delta ops."""
    from utils.summarizer import _process_response

    logger.info(f"Structurer pass for channel {channel_id}")
    prompt = build_structurer_prompt(minutes_text, current_json=None)
    logger.debug(f"Structurer — PROMPT:\n{prompt[1]['content']}")

    try:
        response = await provider.generate_ai_response(
            prompt, temperature=0,
            response_mime_type="application/json",
            response_json_schema=delta_schema,
        )
    except Exception as e:
        logger.error(f"Structurer failed for channel {channel_id}: {e}")
        return None, str(e)

    logger.debug(f"Structurer — RESPONSE:\n{response}")

    from utils.summary_schema import make_empty_summary
    empty = make_empty_summary(channel_id)

    delta, err = await _process_response(
        response, empty, set(),
        channel_id, provider, prompt, delta_schema,
    )
    return delta, err


def _secretary_max_tokens(msg_count):
    """Scale Secretary output budget with message count.
    Base 1024 + 4 tokens per message, capped at 16384.
    Prevents Gemini's repetition loop from burning 32K+ tokens."""
    return min(1024 + (msg_count * 4), 16384)


def _result(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}
