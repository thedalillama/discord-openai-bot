# utils/summarizer_authoring.py
# Version 1.0.0
"""
Two-pass authoring pipeline for cold start summarization.

Pass 1 (Secretary): Streams through messages in batches, writing and
  updating natural language minutes with no JSON constraints.
Pass 2 (Structurer): Converts the final natural language minutes into
  structured JSON delta ops using Gemini Structured Outputs.

CREATED v1.0.0: Extracted from summarizer.py v1.9.0
- ADDED: cold_start_pipeline() — full two-pass flow
- ADDED: _run_secretary_batches() — Pass 1 streaming
- ADDED: _run_structurer() — Pass 2 JSON conversion
"""
import asyncio
import json
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer.authoring')


async def cold_start_pipeline(channel_id, provider, batch_size,
                               prov_name, model_name, all_messages):
    """Two-pass pipeline: Secretary writes minutes, Structurer makes JSON.

    Args:
        channel_id: Discord channel ID
        provider: AI provider instance (Gemini)
        batch_size: Messages per Secretary batch
        prov_name: Provider name for meta
        model_name: Model name for meta
        all_messages: List of StoredMessage objects to summarize

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
    minutes_text, total = await _run_secretary_batches(
        provider, all_messages, batch_size, build_label_map,
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
    })

    await asyncio.to_thread(
        save_channel_summary, channel_id,
        json.dumps(updated), len(all_messages), last_id,
    )

    if token_count > 2000:
        logger.warning(f"Summary token count {token_count} exceeds 2000 target")
    logger.info(
        f"Cold start complete for channel {channel_id}: "
        f"{total} messages, {token_count} summary tokens"
    )
    return _result(total, token_count, verification, None)


async def _run_secretary_batches(provider, all_messages, batch_size,
                                  build_label_map, build_secretary_prompt,
                                  channel_id):
    """Pass 1: Stream messages through Secretary in batches.
    Returns (minutes_text, total_processed) or (None, 0) on failure."""
    minutes_text = ""
    total = 0
    batch_num = 0

    for i in range(0, len(all_messages), batch_size):
        batch = all_messages[i:i + batch_size]
        batch_num += 1
        _, labeled_text = build_label_map(batch)

        logger.info(
            f"Secretary batch {batch_num}: {len(batch)} msgs "
            f"(ids {batch[0].id}..{batch[-1].id})"
        )

        prompt = build_secretary_prompt(minutes_text, labeled_text)
        logger.debug(
            f"Secretary batch {batch_num} — PROMPT:\n{prompt[1]['content']}"
        )

        try:
            minutes_text = await provider.generate_ai_response(
                prompt, temperature=0,
            )
        except Exception as e:
            logger.error(f"Secretary batch {batch_num} failed: {e}")
            return None, 0

        logger.debug(
            f"Secretary batch {batch_num} — OUTPUT:\n{minutes_text}"
        )
        total += len(batch)

    logger.info(
        f"Secretary complete for channel {channel_id}: "
        f"{total} msgs in {batch_num} batches"
    )
    return minutes_text, total


async def _run_structurer(provider, minutes_text, delta_schema,
                           build_structurer_prompt, channel_id):
    """Pass 2: Convert natural language minutes to JSON delta ops.
    Returns (delta_dict, None) or (None, error_string)."""
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


def _result(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}
