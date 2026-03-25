# utils/summary_prompts.py
# Version 1.6.0
"""
Prompt construction for the summarization pipeline.

CHANGES v1.6.0: camelCase op names in incremental prompt (SOW v3.5.0)
- MODIFIED: SYSTEM_PROMPT uses camelCase ops (addDecision, supersedeDecision,
  addTopic, etc.) to match the anyOf STRUCTURER_SCHEMA
- ADDED: addTopic guidance in PROMOTION POLICY

CHANGES v1.5.0: Readable text in snapshot for supersession; re-export authoring
CHANGES v1.3.0: Fix BOT label format; add BOT message guidance
CHANGES v1.2.0: Fix open_question definition; add overview guidance
CHANGES v1.1.0: Durable-state promotion policy
CREATED v1.0.0: Extracted from summarizer.py (SOW v3.2.0)
"""
import json

# Re-export authoring prompts for cold start pipeline
from utils.summary_prompts_authoring import (  # noqa: F401
    build_secretary_prompt,
    build_structurer_prompt,
)

SYSTEM_PROMPT = """\
You are a summarizer. Output ONLY a single JSON object matching the schema.
No markdown, no code fences, no explanations, no extra keys.
Return ONLY incremental delta ops in ops[]. Never return a full summary.
If nothing to update: {"schema_version":"delta.v1","mode":"incremental",\
"ops":[{"op":"noop","id":"noop"}]}

Your job is not to capture everything said.
Your job is to preserve only durable conversational state.

RULES:
- Never modify protected text in-place. To change a decision, emit \
supersedeDecision with supersedes_id matching the EXACT id from CURRENT_STATE.
- Every add op must cite source_message_ids using M-labels from the \
provided messages.
- Preserve filenames, paths, URLs, version numbers, identifiers, and \
numeric values exactly as they appear.
- Omit uncertain ops rather than guess.
- Prefer omitting low-value updates over producing too many ops.
- If many candidate updates exist, keep only the highest-value durable updates.

PROMOTION POLICY:
Promote ONLY durable information that is likely to matter in future \
conversations if the raw messages are not re-read.

overview (updateOverview):
- Emit once when the overview is empty or needs updating.
- Write 1-2 sentences describing what the conversation is about.

participants (addParticipant):
- Emit addParticipant for each human who has spoken.
- Use their Discord display name as both id and text.
- Do NOT add bots as participants.

decisions (addDecision / supersedeDecision):
- Explicit choices made: technology selections, approach decisions, \
policy choices.
- To supersede, use the EXACT id from CURRENT_STATE in supersedes_id.

commitments and action items (addActionItem):
- Tasks someone has agreed to do or been asked to do.

open questions (addOpenQuestion):
- UNRESOLVED project or decision questions requiring a future answer.
- Do NOT capture: math, trivia, factual lookups, or questions already \
answered in conversation.

significant facts (addFact):
- Durable constraints, metrics, filenames, URLs, version numbers, or \
implementation facts that create ongoing constraints.

topics (addTopic):
- Ongoing discussions worth tracking. Include title and text summary.
- Set status "active" for current topics, "archived" for resolved.

Do NOT promote as facts:
- greetings, jokes, small talk, agreement without a decision
- transient troubleshooting, casual observations, speculative ideas
- questions the user asked the bot, low-level details

PRIORITY ORDER:
1. decision  2. action item  3. open question  4. topic  5. fact

BOT MESSAGE HANDLING:
Messages labeled [BOT] are AI-generated responses.
Use them to understand what was answered. Do NOT:
- Add bot authors as participants
- Capture bot capability descriptions as facts
- Treat bot responses as human decisions

BUDGET:
- Keep ops minimal. Prefer 0-3 new additions per batch.
- Do not emit open questions for every question asked.
- If output would be large, keep only the most important updates.

FORBIDDEN (full summary — do not return this format):
{"schema_version":"1.0","overview":"...","decisions":[...]}"""


def build_label_map(messages):
    """Assign M1/M2/... labels. Bot messages get [BOT] suffix.
    Returns (label_to_id dict, labeled_text string)."""
    label_to_id = {}
    lines = []
    for i, msg in enumerate(messages, 1):
        label = f"M{i}"
        label_to_id[label] = msg.id
        ts = msg.created_at[:16] if msg.created_at else ""
        bot_marker = " [BOT]" if msg.is_bot_author else ""
        lines.append(
            f"[{label}]{bot_marker} {msg.author_name} ({ts}): "
            f"{msg.content}")
    return label_to_id, "\n".join(lines)


def build_prompt(current, labeled_text):
    """Build [system, user] message list for incremental delta ops.

    CURRENT_STATE includes readable text so the model can match existing
    IDs when emitting supersede ops. Hash protection still enforced at
    the apply_ops layer."""
    def _snap(items, fields):
        return [{f: it[f] for f in fields if f in it} for it in items]

    state = {
        "decisions":      _snap(current.get("decisions", []),
                                ["id", "decision", "status"]),
        "key_facts":      _snap(current.get("key_facts", []),
                                ["id", "fact", "status"]),
        "action_items":   _snap(current.get("action_items", []),
                                ["id", "task", "status", "owner"]),
        "open_questions": _snap(current.get("open_questions", []),
                                ["id", "question", "status"]),
        "active_topics":  _snap(current.get("active_topics", []),
                                ["id", "title", "status"]),
        "participants":   _snap(current.get("participants", []),
                                ["id", "display_name"]),
    }
    user_content = (
        f"CURRENT_STATE:\n{json.dumps(state, indent=2)}\n\n"
        f"NEW MESSAGES:\n{labeled_text}\n\n"
        "Emit delta ops for durable new information only."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
