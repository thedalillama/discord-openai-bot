# utils/summarizer.py
# Version 1.8.0
"""
Summarization pipeline orchestrator.

Three-layer enforcement (SOW v3.2.0):
  Layer 1 — Gemini Structured Outputs: response_mime_type + DELTA_SCHEMA
  Layer 2 — Normalization: classify → canonicalize → diff_full_to_ops
  Layer 3 — Domain validation: source IDs, duplicate IDs, status transitions

CHANGES v1.8.0: Filter summary command output from summarizer input
- ADDED: is_summary_output() filter in _get_unsummarized_messages() — excludes
  !summary create results, !summary display, and !summary clear confirmations

CHANGES v1.7.0: DEBUG-level pipeline tracing
- ADDED: batch header log (batch N, message range, human/bot counts)
- ADDED: full prompt logged at DEBUG before each API call
- ADDED: full raw API response logged at DEBUG after each call
- ADDED: classification and op counts logged at DEBUG in _process_response
- ADDED: repair call logged at DEBUG with error reasons

CHANGES v1.6.0: Include bot messages as [BOT]-labeled context
- REMOVED: is_bot_author filter from _get_unsummarized_messages(); bot responses
  are now passed to Gemini so it can see what questions were answered and what
  facts were established; build_label_map() marks them with [BOT] suffix

CHANGES v1.5.0: Filter bot-authored messages from summarization input (SOW v3.2.1)
- ADDED: is_bot_author check in _get_unsummarized_messages(); bot responses
  (AI-generated content) excluded — only human messages are summarized

CHANGES v1.4.0: Filter "System prompt updated for" from summarization input
- ADDED: "System prompt updated for" excluded in _get_unsummarized_messages();
  kept in channel_history for realtime_settings_parser.py but noise for summarizer

CHANGES v1.3.0: Housekeeping noise filter in _get_unsummarized_messages()
- ADDED: is_history_output(), is_settings_persistence_message(), !-command filter

CHANGES v1.2.0: Batch loop (SOW v3.2.0)
- ADDED: summarize_channel() loops over SUMMARIZER_BATCH_SIZE chunks until all
  unsummarized messages are processed; summary state reloaded from DB each
  iteration so each batch builds on the previous result
- ADDED: SUMMARIZER_BATCH_SIZE imported from config
- CHANGED: returns total messages_processed across all batches; token_count and
  verification reflect the final batch state

CHANGES v1.1.0: Full SOW compliance
- REPLACED: system prompt → SOW-specified strict instruction (summary_prompts.py)
- ADDED: Gemini Structured Outputs (response_mime_type + DELTA_SCHEMA)
- ADDED: Three-layer pipeline: classify → normalize → validate → apply_ops
- ADDED: Repair prompt retry on parse/classify failure (one attempt)
- UPDATED: _build_prompt() → SOW template; moved to summary_prompts.py
- UPDATED: _translate_labels_to_ids() → iterates ops[] not legacy list keys
- REPLACED: apply_updates() → apply_ops() from summary_schema
- SPLIT: prompt helpers → summary_prompts.py; JSON parse → summary_normalization.py

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import asyncio
import json
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer')


async def summarize_channel(channel_id, batch_size=None):
    """Generate or update the structured summary for a channel.

    Loops in batches of SUMMARIZER_BATCH_SIZE until all unsummarized messages
    are consumed. Returns {messages_processed, token_count, verification, error}.
    """
    from utils.summary_store import get_channel_summary, save_channel_summary
    from utils.summary_schema import (
        make_empty_summary, apply_ops, verify_protected_hashes,
        run_source_verification, DELTA_SCHEMA,
    )
    from utils.summary_prompts import build_label_map, build_prompt
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL, SUMMARIZER_BATCH_SIZE

    effective_batch = batch_size if batch_size is not None else SUMMARIZER_BATCH_SIZE
    provider = get_provider(SUMMARIZER_PROVIDER)
    total_processed = 0
    last_token_count = 0
    last_verification = {}
    batch_num = 0

    while True:
        # Reload fresh each iteration — picks up the save from the previous batch.
        summary_json, last_message_id = await asyncio.to_thread(
            get_channel_summary, channel_id
        )
        if summary_json:
            try:
                current = json.loads(summary_json)
            except Exception as e:
                logger.error(f"Failed to parse stored summary for channel {channel_id}: {e}")
                current = make_empty_summary(channel_id)
                last_message_id = None
        else:
            current = make_empty_summary(channel_id)
            last_message_id = None

        new_messages = await _get_unsummarized_messages(channel_id, last_message_id)
        new_messages = new_messages[:effective_batch]
        if not new_messages:
            break

        batch_num += 1
        human_count = sum(1 for m in new_messages if not m.is_bot_author)
        bot_count = len(new_messages) - human_count
        logger.debug(
            f"Batch {batch_num}: {len(new_messages)} messages "
            f"({human_count} human, {bot_count} bot) — "
            f"ids {new_messages[0].id}..{new_messages[-1].id}"
        )

        label_to_id, labeled_text = build_label_map(new_messages)
        context_labels = set(label_to_id.keys())
        prompt_messages = build_prompt(current, labeled_text)

        logger.debug(
            f"Batch {batch_num} — SYSTEM PROMPT:\n{prompt_messages[0]['content']}"
        )
        logger.debug(
            f"Batch {batch_num} — USER MESSAGE:\n{prompt_messages[1]['content']}"
        )

        try:
            response_text = await provider.generate_ai_response(
                prompt_messages, temperature=0,
                response_mime_type="application/json",
                response_json_schema=DELTA_SCHEMA,
            )
        except Exception as e:
            logger.error(f"Summarizer provider call failed for channel {channel_id}: {e}")
            return _partial(total_processed, last_token_count, last_verification, str(e))

        logger.debug(f"Batch {batch_num} — RAW RESPONSE:\n{response_text}")

        delta, err = await _process_response(
            response_text, current, context_labels,
            channel_id, provider, prompt_messages, DELTA_SCHEMA,
            batch_num=batch_num,
        )
        if err:
            return _partial(total_processed, last_token_count, last_verification, err)

        _translate_labels_to_ids(delta.get("ops", []), label_to_id)
        updated = apply_ops(current, delta)
        mismatches, verified = verify_protected_hashes(updated, current)
        messages_by_id = {msg.id: msg.content for msg in new_messages}
        src_passed, src_failed = run_source_verification(updated, messages_by_id)

        token_count = estimate_tokens(json.dumps(updated))
        updated["summary_token_count"] = token_count
        last_id = new_messages[-1].id
        protected_count = sum(
            len(updated.get(k, []))
            for k in ("decisions", "key_facts", "action_items", "pinned_memory")
        )
        verification = {
            "protected_items_count": protected_count,
            "hashes_verified": verified, "mismatches": mismatches,
            "source_checks_passed": src_passed, "source_checks_failed": src_failed,
        }
        updated["meta"].update({
            "model": f"{SUMMARIZER_PROVIDER}/{SUMMARIZER_MODEL}",
            "summarized_at": datetime.now(timezone.utc).isoformat(),
            "token_count": token_count,
            "message_range": {
                "first_id": new_messages[0].id,
                "last_id": last_id,
                "count": len(new_messages),
            },
            "verification": verification,
        })

        prior_count = current.get("meta", {}).get("message_range", {}).get("count", 0)
        await asyncio.to_thread(
            save_channel_summary, channel_id,
            json.dumps(updated), prior_count + len(new_messages), last_id,
        )

        total_processed += len(new_messages)
        last_token_count, last_verification = token_count, verification
        if token_count > 2000:
            logger.warning(f"Summary token count {token_count} exceeds 2000 target")
        logger.info(
            f"Batch {batch_num} saved for channel {channel_id}: "
            f"{len(new_messages)} messages, {token_count} tokens, "
            f"{mismatches} hash mismatches"
        )

    if total_processed == 0:
        logger.info(f"No new messages to summarize for channel {channel_id}")
    else:
        logger.info(
            f"Summarization complete for channel {channel_id}: "
            f"{total_processed} messages across {batch_num} batch(es)"
        )
    return _partial(total_processed, last_token_count, last_verification, None)


def _partial(processed, token_count, verification, error):
    return {"messages_processed": processed, "token_count": token_count,
            "verification": verification, "error": error}


async def _process_response(response_text, pre_state, context_labels,
                             channel_id, provider, prompt_messages, delta_schema,
                             batch_num=0):
    """Parse (Layer 2) and domain-validate (Layer 3). One repair retry on failure."""
    from utils.summary_normalization import (
        parse_json_response, classify_response, canonicalize_full_summary, diff_full_to_ops
    )
    from utils.summary_validation import validate_domain

    errors = []
    for attempt in range(2):
        parsed = parse_json_response(response_text)
        if parsed is None:
            errors.append("Response is not valid JSON")
            if attempt == 0:
                logger.debug(f"Batch {batch_num} — parse failed, sending repair prompt")
                response_text = await _repair_call(
                    provider, prompt_messages, errors, delta_schema, channel_id
                )
                logger.debug(f"Batch {batch_num} — REPAIR RESPONSE:\n{response_text}")
                continue
            return None, "; ".join(errors)

        kind = classify_response(parsed)
        logger.debug(f"Batch {batch_num} — response classified as: {kind}")

        if kind == "delta":
            delta = parsed
        elif kind == "full":
            logger.info(f"Full summary response — normalizing to delta (channel {channel_id})")
            ops = diff_full_to_ops(pre_state, canonicalize_full_summary(parsed))
            delta = {"schema_version": "delta.v1", "mode": "incremental", "ops": ops}
        else:
            errors.append("Unknown response shape (not delta or full summary)")
            if attempt == 0:
                logger.debug(f"Batch {batch_num} — unknown shape, sending repair prompt")
                response_text = await _repair_call(
                    provider, prompt_messages, errors, delta_schema, channel_id
                )
                logger.debug(f"Batch {batch_num} — REPAIR RESPONSE:\n{response_text}")
                continue
            return None, "; ".join(errors)

        ops_before = len(delta.get("ops", []))
        delta["ops"] = validate_domain(delta, pre_state, context_labels)
        ops_after = len(delta["ops"])
        logger.debug(
            f"Batch {batch_num} — domain validation: {ops_before} ops in, "
            f"{ops_after} accepted, {ops_before - ops_after} rejected"
        )
        return delta, None

    return None, "; ".join(errors)


async def _repair_call(provider, original_messages, errors, delta_schema, channel_id):
    """Resend the original prompt with a repair instruction appended. One retry only."""
    repair = (
        "Your previous output failed validation.\n\n"
        "VALIDATION_ERRORS:\n" +
        "\n".join(f"- {e}" for e in errors) +
        "\n\nReturn ONLY corrected JSON conforming to the schema. No other text."
    )
    try:
        return await provider.generate_ai_response(
            original_messages + [{"role": "user", "content": repair}],
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=delta_schema,
        )
    except Exception as e:
        logger.error(f"Repair call failed for channel {channel_id}: {e}")
        return ""


async def _get_unsummarized_messages(channel_id, last_message_id):
    """Return unsummarized messages, excluding housekeeping noise (bot commands,
    settings confirmations, history output) — same filters as prepare_messages_for_api().
    Bot-authored messages are included but flagged via is_bot_author for label marking."""
    from utils.message_store import get_channel_messages
    from utils.history.message_processing import (
        is_history_output, is_settings_persistence_message, is_summary_output,
    )
    all_messages = await asyncio.to_thread(get_channel_messages, channel_id)
    if last_message_id is not None:
        all_messages = [m for m in all_messages if m.id > last_message_id]
    return [
        m for m in all_messages if m.content
        and not m.content.startswith('!')
        and not is_history_output(m.content)
        and not is_settings_persistence_message(m.content)
        and not is_summary_output(m.content)
        and "System prompt updated for" not in m.content
    ]


def _translate_labels_to_ids(ops, label_to_id):
    """Replace M-label strings with integer snowflake IDs in ops[].source_message_ids."""
    for op in ops:
        if "source_message_ids" in op:
            op["source_message_ids"] = [
                label_to_id.get(mid, mid) for mid in op["source_message_ids"]
            ]
