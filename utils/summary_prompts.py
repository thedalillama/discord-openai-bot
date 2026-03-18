# utils/summary_prompts.py
# Version 1.5.0
"""
Prompt construction for the summarization pipeline.

CHANGES v1.5.0: Two-pass architecture — Secretary + Structurer
- ADDED: summary_prompts_authoring.py — Secretary and Structurer prompts
  for the two-pass authoring pipeline (Pass 1: natural language minutes,
  Pass 2: JSON structuring). New file to stay within 250-line limit.
- REVISED: SYSTEM_PROMPT — meeting secretary framing for incremental delta
  updates (Batch 2+ maintenance path). Readable text now exposed in snapshot.
- REVISED: build_prompt() — exposes decision/fact/action text alongside
  hashes so the model can recognize supersession and completion.
- RETAINED: build_label_map() — unchanged

CHANGES v1.4.0: Meeting minutes philosophy
CHANGES v1.3.0: Fix BOT label format; add BOT message guidance
CHANGES v1.2.0: Fix open_question definition; overview/participant guidance
CHANGES v1.1.0: Durable-state promotion policy
CREATED v1.0.0: Extracted from summarizer.py (SOW v3.2.0)
"""
import json

# Re-export authoring prompts for convenient single-module access
from utils.summary_prompts_authoring import (  # noqa: F401
    SECRETARY_SYSTEM_PROMPT,
    STRUCTURER_SYSTEM_PROMPT,
    build_secretary_prompt,
    build_structurer_prompt,
)

# ---------------------------------------------------------------------------
# Incremental maintenance: delta ops prompt (Batch 2+)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a meeting secretary maintaining structured minutes for a Discord \
conversation. Output ONLY a single JSON object matching the schema.
No markdown, no code fences, no explanations, no extra keys.
Return ONLY incremental delta ops in ops[]. Never return a full summary.
If nothing to update: {"schema_version":"delta.v1","mode":"incremental",\
"ops":[{"op":"noop","id":"noop"}]}

ROLE:
You maintain structured minutes that evolve as the conversation unfolds.
Each call gives you the current minutes plus a small batch of new messages.
Record what was DECIDED and DONE, not what was SAID.

PROTECTION RULES:
- Never modify protected text in-place. To change a decision, emit \
supersede_decision with supersedes_id pointing at the prior decision.
- Every add_* op must cite source_message_ids using M-labels.
- Preserve filenames, paths, URLs, version numbers exactly.
- Omit uncertain ops rather than guess.

WHAT TO CAPTURE (priority order):
1. decisions  2. action items  3. open questions (genuinely unresolved only)
4. topics with narrative summaries  5. key facts (durable constraints only)
6. participants (humans only)  7. overview updates

WHAT TO SKIP:
- Greetings, jokes, trivia, bot capability tests, math, general knowledge
- Questions asked and answered in the same conversation
- Bot capabilities, transient observations, speculative ideas not adopted

FORBIDDEN (full summary — do not return this format):
{"schema_version":"1.0","overview":"...","decisions":[...]}"""


def build_label_map(messages):
    """Assign M1/M2/... labels. Bot-authored messages get a [BOT] marker.
    Returns (label_to_id dict, labeled_text string)."""
    label_to_id = {}
    lines = []
    for i, msg in enumerate(messages, 1):
        label = f"M{i}"
        label_to_id[label] = msg.id
        ts = msg.created_at[:16] if msg.created_at else ""
        bot_marker = " [BOT]" if msg.is_bot_author else ""
        lines.append(
            f"[{label}]{bot_marker} {msg.author_name} ({ts}): {msg.content}"
        )
    return label_to_id, "\n".join(lines)


def build_prompt(current, labeled_text):
    """
    Build [system, user] for incremental delta updates (Batch 2+).

    Shows full readable text for decisions/facts/actions so the model
    can recognize supersession and completion. Hash verification still
    happens server-side in apply_ops().
    """
    def _snap(items, fields):
        return [{f: it[f] for f in fields if f in it} for it in items]

    state = {
        "overview":       current.get("overview", ""),
        "decisions":      _snap(current.get("decisions", []),
                                ["id", "decision", "text_hash", "status"]),
        "key_facts":      _snap(current.get("key_facts", []),
                                ["id", "fact", "text_hash", "status",
                                 "category"]),
        "action_items":   _snap(current.get("action_items", []),
                                ["id", "task", "text_hash", "status",
                                 "owner"]),
        "open_questions": _snap(current.get("open_questions", []),
                                ["id", "question", "status"]),
        "active_topics":  _snap(current.get("active_topics", []),
                                ["id", "title", "status", "summary"]),
        "participants":   _snap(current.get("participants", []),
                                ["id", "display_name"]),
    }

    total_items = sum(
        len(current.get(k, []))
        for k in ["decisions", "key_facts", "action_items",
                   "open_questions", "active_topics"]
    )

    user_content = (
        "TASK:\n"
        "Update the meeting minutes. Given CURRENT_MINUTES and\n"
        "NEW_MESSAGES, emit delta ops to integrate new information.\n\n"
        f"CURRENT_MINUTES ({total_items} items):\n"
        f"{json.dumps(state, indent=2)}\n\n"
        f"NEW_MESSAGES:\n{labeled_text}\n\n"
        "RULES:\n"
        "- Only emit ops where NEW_MESSAGES provide clear evidence.\n"
        "- Cite source_message_ids using M-labels from above.\n"
        "- Group new information under existing topics when relevant.\n"
        "- Do not restate CURRENT_MINUTES unless emitting an op.\n"
        "- If the minutes have many items, prefer updating existing\n"
        "  topics over adding new standalone facts."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
