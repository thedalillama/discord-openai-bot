# utils/summarizer.py
# Version 1.0.0
"""
Summarization engine: reads raw messages, calls LLM, applies updates,
verifies integrity, and stores the result.

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
- ADDED: summarize_channel() — main entry point
- ADDED: _get_unsummarized_messages() — fetch messages after last_message_id
- ADDED: _build_label_map() — assign M1/M2/M3 labels, return label→id mapping
- ADDED: _build_prompt() — construct system+user message list for LLM
- ADDED: _translate_labels_to_ids() — replace M-labels with real snowflake IDs
- ADDED: _parse_json_response() — parse LLM output, strip markdown fences

Provider calls go through provider.generate_ai_response() which handles
loop.run_in_executor() internally — matching the established convention.
SQLite reads/writes use asyncio.to_thread() — matching raw_events.py pattern.

Note: SUMMARIZER_MODEL is stored in meta for reference. The provider singleton
uses whatever model it was initialised with; per-call model overrides require
a provider refactor (deferred to a future version).
"""
import asyncio
import json
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.context_manager import estimate_tokens

logger = get_logger('summarizer')

# Maximum messages processed per !summarize call to bound prompt size.
_MAX_MESSAGES = 500

_SYSTEM_PROMPT = (
    "You are a conversation summarizer. You receive a current summary JSON "
    "and a batch of new messages. Return ONLY a valid JSON object with the "
    "changes to apply — no markdown, no explanation, just the JSON.\n\n"
    "RULES:\n"
    "- Return incremental updates only: ADD, SUPERSEDE, CLOSE, COMPLETE, "
    "ANSWER, or UPDATE operations on specific items.\n"
    "- Never modify the protected field of any existing decision, key_fact, "
    "action_item, or pinned_memory item.\n"
    "- To change a decision, SUPERSEDE it: set old status to 'superseded' "
    "and create a new item with a 'supersedes' back-reference.\n"
    "- Preserve filenames, paths, URLs, version numbers, and numerical values "
    "exactly as they appear in the source messages.\n"
    "- Use source_message_ids to reference the M-labels (e.g. 'M1', 'M2') "
    "provided in the context.\n"
    "- Only promote durable information. Skip casual filler and greetings.\n"
    "- Keep the overview to 1-3 sentences."
)


async def summarize_channel(channel_id):
    """
    Generate or update the structured summary for a channel.

    Returns:
        dict: {messages_processed, token_count, verification, error}
              error is None on success, or an error string on failure.
    """
    from utils.summary_store import get_channel_summary, save_channel_summary
    from utils.summary_schema import (
        make_empty_summary, apply_updates,
        verify_protected_hashes, run_source_verification,
    )
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL

    _empty = {"messages_processed": 0, "token_count": 0, "verification": {}, "error": None}

    # Load or initialise summary
    summary_json, last_message_id = await asyncio.to_thread(get_channel_summary, channel_id)
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

    # Fetch unsummarised messages
    new_messages = await _get_unsummarized_messages(channel_id, last_message_id)
    if not new_messages:
        logger.info(f"No new messages to summarize for channel {channel_id}")
        return _empty

    label_to_id, labeled_text = _build_label_map(new_messages)
    prompt_messages = _build_prompt(json.dumps(current, indent=2), labeled_text)

    # Call LLM
    try:
        provider = get_provider(SUMMARIZER_PROVIDER)
        response_text = await provider.generate_ai_response(prompt_messages, temperature=0)
    except Exception as e:
        logger.error(f"Summarizer provider call failed for channel {channel_id}: {e}")
        return {**_empty, "error": str(e)}

    updates = _parse_json_response(response_text)
    if updates is None:
        return {**_empty, "error": "LLM returned invalid JSON"}

    _translate_labels_to_ids(updates, label_to_id)

    snapshot = current
    updated = apply_updates(current, updates)
    mismatches, verified = verify_protected_hashes(updated, snapshot)

    messages_by_id = {msg.id: msg.content for msg in new_messages}
    src_passed, src_failed = run_source_verification(updated, messages_by_id)

    # Token count and meta
    summary_str = json.dumps(updated)
    token_count = estimate_tokens(summary_str)
    updated["summary_token_count"] = token_count

    last_id = new_messages[-1].id
    protected_count = sum(
        len(updated.get(k, []))
        for k in ("decisions", "key_facts", "action_items", "pinned_memory")
    )
    verification = {
        "protected_items_count": protected_count,
        "hashes_verified": verified,
        "mismatches": mismatches,
        "source_checks_passed": src_passed,
        "source_checks_failed": src_failed,
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
        json.dumps(updated), prior_count + len(new_messages), last_id
    )

    if token_count > 2000:
        logger.warning(f"Summary token count {token_count} exceeds 2000 target for channel {channel_id}")
    logger.info(
        f"Summary saved for channel {channel_id}: {len(new_messages)} messages, "
        f"{token_count} tokens, {mismatches} hash mismatches"
    )
    return {"messages_processed": len(new_messages), "token_count": token_count,
            "verification": verification, "error": None}


async def _get_unsummarized_messages(channel_id, last_message_id):
    """Return messages after last_message_id, capped at _MAX_MESSAGES."""
    from utils.message_store import get_channel_messages
    all_messages = await asyncio.to_thread(get_channel_messages, channel_id)
    if last_message_id is not None:
        all_messages = [m for m in all_messages if m.id > last_message_id]
    return all_messages[-_MAX_MESSAGES:]


def _build_label_map(messages):
    """
    Assign M1/M2/M3 labels to messages.

    Returns:
        tuple: (label_to_id dict, labeled_text string)
    """
    label_to_id = {}
    lines = []
    for i, msg in enumerate(messages, 1):
        label = f"M{i}"
        label_to_id[label] = msg.id
        ts = msg.created_at[:16] if msg.created_at else ""
        lines.append(f"[{label}] {msg.author_name} ({ts}): {msg.content}")
    return label_to_id, "\n".join(lines)


def _build_prompt(current_summary_json, labeled_text):
    """Build the [system, user] message list for the summarizer LLM call."""
    user_content = (
        f"Current summary:\n{current_summary_json}\n\n"
        f"New messages:\n{labeled_text}\n\n"
        "Return the incremental update JSON now."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


def _parse_json_response(text):
    """Parse JSON from LLM response, stripping markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:200]}")
        return None


def _translate_labels_to_ids(updates, label_to_id):
    """Replace M-label strings with integer snowflake IDs in all source_message_ids."""
    def _translate(id_list):
        result = []
        for item_id in id_list:
            if isinstance(item_id, str) and item_id in label_to_id:
                result.append(label_to_id[item_id])
            elif isinstance(item_id, int):
                result.append(item_id)
        return result

    for list_key in ("topic_updates", "decision_updates", "fact_updates",
                     "action_item_updates", "question_updates", "pinned_memory_updates"):
        for entry in updates.get(list_key, []):
            item = entry.get("item", {})
            if "source_message_ids" in item:
                item["source_message_ids"] = _translate(item["source_message_ids"])
