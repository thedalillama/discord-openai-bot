# utils/history/message_processing.py
# Version 2.4.0
"""
Message processing and filtering for Discord bot history.

CHANGES v2.4.0: Thread _msg_id through message creation and API prep
- MODIFIED: create_user_message(), create_assistant_message(),
  format_user_message_for_history() — accept optional msg_id kwarg;
  include _msg_id in returned dict when provided
- MODIFIED: prepare_messages_for_api() — pass through _msg_id from
  channel_history so Layer 2 dedup in context_manager can match IDs

CHANGES v2.3.0: Prefix-based filtering replaces pattern matching
- ADDED: is_noise_message() — checks for ℹ️ prefix (command output, display)
- ADDED: is_settings_message() — checks for ⚙️ prefix (persistent settings)
- ADDED: is_admin_output() — either prefix (filters from API and summarizer)
- RETAINED: is_history_output() — now delegates to prefix checks + legacy
  patterns for backward compatibility with pre-prefix messages in history
- RETAINED: is_settings_persistence_message() — now delegates to prefix check
  + legacy patterns for backward compat
- RETAINED: is_summary_output() — now delegates to prefix check + legacy
- RETAINED: All other functions unchanged

The ℹ️/⚙️ prefix system replaces the growing list of string patterns.
New commands only need to prepend the right emoji. Legacy patterns remain
for messages already stored in SQLite/Discord history without prefixes.

CHANGES v2.2.7: Add is_summary_output()
CHANGES v2.2.6: Add DEEPSEEK_REASONING noise pattern
CHANGES v2.2.5: Filter settings persistence messages from API payload
CHANGES v2.2.4: Add API error message filter pattern
"""
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger
from .storage import channel_history
from .prompts import get_system_prompt

logger = get_logger('history.message_processing')

# Must match API_ERROR_PREFIX in utils/response_handler.py exactly.
API_ERROR_PREFIX = "I'm sorry an API error occurred when attempting to respond: "

# Must match REASONING_PREFIX in ai_providers/openai_compatible_provider.py.
REASONING_PREFIX = "[DEEPSEEK_REASONING]:"

# --- Prefix-based filters (new system) ---

INFO_PREFIX = "ℹ️"
SETTINGS_PREFIX = "⚙️"


def is_noise_message(content):
    """True if message is informational output (ℹ️ prefix). Filter everywhere."""
    return content.startswith(INFO_PREFIX)


def is_settings_message(content):
    """True if message is a settings change (⚙️ prefix). Keep for replay,
    filter from API and summarizer."""
    return content.startswith(SETTINGS_PREFIX)


def is_admin_output(content):
    """True if message is any administrative output. Filter from API/summarizer."""
    return content.startswith(INFO_PREFIX) or content.startswith(SETTINGS_PREFIX)


# --- Legacy filters (backward compat for pre-prefix messages) ---

def is_bot_command(message_text):
    """Return True if message is a bot command (except !prompt)."""
    if message_text.startswith('!prompt'):
        return False
    return (message_text.startswith('!') or
            ': !' in message_text or
            message_text.startswith('/'))


def is_history_output(message_text):
    """
    Return True if message is bot noise to exclude from channel_history.

    Checks new prefix system first, then falls back to legacy patterns
    for messages stored before the prefix system was introduced.
    """
    # New prefix system
    if is_noise_message(message_text):
        return True

    # Settings messages are NOT history noise — they stay in history
    # for replay, but get filtered at API build time separately.
    if "System prompt updated for" in message_text:
        return False

    if is_summary_output(message_text):
        return True

    # Legacy patterns for pre-prefix messages
    return (
        message_text.startswith(REASONING_PREFIX) or
        message_text.startswith(API_ERROR_PREFIX) or
        "**Conversation History**" in message_text or
        HISTORY_LINE_PREFIX in message_text or
        message_text.startswith("**1.") or
        message_text.startswith("**2.") or
        (("Loaded " in message_text) and
         (" messages from channel history" in message_text)) or
        "Cleaned history: removed " in message_text or
        message_text.startswith("```\n!") or
        "**Bot Status for" in message_text or
        "Usage: !history" in message_text or
        "Options: on, off" in message_text or
        "Available providers:" in message_text or
        "DeepSeek thinking display is currently" in message_text or
        "DeepSeek thinking display is already" in message_text or
        "Auto-response is currently " in message_text or
        "Auto-response is already" in message_text or
        "is already set to" in message_text or
        "is already using the default" in message_text or
        ("System prompt for" in message_text and "is already" in message_text) or
        "Current system prompt for" in message_text or
        "You need administrator permissions" in message_text or
        "Invalid setting:" in message_text or
        "Invalid AI provider:" in message_text or
        "Unknown history command:" in message_text or
        "No Category:" in message_text or
        ("Manage the" in message_text and "provider" in message_text)
    )


