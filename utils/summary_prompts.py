# utils/summary_prompts.py
# Version 1.3.0
"""
Prompt construction for the summarization pipeline.

CHANGES v1.3.0: Fix BOT label format; add BOT message guidance to prompt
- MODIFIED: build_label_map() adds [BOT] after the label bracket (not inside it)
  so source_message_ids stay as plain M-labels (M3 not M3/BOT)
- ADDED: BOT MESSAGE HANDLING section in SYSTEM_PROMPT explaining how to treat
  bot responses — context only, not participant statements or capability facts

CHANGES v1.2.0: Fix open_question definition; add overview and participant guidance
- ADDED: explicit definition of open_question — unresolved project/decision
  question only; conversational Q&A that was asked and answered is NOT one
- ADDED: update_overview and add_participant to PROMOTION POLICY
- ADDED: overview guidance — short 1-2 sentence summary of what was discussed

CHANGES v1.1.0: Durable-state promotion policy
- REPLACED: broad "Promote: facts" rule → detailed PROMOTION POLICY with
  high/low priority guidance, PRIORITY ORDER, and BUDGET constraints
- ADDED: "Your job is to preserve only durable conversational state" framing
- REMOVED: "config values" from promote list

CREATED v1.0.0: Extracted from summarizer.py (SOW v3.2.0)
- ADDED: SYSTEM_PROMPT — SOW-specified strict instruction for Gemini
- ADDED: build_label_map() — assign M1/M2/M3 labels to messages
- ADDED: build_prompt() — build [system, user] message list from SOW template
  (hash-only CURRENT_STATE snapshot + M-labeled messages + RULES)
"""
import json

SYSTEM_PROMPT = """\
You are a summarizer. Output ONLY a single JSON object matching the schema.
No markdown, no code fences, no explanations, no extra keys.
Return ONLY incremental delta ops in ops[]. Never return a full summary.
If nothing to update: {"schema_version":"delta.v1","mode":"incremental","ops":[{"op":"noop","id":"noop"}]}

Your job is not to capture everything said.
Your job is to preserve only durable conversational state.

RULES:
- Never modify protected text in-place. To change a decision, emit supersede_decision.
- Every add_* op must cite source_message_ids using M-labels from the provided messages.
- Preserve filenames, paths, URLs, version numbers, identifiers, and numeric values exactly as they appear.
- Omit uncertain ops rather than guess.
- Prefer omitting low-value updates over producing too many ops.
- If many candidate updates exist, keep only the highest-value durable updates.

PROMOTION POLICY:
Promote ONLY durable information that is likely to matter in future conversations if the raw messages are not re-read.

overview (update_overview):
- Emit once when the overview is empty or needs updating.
- Write 1-2 sentences describing what the conversation is about and who is participating.
- Example: "Testing session for the OpenClaw Discord bot. absolutebeginner is exploring bot capabilities and discussing AI providers."

participants (add_participant):
- Emit add_participant for each human who has spoken.
- Use their Discord display name as both id and text.
- Do NOT add bots as participants.

decisions (add_decision / supersede_decision):
- Explicit choices made: technology selections, approach decisions, policy choices.

commitments and action items (add_action_item):
- Tasks someone has agreed to do or been asked to do.

open questions (add_open_question):
- An open question is an UNRESOLVED project or decision question that requires a future answer.
- It must be about something consequential that affects the project, plans, or decisions.
- Do NOT capture: math problems, trivia, factual lookups, conversational questions, or any
  question that was clearly asked and answered in the same conversation.
- Example of a valid open question: "Should we use PostgreSQL or SQLite?"
- Example of NOT an open question: "What is 45 * 78?", "Who won the Super Bowl?", "What time is it in London?"

significant facts (add_fact):
- A significant fact worth retaining long-term must be one of:
  - a durable constraint or requirement
  - a concrete commitment or obligation
  - a metric, reference, filename, path, URL, version number, or identifier that will matter later
  - a durable user or team preference or personal detail shared intentionally
  - an implementation fact that creates an ongoing constraint or affects future design decisions

Do NOT promote as facts:
- greetings, acknowledgments, jokes, small talk
- agreement/disagreement without a resulting decision
- transient troubleshooting chatter, casual observations
- restatements of what someone just said
- speculative ideas that were not adopted
- questions the user asked the bot (even if interesting)
- low-level implementation details unless they create a durable constraint

PRIORITY ORDER:
When the same information could fit multiple categories, prefer this order:
1. decision
2. commitment / action item
3. open question (only if genuinely unresolved and consequential)
4. pinned memory
5. significant fact

BOT MESSAGE HANDLING:
Messages labeled [Mn/BOT] are AI-generated responses. Use them to:
- Understand what questions were answered (do not mark those as open questions)
- Extract facts that were established or confirmed in the exchange
Do NOT:
- Add bot authors as participants
- Capture bot capability descriptions as facts ("the bot can do X")
- Treat bot responses as human decisions or commitments

BUDGET:
- Keep ops minimal.
- Prefer 0-3 new fact-style additions per batch unless the batch contains unusually important durable information.
- Do not emit many similar add_fact ops.
- Do not emit open questions for every question asked — only genuinely unresolved consequential ones.
- If output would become large, include only the most important durable updates and omit the rest.

FORBIDDEN (full summary — do not return this format):
{"schema_version":"1.0","overview":"...","decisions":[...]}"""


def build_label_map(messages):
    """Assign M1/M2/... labels. Bot-authored messages get a /BOT suffix on the label.
    Returns (label_to_id dict, labeled_text string)."""
    label_to_id = {}
    lines = []
    for i, msg in enumerate(messages, 1):
        label = f"M{i}"
        label_to_id[label] = msg.id
        ts = msg.created_at[:16] if msg.created_at else ""
        bot_marker = " [BOT]" if msg.is_bot_author else ""
        lines.append(f"[{label}]{bot_marker} {msg.author_name} ({ts}): {msg.content}")
    return label_to_id, "\n".join(lines)


def build_prompt(current, labeled_text):
    """
    Build [system, user] message list using SOW template.

    CURRENT_STATE is sent as a hash-only snapshot (id, text_hash, status) so the
    model cannot see or rewrite protected field content.
    """
    def _snap(items, fields):
        return [{f: it[f] for f in fields if f in it} for it in items]

    state = {
        "overview":      current.get("overview", ""),
        "decisions":     _snap(current.get("decisions", []),      ["id", "text_hash", "status"]),
        "key_facts":     _snap(current.get("key_facts", []),      ["id", "text_hash", "status", "category"]),
        "action_items":  _snap(current.get("action_items", []),   ["id", "text_hash", "status"]),
        "open_questions":_snap(current.get("open_questions", []), ["id", "status"]),
        "active_topics": _snap(current.get("active_topics", []),  ["id", "title", "status"]),
        "participants":  _snap(current.get("participants", []),   ["id", "display_name"]),
    }
    user_content = (
        "TASK:\nGiven CURRENT_STATE and NEW_MESSAGES, output ONLY delta ops.\n\n"
        f"CURRENT_STATE (read-only):\n{json.dumps(state, indent=2)}\n\n"
        f"NEW_MESSAGES:\n{labeled_text}\n\n"
        "RULES:\n"
        "- Only add/close/complete/supersede where NEW_MESSAGES provide evidence.\n"
        "- Every op adding content must cite source_message_ids using M-labels above.\n"
        "- Do not restate CURRENT_STATE unless emitting an op about it."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
