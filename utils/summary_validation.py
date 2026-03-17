# utils/summary_validation.py
# Version 1.1.0
"""
Domain validation for delta ops (Layer 3 of three-layer enforcement).

CHANGES v1.1.0: Reject content-empty add ops
- ADDED: check 0 — add_* ops with empty text field rejected before source check

CREATED v1.0.0: SOW v3.2.0
- ADDED: validate_domain() — filters ops to those passing all domain checks:
  source ID presence, duplicate ADD IDs within delta, ADD of already-existing
  IDs in pre_state, and status transition validity

Invalid ops are excluded and logged. Pre-update summary is not modified.
Valid ops are returned as a list.
"""
from utils.logging_utils import get_logger

logger = get_logger('summary_validation')

_ADD_OPS = frozenset({
    "add_fact", "add_decision", "add_topic", "add_action_item",
    "add_open_question", "add_pinned_memory", "add_participant",
})
# Ops that require a non-empty text field to be meaningful
_CONTENT_OPS = frozenset({
    "add_fact", "add_decision", "add_action_item", "add_open_question", "add_pinned_memory",
})
_VALID_STATUSES = {
    "active_topics":  {"active", "resolved", "archived"},
    "action_items":   {"open", "in_progress", "completed", "cancelled"},
    "open_questions": {"open", "answered", "closed"},
    "decisions":      {"active", "superseded"},
}
_STATUS_OP_SECTION = {
    "update_topic_status":  "active_topics",
    "complete_action_item": "action_items",
    "close_open_question":  "open_questions",
}
_SECTION_FOR_ADD = {
    "add_fact":          "key_facts",
    "add_decision":      "decisions",
    "add_topic":         "active_topics",
    "add_action_item":   "action_items",
    "add_open_question": "open_questions",
    "add_pinned_memory": "pinned_memory",
}


def validate_domain(delta, pre_state, context_labels):
    """
    Filter delta ops to only those passing domain validation.

    Checks (in order):
    1. add_* ops cite only M-labels present in context_labels
    2. No duplicate ADD IDs within this delta
    3. No ADD of an ID already in pre_state
    4. Status transitions are valid per _VALID_STATUSES

    Args:
        delta:          Parsed delta dict with ops[]
        pre_state:      Pre-update summary dict (read-only)
        context_labels: Set of valid M-label strings e.g. {"M1", "M2", ...}
    Returns:
        list: Valid ops only
    """
    valid = []
    seen_add_ids = set()
    pre_ids = {
        sec: {it["id"] for it in pre_state.get(sec, [])}
        for sec in ("decisions", "key_facts", "action_items",
                    "open_questions", "active_topics", "pinned_memory")
    }

    for op in delta.get("ops", []):
        op_type = op.get("op", "")
        op_id   = op.get("id", "")

        if op_type == "noop":
            valid.append(op)
            continue

        if op_type in _ADD_OPS:
            # 0. Content check — reject ops with empty text
            if op_type in _CONTENT_OPS and not op.get("text", "").strip():
                logger.warning(f"{op_type} id={op_id}: rejected — empty text field")
                continue

            # 1. Source ID check
            bad = [m for m in op.get("source_message_ids", []) if m not in context_labels]
            if bad:
                logger.warning(f"{op_type} id={op_id}: invalid source_message_ids {bad}")
                continue

            # 2. Within-delta duplicate check
            if op_id in seen_add_ids:
                logger.warning(f"Duplicate ADD in delta rejected: {op_type} id={op_id}")
                continue
            seen_add_ids.add(op_id)

            # 3. Pre-state duplicate check
            section = _SECTION_FOR_ADD.get(op_type)
            if section and op_id in pre_ids.get(section, set()):
                logger.warning(f"ADD rejected: {op_id} already exists in {section}")
                continue

        # 4. Status transition check
        if op_type in _STATUS_OP_SECTION:
            section = _STATUS_OP_SECTION[op_type]
            status  = op.get("status")
            if status and status not in _VALID_STATUSES.get(section, set()):
                logger.warning(f"Invalid status {status!r} for {op_type} id={op_id}")
                continue

        valid.append(op)

    rejected = len(delta.get("ops", [])) - len(valid)
    if rejected:
        logger.info(f"Domain validation: {rejected} op(s) rejected, {len(valid)} accepted")
    return valid
