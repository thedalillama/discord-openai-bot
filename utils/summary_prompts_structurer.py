# utils/summary_prompts_structurer.py
# Version 1.0.0
"""
Structurer prompt for Pass 2: convert natural language minutes to JSON delta ops.

CREATED v1.0.0: Extracted from summary_prompts_authoring.py v1.7.0 (SOW v5.6.0)
"""
import json

STRUCTURER_SYSTEM_PROMPT = """\
You are a structured data extractor. Convert meeting minutes into JSON \
delta operations. Output ONLY a single JSON object matching the schema.
No markdown, no code fences, no explanations.

EXTRACTION RULES:
- Each decision line → addDecision op
- Each key fact → addFact op
- Each open action item → addActionItem op (include owner if stated)
- Each completed action item → addActionItem with status "completed"
- Each open question → addOpenQuestion op
- Each ACTIVE TOPIC (### heading + summary) → addTopic op with \
status "active". Put the heading in "title" and the summary in "text".
- Each ARCHIVED item → addTopic op with status "archived". \
Put the one-line description in "title".
- Each participant → addParticipant op
- The OVERVIEW section → updateOverview op
- Use exact text from the minutes. Do not paraphrase or invent content.
- If nothing to extract: {"schema_version":"delta.v1","mode":"incremental",\
"ops":[{"op":"noop","id":"noop"}]}

TOPIC EXAMPLES:
Minutes input:
  ### Database Decision
  The team decided on PostgreSQL after considering SQLite and Redis.
Output:
  {"op":"addTopic","id":"topic-database-decision",\
"title":"Database Decision",\
"text":"The team decided on PostgreSQL after considering SQLite and Redis.",\
"status":"active"}

Minutes input:
  - Bot interaction and testing (M1-M14)
Output:
  {"op":"addTopic","id":"topic-bot-interaction",\
"title":"Bot interaction and testing","status":"archived"}

ID GENERATION:
- Use descriptive kebab-case IDs: "decision-use-sqlite", "topic-api-design"
- Facts: "fact-[short-description]"
- Action items: "action-[short-description]"
- Questions: "question-[short-description]"
- Topics: "topic-[short-description]"

For items matching existing CURRENT_STATE entries by content, do not \
re-add them. Only emit ops for new or changed items."""


def build_structurer_prompt(minutes_text, current_json=None):
    """
    Build [system, user] for Pass 2 (JSON structuring).

    Args:
        minutes_text: Natural language minutes from Pass 1.
        current_json: Existing structured summary dict, or None.

    Returns:
        list: [{role: system, content: ...}, {role: user, content: ...}]
    """
    user_content = f"MINUTES TO STRUCTURE:\n{minutes_text}"

    if current_json:
        def _snap(items, fields):
            return [{f: it[f] for f in fields if f in it} for it in items]

        state = {
            "decisions":      _snap(current_json.get("decisions", []),
                                    ["id", "decision", "status"]),
            "key_facts":      _snap(current_json.get("key_facts", []),
                                    ["id", "fact", "status"]),
            "action_items":   _snap(current_json.get("action_items", []),
                                    ["id", "task", "status", "owner"]),
            "open_questions": _snap(current_json.get("open_questions", []),
                                    ["id", "question", "status"]),
            "active_topics":  _snap(current_json.get("active_topics", []),
                                    ["id", "title", "status"]),
            "participants":   _snap(current_json.get("participants", []),
                                    ["id", "display_name"]),
        }
        user_content += (
            f"\n\nCURRENT_STATE (do not re-add existing items):\n"
            f"{json.dumps(state, indent=2)}"
        )

    return [
        {"role": "system", "content": STRUCTURER_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
