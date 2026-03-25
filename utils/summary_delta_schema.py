# utils/summary_delta_schema.py
# Version 1.0.0
"""
Discriminated union delta schema for Gemini Structured Outputs.

CREATED v1.0.0: anyOf schema to fix Gemini skipping add_topic ops
- Uses anyOf discriminated union: each op type is a separate variant
  with only its required fields. Eliminates the optional-field problem
  that causes Gemini's FSM constrained decoder to skip complex ops.
- Uses camelCase enum values (addTopic vs add_topic) for higher token
  probability in the decoder. translate_ops() maps back to snake_case.
- Uses propertyOrdering with op first so the decoder commits to the
  operation type before generating dependent fields.
- Designed for responseJsonSchema (JSON Schema format), not
  responseSchema (OpenAPI format), for better anyOf support.

Research basis: "Gemini Structured Outputs and Complex Enum Schemas:
Systematic Underperformance Analysis" — constrained decoding creates
measurable bias in enum selection; flat enum + optional fields is the
worst-case architecture for Gemini's decoder.
"""

# Map camelCase op names back to snake_case for apply_ops()
_ENUM_MAP = {
    "addTopic": "add_topic",
    "addFact": "add_fact",
    "addDecision": "add_decision",
    "addActionItem": "add_action_item",
    "addOpenQuestion": "add_open_question",
    "addPinnedMemory": "add_pinned_memory",
    "updateOverview": "update_overview",
    "updateTopicStatus": "update_topic_status",
    "completeActionItem": "complete_action_item",
    "closeOpenQuestion": "close_open_question",
    "supersedeDecision": "supersede_decision",
    "addParticipant": "add_participant",
    "noop": "noop",
}


def translate_ops(delta):
    """Translate camelCase op names to snake_case for apply_ops().
    Modifies delta in place and returns it."""
    for op in delta.get("ops", []):
        raw = op.get("op", "")
        op["op"] = _ENUM_MAP.get(raw, raw)
    return delta


def _variant(op_enum, required, properties):
    """Build one anyOf variant with propertyOrdering."""
    props = {"op": {"type": "string", "enum": [op_enum]}}
    props.update(properties)
    ordering = [k for k in props]
    return {
        "type": "object",
        "required": required,
        "properties": props,
        "propertyOrdering": ordering,
    }


# Common property definitions
_ID = {"type": "string"}
_TEXT = {"type": "string"}
_TITLE = {"type": "string"}
_STATUS = {"type": "string"}
_OWNER = {"type": "string"}
_DEADLINE = {"type": "string"}
_CATEGORY = {"type": "string"}
_SRC_IDS = {"type": "array", "items": {"type": "string"}}
_SUP_ID = {"type": "string"}


STRUCTURER_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "mode", "ops"],
    "propertyOrdering": ["schema_version", "mode", "ops"],
    "properties": {
        "schema_version": {"type": "string", "enum": ["delta.v1"]},
        "mode": {"type": "string", "enum": ["incremental"]},
        "ops": {
            "type": "array",
            "items": {
                "anyOf": [
                    _variant("addTopic",
                        ["op", "id", "title", "status"],
                        {"id": _ID, "title": _TITLE,
                         "text": _TEXT, "status": _STATUS,
                         "source_message_ids": _SRC_IDS}),
                    _variant("addDecision",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT,
                         "status": _STATUS,
                         "source_message_ids": _SRC_IDS}),
                    _variant("addFact",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT,
                         "category": _CATEGORY,
                         "source_message_ids": _SRC_IDS}),
                    _variant("addActionItem",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT,
                         "owner": _OWNER, "deadline": _DEADLINE,
                         "source_message_ids": _SRC_IDS}),
                    _variant("addOpenQuestion",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT,
                         "source_message_ids": _SRC_IDS}),
                    _variant("addPinnedMemory",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT,
                         "source_message_ids": _SRC_IDS}),
                    _variant("updateOverview",
                        ["op", "id", "text"],
                        {"id": _ID, "text": _TEXT}),
                    _variant("addParticipant",
                        ["op", "id"],
                        {"id": _ID, "text": _TEXT}),
                    _variant("supersedeDecision",
                        ["op", "id", "supersedes_id"],
                        {"id": _ID, "text": _TEXT,
                         "supersedes_id": _SUP_ID,
                         "source_message_ids": _SRC_IDS}),
                    _variant("updateTopicStatus",
                        ["op", "id", "status"],
                        {"id": _ID, "status": _STATUS}),
                    _variant("completeActionItem",
                        ["op", "id"],
                        {"id": _ID}),
                    _variant("closeOpenQuestion",
                        ["op", "id"],
                        {"id": _ID}),
                    _variant("noop",
                        ["op", "id"],
                        {"id": _ID}),
                ],
            },
        },
    },
}
