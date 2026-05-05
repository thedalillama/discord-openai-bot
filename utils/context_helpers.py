# utils/context_helpers.py
# Version 1.2.0
"""
Helper functions for context assembly (SOW v7.0.0 M1).
Extracted from context_manager.py to respect the 250-line limit.

CHANGES v1.2.0: _FOCUS_INSTRUCTION appended to information-query system prompts
  to prevent non-sequitur context injection (NON_SEQUITUR_INSTRUCTION_HANDOFF).
CHANGES v1.1.0: build_system_prompt() — assembles system prompt from context
  components; handles conversational/author-filter/information branching so
  context_manager.py has a single call site (SOW v7.6.0).
CREATED v1.0.0: _load_summary, read_control_file, _merge_dedup_sort,
  _trim_to_budget, _format_as_turn.
"""
import os
from config import CONTROL_FILE_PATH
from utils.logging_utils import get_logger

logger = get_logger('context_helpers')

_control_cache = {}

_FOCUS_INSTRUCTION = (
    "IMPORTANT: Respond only to the user's current message. "
    "Do not introduce topics from the context unless the user "
    "explicitly asks about them. If the user's message is a "
    "joke, greeting, or casual remark, respond in kind without "
    "forcing facts into your reply. If you cannot connect the "
    "user's message to the context, respond naturally without "
    "claiming the context is relevant. Do not address questions "
    "from earlier in the conversation unless the user repeats "
    "them now."
)


def _load_summary(channel_id):
    """Load channel summary dict. Returns None if not found."""
    import json
    try:
        from utils.summary_store import get_channel_summary
        raw, _ = get_channel_summary(channel_id)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Failed to load summary ch:{channel_id}: {e}")
        return None


def read_control_file():
    """Read control file, return contents or empty string.
    Cached with mtime check — re-read only when file changes.
    """
    path = CONTROL_FILE_PATH
    if not os.path.exists(path):
        return ""
    try:
        mtime = os.path.getmtime(path)
        if mtime == _control_cache.get("mtime"):
            return _control_cache["content"]
        with open(path) as f:
            content = f.read().strip()
        _control_cache["mtime"] = mtime
        _control_cache["content"] = content
        return content
    except Exception as e:
        logger.warning(f"Control file read failed: {e}")
        return ""


def _merge_dedup_sort(a, b):
    """Merge two message lists, dedup by id, sort chronologically."""
    seen, result = set(), []
    for msg in sorted(a + b, key=lambda m: m.get("created_at") or ""):
        if msg["id"] not in seen:
            seen.add(msg["id"])
            result.append(msg)
    return result


def _trim_to_budget(msgs, max_tokens):
    """Trim oldest messages to fit within max_tokens.
    Returns (block, tokens_used).
    """
    from utils.context_manager import estimate_tokens, MSG_OVERHEAD
    block, used = [], 0
    for msg in reversed(msgs):
        t = estimate_tokens(msg["content"]) + MSG_OVERHEAD
        if used + t > max_tokens:
            break
        block.append(msg)
        used += t
    block.reverse()
    return block, used


def _format_as_turn(msg):
    """Format a DB message dict as an API message turn."""
    role = "assistant" if msg.get("is_bot") else "user"
    date_str = (msg.get("created_at") or "")[:10]
    content = f"[{date_str}] {msg['author']}: {msg['content']}"
    return {"role": role, "content": content, "_msg_id": msg["id"]}


def build_system_prompt(base_personality, control, always_on,
                        retrieved, author_filter, af_query,
                        citation_map, summary, today,
                        channel_id, query_type=None):
    """Assemble the system prompt from context components.

    Handles all branching in one place:
    - Conversational: no always-on summary, no retrieved block.
    - Author-filtered: drops always-on, adds author-specific header.
    - Information: full always-on + retrieved block or fallback summary.
    """
    from utils.query_type import QueryType
    is_conv = (query_type == QueryType.CONVERSATIONAL)

    content = base_personality
    if control:
        content += f"\n\n{control}"

    # Always-on: information queries without author filter only
    if always_on and not is_conv and not author_filter:
        content += (f"\n\n--- CONVERSATION CONTEXT ---\n"
                    f"Today's date: {today}\n\n{always_on}")

    content += f"\n\n{_FOCUS_INSTRUCTION}"

    if is_conv:
        return content

    if retrieved:
        cite_instr = ("CITATION INSTRUCTIONS: cite [N] inline for specific info. "
                      "For participant questions, only cite their messages.\n\n"
                      ) if citation_map else ""
        if author_filter:
            af = ", ".join(author_filter)
            hdr = (f"\n\n--- {af}'s Channel Messages ---\n"
                   f"User asked: \"{af_query}\". Only answer if relevant. "
                   f"Frame specific values with their date: 'on [date] {af} said ...'."
                   f" If not found, say so clearly.\n\n")
        else:
            hdr = (f"\n\n--- PAST MESSAGES FROM THIS CHANNEL ---\n"
                   f"Real messages retrieved by topic relevance.\n\n")
        content += hdr + cite_instr + retrieved
    elif summary:
        from utils.summary_display import format_summary_for_context
        content += (f"\n\n--- CONVERSATION CONTEXT ---\nToday's date: {today}\n\n"
                    f"The following is a summary of this channel's conversation "
                    f"history.\n\n{format_summary_for_context(summary)}")
        logger.warning(f"Retrieval fully degraded ch:{channel_id}")

    return content
