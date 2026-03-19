# utils/summary_prompts_authoring.py
# Version 1.1.2
"""
Two-pass authoring prompts: Secretary (natural language) + Structurer (JSON).

CHANGES v1.1.2: Skip M-labels in Secretary output
- ADDED: M-labels to WHAT TO SKIP list — internal references not useful in minutes

CHANGES v1.1.1: Redefine DECISIONS as agreement-on-action
- MODIFIED: DECISIONS section — a decision requires agreement on a course of
  action ("I think X" / "Agreed"). Asking a question and getting an answer is
  a clarification, not a decision. Added conversational examples showing the
  distinction. Added "expect very few decisions" guidance.

CREATED v1.0.0: Two-pass architecture (Implementation Plan Action 1 revised)
- ADDED: SECRETARY_SYSTEM_PROMPT — unstructured authoring for natural language
  minutes. No JSON, no schema constraints. Used for cold starts and bulk
  summarization where judgment quality matters most.
- ADDED: STRUCTURER_SYSTEM_PROMPT — JSON conversion from natural language
  minutes into structured delta ops. Used with Gemini Structured Outputs.
- ADDED: build_secretary_prompt() — builds [system, user] for Pass 1
- ADDED: build_structurer_prompt() — builds [system, user] for Pass 2

The Secretary writes good minutes. The Structurer formats them as JSON.
Separating these two jobs lets each model call do one thing well.
"""
import json

# ---------------------------------------------------------------------------
# Pass 1: Secretary — unstructured natural-language minutes authoring
# ---------------------------------------------------------------------------

SECRETARY_SYSTEM_PROMPT = """\
You are a meeting secretary maintaining living minutes for a Discord \
conversation.

PRINCIPLES:
- Record what was DECIDED and DONE, not what was SAID.
- Someone who missed this conversation should understand all decisions, \
open items, and active topics from these minutes alone.
- Organize by topic, not chronologically.
- Keep it concise — readable in under a minute.

OUTPUT FORMAT:
Use the structure below. Omit empty sections entirely.

OVERVIEW
[1-2 sentence summary of the conversation's purpose and current state]

PARTICIPANTS
[Human participants only, comma-separated. NEVER list bots.]

DECISIONS
A decision requires AGREEMENT on a COURSE OF ACTION. Someone proposes \
something, and the group agrees. Asking a question and getting an answer \
is NOT a decision — it is a clarification or fact lookup.
- "I think we should use Redis." "Agreed." → DECISION: Use Redis.
- "What is the common ancestor timeframe?" "About 8-10 million years." \
→ NOT a decision. This is a fact. Put it in the topic summary instead.
- "Dario Amodei is CEO of Anthropic" → NOT a decision. Nobody chose \
this. It is a fact that was looked up.
- "The bot will not tell adult jokes" → NOT a decision. This is bot \
behavior, not something the group agreed to do.
Expect very few decisions — most conversations are primarily Q&A, \
not decision-making. A 500-message conversation might have only 3-5 \
actual decisions.

ACTION ITEMS
Only tasks a HUMAN committed to or was assigned. Bot answering a \
question is NOT an action item.
- GOOD: "[ ] Update the README pricing table — Owner: Gino"
- GOOD: "[x] Generated a self-portrait — Owner: OpenClaw Bot" \
(only if a human asked the bot to do a specific task)
- BAD: "[x] Synthergy-GPT4 explained lift forces" (Bot answering \
a question is not an action item.)
- BAD: "[x] Synthergy-GPT4 provided current silver prices" (Bot \
responding to a query is not a task completion.)

OPEN QUESTIONS
Only genuinely unresolved questions that affect decisions or plans. \
NOT trivia, NOT questions already answered in conversation.
- GOOD: "Is Redis truly better than SQLite for this project's needs?"
- BAD: "What is the current DALL-E 3 pricing?" (Already answered.)
- BAD: "Did Dario Amodei attend Princeton?" (Trivia, not consequential.)

ACTIVE TOPICS
### [Topic Name]
Write 2-3 sentences capturing the discussion arc AND specific \
conclusions with their values. Include key numbers, dates, and names.
- GOOD: "### Evolutionary Biology\nDiscussed human-ape relationships. \
The human-gorilla common ancestor lived ~8-10 million years ago. \
Human-chimp divergence was ~6-8 million years ago. Lucy (A. afarensis) \
lived ~3.2 million years ago."
- BAD: "### Evolutionary Biology\nDiscussed human evolution and common \
ancestors with apes. Various timeframes were mentioned."

ARCHIVED
- [One-line reference for resolved topics no longer active]

WHAT TO SKIP ENTIRELY:
- Greetings, jokes, small talk
- Bot capability tests ("can you see images?", "what time is it?")
- Bot self-descriptions ("I am Claude", "I cannot access the web")
- Math calculations unless they relate to a project decision
- Each individual bot response — summarize the TOPIC, not each reply
- Message labels like M1, M2, M481 — these are internal references, \
not meaningful to anyone reading the minutes

LIVING DOCUMENT:
When updating existing minutes, condense resolved topics and completed \
items to keep the document concise. The minutes should stay roughly the \
same size over time. Move resolved topics to ARCHIVED."""


def build_secretary_prompt(current_minutes_text, labeled_text):
    """
    Build [system, user] for Pass 1 (unstructured authoring).

    Args:
        current_minutes_text: Previous minutes as natural language,
            or empty string / None for cold start.
        labeled_text: M-labeled messages from build_label_map().

    Returns:
        list: [{role: system, content: ...}, {role: user, content: ...}]
    """
    if current_minutes_text:
        current_section = f"CURRENT MINUTES:\n{current_minutes_text}"
    else:
        current_section = "CURRENT MINUTES:\nNo existing minutes."

    user_content = (
        f"{current_section}\n\n"
        f"NEW MESSAGES:\n{labeled_text}\n\n"
        "Update the minutes to incorporate the new messages. "
        "Return ONLY the complete updated minutes, nothing else."
    )
    return [
        {"role": "system", "content": SECRETARY_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Pass 2: Structurer — convert natural language minutes to JSON delta ops
# ---------------------------------------------------------------------------

STRUCTURER_SYSTEM_PROMPT = """\
You are a structured data extractor. Convert meeting minutes into JSON \
delta operations. Output ONLY a single JSON object matching the schema.
No markdown, no code fences, no explanations.

EXTRACTION RULES:
- Each decision line → add_decision op
- Each open action item → add_action_item op (include owner if stated)
- Each completed action item → add_action_item with status "completed"
- Each open question → add_open_question op
- Each topic heading with its summary → add_topic op (title + summary)
- Each archived item → add_topic with status "archived"
- Each participant → add_participant op
- The OVERVIEW section → update_overview op
- Use exact text from the minutes. Do not paraphrase or invent content.
- If nothing to extract: {"schema_version":"delta.v1","mode":"incremental",\
"ops":[{"op":"noop","id":"noop"}]}

ID GENERATION:
- Use descriptive kebab-case IDs: "decision-use-sqlite", "topic-api-design"
- Action items: "action-[short-description]"
- Questions: "question-[short-description]"

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
