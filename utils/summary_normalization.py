# utils/summary_normalization.py
# Version 1.0.1
"""
Response parsing, classification, and normalization (Layer 2).

CREATED v1.0.0: SOW v3.2.0
- ADDED: parse_json_response() — three-strategy JSON extraction from LLM text
- ADDED: classify_response() — detect "delta", "full", or "unknown"
- ADDED: canonicalize_full_summary() — field remap and type coercion
- ADDED: diff_full_to_ops() — domain-aware diff of full summary → delta ops[]

CHANGED v1.0.1:
- FIX: canonicalize_full_summary() now maps universal "text" → type-specific content
  field (decision/fact/task/question) when the type-specific field is absent.
  Gemini uses "text" universally; without this fix diff_full_to_ops set empty content
  and apply_ops hashed empty strings (e3b0c442).
- FIX: canonicalize_full_summary() normalizes "supersedes" → "supersedes_id".

Used by summarizer.py for all response parsing and normalization.
"""
import json
import copy
from utils.logging_utils import get_logger

logger = get_logger('summary_normalization')

# section → (content_field, add_op_type)
_SECTIONS = {
    "decisions":      ("decision", "add_decision"),
    "key_facts":      ("fact",     "add_fact"),
    "action_items":   ("task",     "add_action_item"),
    "open_questions": ("question", "add_open_question"),
    "pinned_memory":  ("text",     "add_pinned_memory"),
    "active_topics":  ("title",    "add_topic"),
}
_PROTECTED    = frozenset({"decisions", "key_facts", "action_items", "pinned_memory"})
_STATUS_OPS   = {
    "action_items":   "complete_action_item",
    "open_questions": "close_open_question",
    "active_topics":  "update_topic_status",
}


def parse_json_response(text):
    """Parse JSON from LLM response using three strategies:
    1. Direct parse  2. Strip markdown fence  3. Extract outermost { ... }"""
    text = text.strip()
    if not text:
        logger.error("LLM returned empty response")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        lines = text.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    logger.error(f"Failed to parse LLM response as JSON.\nResponse: {text[:1000]}")
    return None


def classify_response(obj):
    """
    Classify a parsed LLM response dict.

    Returns:
        "delta"   — schema_version="delta.v1" and ops[] present
        "full"    — top-level summary fields present (overview, decisions, etc.)
        "unknown" — neither pattern matches
    """
    if not isinstance(obj, dict):
        return "unknown"
    if obj.get("schema_version") == "delta.v1" and "ops" in obj:
        return "delta"
    if any(k in obj for k in ("overview", "decisions", "key_facts", "active_topics")):
        return "full"
    return "unknown"


def canonicalize_full_summary(full):
    """
    Normalize field names and types in a full summary response.

    Corrects common Gemini drift patterns:
    - name → title (topics)
    - source_message_id → source_message_ids (string → [string])
    - "text" → type-specific content field (decision/fact/task/question)
    - supersedes → supersedes_id

    Returns a deep copy with corrections applied.
    """
    full = copy.deepcopy(full)
    for section, (content_field, _) in _SECTIONS.items():
        for item in full.get(section, []):
            if "name" in item and "title" not in item:
                item["title"] = item.pop("name")
            smid = item.pop("source_message_id", None)
            smids = item.get("source_message_ids")
            if smid is not None and smids is None:
                item["source_message_ids"] = [smid]
            elif isinstance(smids, str):
                item["source_message_ids"] = [smids]
            # Map universal "text" → type-specific content field when absent
            if content_field != "text" and content_field not in item and "text" in item:
                item[content_field] = item["text"]
            # Normalize supersedes → supersedes_id
            if "supersedes" in item and "supersedes_id" not in item:
                item["supersedes_id"] = item.pop("supersedes")
    return full


def diff_full_to_ops(pre_state, full):
    """
    Produce delta ops[] by diffing a full summary against the pre-update state.

    Generates add ops for new items and status-change ops for existing items.
    Rejects protected-field rewrites (logs and skips — does not raise).

    Args:
        pre_state: Pre-update persistent summary dict
        full:      Canonicalized full summary from LLM
    Returns:
        list: Delta ops[] dicts
    """
    ops = []
    pre_idx = {
        sec: {it["id"]: it for it in pre_state.get(sec, [])}
        for sec in _SECTIONS
    }

    if full.get("overview") and full["overview"] != pre_state.get("overview", ""):
        ops.append({"op": "update_overview", "id": "overview", "text": full["overview"]})

    for section, (content_field, add_op) in _SECTIONS.items():
        pre = pre_idx[section]
        for item in full.get(section, []):
            iid = item.get("id")
            if not iid:
                continue

            if iid not in pre:
                # New item — build add op
                op = {
                    "op": add_op, "id": iid,
                    "source_message_ids": item.get("source_message_ids", []),
                }
                if content_field in item:
                    op["text"] = item[content_field]
                if section == "active_topics":
                    op["title"] = item.get("title", "")
                for f in ("status", "category", "owner", "deadline", "notes"):
                    if f in item:
                        op[f] = item[f]
                ops.append(op)
            else:
                pre_item = pre[iid]
                # Reject protected-field rewrites
                if section in _PROTECTED:
                    if item.get(content_field) != pre_item.get(content_field):
                        logger.warning(f"Protected rewrite rejected: {section} id={iid}")
                        continue
                # Status transition
                status_op = _STATUS_OPS.get(section)
                if status_op and item.get("status") != pre_item.get("status"):
                    ops.append({"op": status_op, "id": iid, "status": item.get("status")})

    return ops
