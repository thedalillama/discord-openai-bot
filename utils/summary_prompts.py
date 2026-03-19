# utils/summary_prompts.py
# Version 1.5.0
"""
Prompt construction for the summarization pipeline.

CHANGES v1.5.0: Readable text in snapshot for supersession; re-export authoring
- MODIFIED: build_prompt() snapshot now includes readable text for decisions,
  key_facts, action_items, and open_questions so the model can match existing
  IDs when emitting supersede_decision ops
- ADDED: Re-exports from summary_prompts_authoring.py for cold start pipeline

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
supersede_decision with supersedes_id matching the EXACT id from CURRENT_STATE.
- Every add_* op must cite source_message_ids using M-labels from the \
provided messages.
- Preserve filenames, paths, URLs, version numbers, identifiers, and \
numeric values exactly as they appear.
- Omit uncertain ops rather than guess.
- Prefer omitting low-value updates over producing too many ops.
- If many candidate updates exist, keep only the highest-value durable updates.

PROMOTION POLICY:
Promote ONLY durable information that is likely to matter in future \
conversations if the raw messages are not re-read.

overview (update_overview):
- Emit once when the overview is empty or needs updating.
- Write 1-2 sentences describing what the conversation is about.

participants (add_participant):
- Emit add_participant for each human who has spoken.
- Use their Discord display name as both id and text.
- Do NOT add bots as participants.

decisions (add_decision / supersede_decision):
- Explicit choices made: technology selections, approach decisions, \
policy choices.
- To supersede, use the EXACT id from CURRENT_STATE in supersedes_id.

commitments and action items (add_action_item):
- Tasks someone has agreed to do or been asked to do.

open questions (add_open_question):
- UNRESOLVED project or decision questions requiring a future answer.
- Do NOT capture: math, trivia, factual lookups, or questions already \
answered in conversation.

significant facts (add_fact):
- Durable constraints, metrics, filenames, URLs, version numbers, or \
implementation facts that create ongoing constraints.

Do NOT promote as facts:
- greetings, jokes, small talk, agreement without a decision
- transient troubleshooting, casual observations, speculative ideas
- questions the user asked the bot, low-level details

PRIORITY ORDER:
1. decision  2. action item  3. open question  4. pinned memory  5. fact

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
        "overview":      current.get("overview", ""),
        "decisions":     _snap(current.get("decisions", []),
                               ["id", "decision", "text_hash", "status"]),
        "key_facts":     _snap(current.get("key_facts", []),
                               ["id", "fact", "text_hash", "status",
                                "category"]),
        "action_items":  _snap(current.get("action_items", []),
                               ["id", "task", "text_hash", "status"]),
        "open_questions": _snap(current.get("open_questions", []),
                                ["id", "question", "status"]),
        "active_topics": _snap(current.get("active_topics", []),
                               ["id", "title", "status"]),
        "participants":  _snap(current.get("participants", []),
                               ["id", "display_name"]),
    }
    user_content = (
        "TASK:\nGiven CURRENT_STATE and NEW_MESSAGES, output ONLY delta ops.\n\n"
        f"CURRENT_STATE (read-only):\n{json.dumps(state, indent=2)}\n\n"
        f"NEW_MESSAGES:\n{labeled_text}\n\n"
        "RULES:\n"
        "- Only add/close/complete/supersede where NEW_MESSAGES provide evidence.\n"
        "- Every op must cite source_message_ids using M-labels above.\n"
        "- To supersede a decision, use the EXACT id from CURRENT_STATE.\n"
        "- Do not restate CURRENT_STATE unless emitting an op about it."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
