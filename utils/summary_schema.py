# utils/summary_schema.py
# Version 1.0.0
"""
Summary JSON schema utilities: factory, hash computation, update application,
and verification functions.

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
- ADDED: make_empty_summary() — blank summary structure for a channel
- ADDED: compute_hash() — SHA-256 truncated to 8 hex chars
- ADDED: apply_updates() — apply LLM incremental update dict to a summary
- ADDED: verify_protected_hashes() — detect and restore corrupted hashed fields
- ADDED: run_source_verification() — verify extracted facts against source messages

Protected fields (hashed at creation, immutable after):
  decisions.decision, key_facts.fact, action_items.task, pinned_memory.text

source_verified applies to key_facts with category in
(metric, reference, constraint, commitment) and all pinned_memory items.
"""
import hashlib
import copy
from datetime import datetime, timezone
from utils.logging_utils import get_logger

logger = get_logger('summary_schema')


def make_empty_summary(channel_id):
    """Return a blank summary dict for the given channel ID."""
    return {
        "schema_version": "1.0",
        "channel_id": str(channel_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "summary_token_count": 0,
        "participants": [],
        "overview": "",
        "active_topics": [],
        "decisions": [],
        "key_facts": [],
        "action_items": [],
        "open_questions": [],
        "pinned_memory": [],
        "meta": {
            "model": "",
            "summarized_at": "",
            "token_count": 0,
            "message_range": {"first_id": 0, "last_id": 0, "count": 0},
            "verification": {
                "protected_items_count": 0,
                "hashes_verified": 0,
                "mismatches": 0,
                "source_checks_passed": 0,
                "source_checks_failed": 0,
            },
        },
    }


def compute_hash(text):
    """Return SHA-256 of text, truncated to 8 hex characters."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def apply_updates(current, updates):
    """
    Apply the LLM's incremental update dict to the current summary.

    Duplicate ADD operations (item ID already in the list) are rejected and
    logged. Returns a deep copy with updates applied — does not mutate current.

    Args:
        current: Current summary dict
        updates: Incremental update dict from LLM response

    Returns:
        dict: New summary with updates applied
    """
    summary = copy.deepcopy(current)
    summary["updated_at"] = datetime.now(timezone.utc).isoformat()

    if updates.get("overview_update"):
        summary["overview"] = updates["overview_update"]

    existing_pids = {p["id"] for p in summary["participants"]}
    for p in updates.get("new_participants", []):
        if p.get("id") not in existing_pids:
            summary["participants"].append(p)
            existing_pids.add(p["id"])

    _apply_list_updates(summary, "active_topics",  updates.get("topic_updates", []))
    _apply_list_updates(summary, "decisions",       updates.get("decision_updates", []))
    _apply_list_updates(summary, "key_facts",       updates.get("fact_updates", []))
    _apply_list_updates(summary, "action_items",    updates.get("action_item_updates", []))
    _apply_list_updates(summary, "open_questions",  updates.get("question_updates", []))
    _apply_list_updates(summary, "pinned_memory",   updates.get("pinned_memory_updates", []))

    return summary


def _apply_list_updates(summary, key, update_list):
    """Apply a list of {action, item} operations to summary[key]."""
    items = summary[key]
    id_to_idx = {item["id"]: i for i, item in enumerate(items)}
    # Protected fields must never be overwritten by update/close/answer actions
    _PROTECTED = {"decision", "fact", "task", "text",
                  "decision_hash", "fact_hash", "task_hash", "text_hash"}

    for entry in update_list:
        action = entry.get("action", "").lower()
        item = entry.get("item", {})
        item_id = item.get("id")

        if action == "add":
            if item_id in id_to_idx:
                logger.warning(f"Duplicate ADD rejected: {key} id={item_id}")
                continue
            items.append(item)
            id_to_idx[item_id] = len(items) - 1

        elif action == "supersede":
            old_id = item.get("supersedes")
            if old_id and old_id in id_to_idx:
                items[id_to_idx[old_id]]["status"] = "superseded"
            items.append(item)
            if item_id:
                id_to_idx[item_id] = len(items) - 1

        elif action in ("update", "close", "complete", "answer"):
            if item_id not in id_to_idx:
                logger.warning(f"Cannot {action} unknown {key} id={item_id}")
                continue
            idx = id_to_idx[item_id]
            for k, v in item.items():
                if k not in _PROTECTED:
                    items[idx][k] = v


def verify_protected_hashes(candidate, snapshot):
    """
    Check all hashed fields in candidate against their stored hashes.
    Assigns hashes to new items. Restores protected field from snapshot on
    mismatch.

    Args:
        candidate: Post-update summary dict (mutated in place)
        snapshot:  Pre-update summary dict (read-only)

    Returns:
        tuple: (mismatches: int, verified: int)
    """
    _HASH_FIELDS = [
        ("decisions",    "decision", "decision_hash"),
        ("key_facts",    "fact",     "fact_hash"),
        ("action_items", "task",     "task_hash"),
        ("pinned_memory","text",     "text_hash"),
    ]
    snap_idx = {
        lst: {it["id"]: it for it in snapshot.get(lst, [])}
        for lst, _, _ in _HASH_FIELDS
    }
    mismatches = verified = 0

    for list_key, content_field, hash_field in _HASH_FIELDS:
        for item in candidate.get(list_key, []):
            content = item.get(content_field, "")
            stored_hash = item.get(hash_field)

            if stored_hash is None:
                # New item — compute and store hash
                item[hash_field] = compute_hash(content)
                verified += 1
                continue

            if compute_hash(content) != stored_hash:
                mismatches += 1
                snap = snap_idx[list_key].get(item.get("id"))
                if snap:
                    item[content_field] = snap[content_field]
                    item[hash_field] = snap[hash_field]
                logger.warning(
                    f"Hash mismatch on {list_key} id={item.get('id')} — "
                    f"{'restored from snapshot' if snap else 'no snapshot; mismatch logged only'}"
                )
            else:
                verified += 1

    return mismatches, verified


def run_source_verification(summary, messages_by_id):
    """
    Set source_verified on new key_facts (pinned categories) and pinned_memory.

    Only runs on items where source_verified is None (not yet checked).

    Args:
        summary:        Summary dict (mutated in place)
        messages_by_id: {snowflake_id: content_string} mapping

    Returns:
        tuple: (passed: int, failed: int)
    """
    _PINNED_CATEGORIES = {"metric", "reference", "constraint", "commitment"}
    passed = failed = 0

    def _check(item, text_field):
        nonlocal passed, failed
        if item.get("source_verified") is not None:
            return  # already checked on a prior run
        text = item.get(text_field, "")
        combined = " ".join(
            messages_by_id.get(sid, "") for sid in item.get("source_message_ids", [])
        )
        if text and text in combined:
            item["source_verified"] = True
            passed += 1
        else:
            item["source_verified"] = False
            failed += 1
            logger.warning(f"Source verification failed: {text_field}='{text[:60]}'")

    for fact in summary.get("key_facts", []):
        if fact.get("category") in _PINNED_CATEGORIES:
            _check(fact, "fact")
    for pin in summary.get("pinned_memory", []):
        _check(pin, "text")

    return passed, failed
