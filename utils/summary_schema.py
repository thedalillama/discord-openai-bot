# utils/summary_schema.py
# Version 1.3.0
"""
Summary schema utilities: DELTA_SCHEMA, empty factory, hash utilities,
ops application, and integrity verification.

CHANGES v1.3.0: Remove notes from DELTA_SCHEMA
- REMOVED: notes field from DELTA_SCHEMA — Gemini was using it as a reasoning
  scratchpad, producing paragraphs of text that bloated output and caused truncation

CHANGES v1.2.0: Reject empty text in _supersede()
- FIXED: _supersede() now skips appending the new decision if text is empty,
  preventing ghost entries with empty decision field and hash of empty string

CHANGES v1.1.0: SOW v3.2.0 full compliance
- ADDED: DELTA_SCHEMA — ops[] JSON schema for Gemini response_json_schema
- REPLACED: apply_updates()/_apply_list_updates() → apply_ops() + helpers
  (_add_if_new, _update_status, _supersede); handles all 13 op types
- UPDATED: verify_protected_hashes() — unified text_hash for all protected
  sections (was: decision_hash/fact_hash/task_hash/text_hash)

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import hashlib
import copy
from datetime import datetime, timezone
from utils.logging_utils import get_logger

logger = get_logger('summary_schema')

DELTA_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "mode", "ops"],
    "properties": {
        "schema_version": {"type": "string", "enum": ["delta.v1"]},
        "mode": {"type": "string", "enum": ["incremental"]},
        "ops": {"type": "array", "items": {
            "type": "object",
            "required": ["op", "id"],
            "properties": {
                "op": {"type": "string", "enum": [
                    "add_fact", "add_decision", "add_topic", "add_action_item",
                    "add_open_question", "add_pinned_memory", "update_overview",
                    "update_topic_status", "complete_action_item", "close_open_question",
                    "supersede_decision", "add_participant", "noop",
                ]},
                "id": {"type": "string"},
                "text": {"type": "string"},
                "title": {"type": "string"},
                "status": {"type": "string"},
                "category": {"type": "string"},
                "owner": {"type": "string"},
                "deadline": {"type": "string"},
                "source_message_ids": {"type": "array", "items": {"type": "string"}},
                "supersedes_id": {"type": "string"},
            },
        }},
    },
}


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
                "protected_items_count": 0, "hashes_verified": 0,
                "mismatches": 0, "source_checks_passed": 0, "source_checks_failed": 0,
            },
        },
    }


def compute_hash(text):
    """Return SHA-256 of text, truncated to 8 hex characters."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def apply_ops(current, delta):
    """Apply delta ops[] to current summary. Returns deep copy with ops applied.
    Protected field text is set only at item creation. Duplicate ADD IDs rejected."""
    summary = copy.deepcopy(current)
    summary["updated_at"] = datetime.now(timezone.utc).isoformat()

    for op in delta.get("ops", []):
        t   = op.get("op", "")
        oid = op.get("id", "")
        if t == "noop": continue
        elif t == "update_overview":
            if op.get("text"): summary["overview"] = op["text"]
        elif t == "add_participant":
            if not any(p["id"] == oid for p in summary["participants"]):
                summary["participants"].append({
                    "id": oid, "display_name": op.get("text") or op.get("title") or oid,
                })
        elif t == "add_topic":
            _add_if_new(summary["active_topics"], oid, {
                "id": oid, "title": op.get("title") or op.get("text", ""),
                "status": op.get("status", "active"),
                "source_message_ids": op.get("source_message_ids", []),
            })
        elif t == "update_topic_status": _update_status(summary["active_topics"], oid, op.get("status"))
        elif t == "add_decision":
            text = op.get("text", "")
            _add_if_new(summary["decisions"], oid, {
                "id": oid, "decision": text, "text_hash": compute_hash(text),
                "status": op.get("status", "active"), "notes": op.get("notes"),
                "source_message_ids": op.get("source_message_ids", []),
            })
        elif t == "supersede_decision": _supersede(summary["decisions"], op)
        elif t == "add_fact":
            text = op.get("text", "")
            _add_if_new(summary["key_facts"], oid, {
                "id": oid, "fact": text, "text_hash": compute_hash(text),
                "category": op.get("category"), "status": op.get("status", "active"),
                "source_message_ids": op.get("source_message_ids", []),
            })
        elif t == "add_action_item":
            text = op.get("text", "")
            _add_if_new(summary["action_items"], oid, {
                "id": oid, "task": text, "text_hash": compute_hash(text),
                "status": op.get("status", "open"),
                "owner": op.get("owner"), "deadline": op.get("deadline"),
                "source_message_ids": op.get("source_message_ids", []),
            })
        elif t == "complete_action_item": _update_status(summary["action_items"], oid, "completed")
        elif t == "add_open_question":
            _add_if_new(summary["open_questions"], oid, {
                "id": oid, "question": op.get("text", ""), "status": "open",
                "source_message_ids": op.get("source_message_ids", []),
                "notes": op.get("notes"),
            })
        elif t == "close_open_question": _update_status(summary["open_questions"], oid, "answered")
        elif t == "add_pinned_memory":
            text = op.get("text", "")
            _add_if_new(summary["pinned_memory"], oid, {
                "id": oid, "text": text, "text_hash": compute_hash(text),
                "status": "active", "source_message_ids": op.get("source_message_ids", []),
            })
        else: logger.warning(f"Unknown op type ignored: {t}")

    return summary