def is_summary_output(message_text):
    """Return True if message is output from a !summary command."""
    if is_noise_message(message_text):
        return True
    # Legacy patterns
    return (
        message_text.startswith("**Summary for #") or
        message_text.startswith("**Summary updated for #") or
        message_text.startswith("No new messages to summarize") or
        message_text.startswith("Summarization failed:") or
        message_text.startswith("Error running summarization:") or
        message_text.startswith("Summary cleared for #") or
        message_text.startswith("No summary found for #") or
        message_text.startswith("No summary available for #") or
        message_text.startswith("Error retrieving summary:") or
        message_text.startswith("Error clearing summary:") or
        message_text.startswith("**Raw Minutes for #") or
        message_text.startswith("**Full Summary for #") or
        message_text.startswith("OVERVIEW")
    )


def is_settings_persistence_message(message_text):
    """Return True if message is a settings persistence message."""
    if is_settings_message(message_text):
        return True
    # Legacy patterns
    return (
        "Auto-response is now **enabled**" in message_text or
        "Auto-response is now **disabled**" in message_text or
        ("AI provider for" in message_text and "changed from" in message_text) or
        ("AI provider for" in message_text and "reset from" in message_text) or
        "DeepSeek thinking display **enabled**" in message_text or
        "DeepSeek thinking display **disabled**" in message_text
    )


def should_skip_message_from_history(message, is_bot_message=False):
    """Return (should_skip, reason) for a Discord message during history load."""
    content = message.content
    if content.startswith('!'):
        if not is_bot_command(content):
            return False, "kept (settings command)"
        return True, "bot command"
    return False, "normal message"


def format_user_message_for_history(display_name, content, history_length,
                                    msg_id=None):
    """Format a user message dict for storage in channel_history."""
    m = {"role": "user", "content": f"{display_name}: {content}"}
    if msg_id is not None: m["_msg_id"] = msg_id
    return m


def create_user_message(display_name, content, history_length=None, msg_id=None):
    """Create a user message dict."""
    m = {"role": "user", "content": f"{display_name}: {content}"}
    if msg_id is not None: m["_msg_id"] = msg_id
    return m


def create_assistant_message(content, msg_id=None):
    """Create an assistant message dict."""
    m = {"role": "assistant", "content": content}
    if msg_id is not None: m["_msg_id"] = msg_id
    return m


def create_system_update_message(content):
    """Create a system message dict."""
    return {"role": "system", "content": content}


def prepare_messages_for_api(channel_id):
    """Prepare messages for API submission, filtering admin output."""
    system_prompt = get_system_prompt(channel_id)
    messages = [{"role": "system", "content": system_prompt}]

    history = channel_history.get(channel_id, [])
    for msg in history:
        if msg["role"] not in ("user", "assistant"):
            continue
        content = msg["content"]
        if is_history_output(content):
            continue
        if is_settings_persistence_message(content):
            continue
        entry = {"role": msg["role"], "content": content}
        if "_msg_id" in msg:
            entry["_msg_id"] = msg["_msg_id"]
        messages.append(entry)

    return messages


def extract_system_prompt_updates(channel_id):
    """Extract SYSTEM_PROMPT_UPDATE records from channel_history."""
    updates = []
    history = channel_history.get(channel_id, [])
    for msg in history:
        if (msg["role"] == "system" and
                msg.get("content", "").startswith("SYSTEM_PROMPT_UPDATE:")):
            updates.append(msg["content"])
    return updates