def _add_if_new(lst, item_id, item):
    if any(x["id"] == item_id for x in lst):
        logger.warning(f"Duplicate ADD rejected: id={item_id}")
        return
    lst.append(item)

def _update_status(lst, item_id, status):
    for item in lst:
        if item["id"] == item_id:
            item["status"] = status
            return
    logger.warning(f"Cannot update status: unknown id={item_id}")

def _supersede(decisions, op):
    text = op.get("text", "").strip()
    if not text:
        logger.warning(f"supersede_decision id={op.get('id')}: rejected — empty text field")
        return
    old_id = op.get("supersedes_id")
    for d in decisions:
        if d["id"] == old_id:
            d["status"] = "superseded"
            break
    decisions.append({
        "id": op.get("id"), "decision": text, "text_hash": compute_hash(text),
        "status": op.get("status", "active"), "supersedes_id": old_id,
        "source_message_ids": op.get("source_message_ids", []), "notes": op.get("notes"),
    })


def verify_protected_hashes(candidate, snapshot):
    """Check text_hash on protected items; assign hashes to new items;
    restore from snapshot on mismatch. Returns (mismatches, verified)."""
    _HASH_FIELDS = [
        ("decisions",    "decision"),
        ("key_facts",    "fact"),
        ("action_items", "task"),
        ("pinned_memory","text"),
    ]
    snap_idx = {lst: {it["id"]: it for it in snapshot.get(lst, [])} for lst, _ in _HASH_FIELDS}
    mismatches = verified = 0

    for list_key, content_field in _HASH_FIELDS:
        for item in candidate.get(list_key, []):
            content = item.get(content_field, "")
            stored  = item.get("text_hash")
            if stored is None:
                item["text_hash"] = compute_hash(content)
                verified += 1
                continue
            if compute_hash(content) != stored:
                mismatches += 1
                snap = snap_idx[list_key].get(item.get("id"))
                if snap:
                    item[content_field] = snap[content_field]
                    item["text_hash"]   = snap["text_hash"]
                logger.warning(
                    f"Hash mismatch on {list_key} id={item.get('id')} — "
                    f"{'restored from snapshot' if snap else 'no snapshot available'}"
                )
            else:
                verified += 1
    return mismatches, verified


def run_source_verification(summary, messages_by_id):
    """Set source_verified on pinned key_facts and pinned_memory items
    (only where source_verified is None). Returns (passed, failed)."""
    _PINNED_CATEGORIES = {"metric", "reference", "constraint", "commitment"}
    passed = failed = 0

    def _check(item, text_field):
        nonlocal passed, failed
        if item.get("source_verified") is not None:
            return
        text     = item.get(text_field, "")
        combined = " ".join(messages_by_id.get(sid, "") for sid in item.get("source_message_ids", []))
        if text and text in combined:
            item["source_verified"] = True;  passed += 1
        else:
            item["source_verified"] = False; failed += 1
            logger.warning(f"Source verification failed: {text_field}='{text[:60]}'")

    for fact in summary.get("key_facts", []):
        if fact.get("category") in _PINNED_CATEGORIES:
            _check(fact, "fact")
    for pin in summary.get("pinned_memory", []):
        _check(pin, "text")
    return passed, failed
