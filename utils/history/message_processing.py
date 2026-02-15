# utils/history/message_processing.py
# Version 2.2.1
"""
Message processing and filtering for Discord bot history.

CHANGES v2.2.1: Fix create_user_message() signature for backward compatibility
- FIXED: create_user_message() now accepts optional history_length argument
- REASON: discord_converter.py calls this function with 3 positional arguments;
  incorrect 2-arg signature introduced in v2.2.0 caused history load errors

CHANGES v2.2.0: Update command name references for v2.13.0 redesign
- CHANGED: is_bot_command() special-case exemption updated from !setprompt to !prompt
- REMOVED: Stale is_history_output() patterns for !getprompt and !getai responses
  ('Current system prompt for', 'Current AI provider for') — dead code after command redesign
- MAINTAINED: All other filtering logic unchanged

CHANGES v2.1.0: (prior version — no changelog entry found, preserved as-is)
"""
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger
from .storage import channel_history
from .prompts import get_system_prompt

logger = get_logger('history.message_processing')


def is_bot_command(message_text):
    """
    Check if a message is a bot command.

    Args:
        message_text: The message text to check

    Returns:
        bool: True if the message is a command, False otherwise
    """
    # Special case: !prompt <text> must not be filtered — the settings parser
    # reads confirmation messages back from history to restore the system prompt
    # after bot restarts. The !prompt command (like the former !setprompt) produces
    # those confirmation messages and must remain in history.
    if message_text.startswith('!prompt'):
        return False

    return (message_text.startswith('!') or
            ': !' in message_text or
            message_text.startswith('/'))


def is_history_output(message_text):
    """
    Check if a message appears to be output from a history command.

    Args:
        message_text: The message text to check

    Returns:
        bool: True if the message looks like history output, False otherwise
    """
    # Special case: never filter system prompt update confirmations —
    # the settings parser depends on reading these back from history
    if "System prompt updated for" in message_text:
        logger.debug("Not filtering 'System prompt updated for' message")
        return False

    is_output = (
        "**Conversation History**" in message_text or          # !history header
        HISTORY_LINE_PREFIX in message_text or                  # history line marker
        message_text.startswith("**1.") or                      # numbered history entries
        message_text.startswith("**2.") or
        (("Loaded " in message_text) and
         (" messages from channel history" in message_text)) or  # !history reload response
        "Cleaned history: removed " in message_text or           # !history clean response
        "Auto-response is now " in message_text or               # !autorespond write response
        "Auto-response is currently " in message_text or         # !autorespond no-arg response
        ("System prompt for" in message_text and
         "reset to default" in message_text) or                  # !prompt reset response
        "AI provider for" in message_text                        # !ai responses
    )

    return is_output


def should_skip_message_from_history(message, is_bot_message=False):
    """
    Determine if a message should be skipped when loading history.

    Args:
        message: Discord message object
        is_bot_message: Whether this is from the bot

    Returns:
        tuple: (should_skip, reason) - reason is for logging
    """
    content = message.content

    # Skip bot commands (except !prompt which carries settings data in its responses)
    if content.startswith('!'):
        if not is_bot_command(content):
            return False, "kept (settings command)"
        return True, "bot command"

    return False, "normal message"


def format_user_message_for_history(display_name, content, history_length):
    """
    Format a user message for storage in channel history.

    Args:
        display_name: The user's display name
        content: The message content
        history_length: Current length of history (used for context)

    Returns:
        dict: Formatted message dict for history storage
    """
    return {
        "role": "user",
        "content": f"{display_name}: {content}"
    }


def create_user_message(display_name, content, history_length=None):
    """
    Create a user message dict for history.

    Args:
        display_name: The user's display name
        content: The message content
        history_length: Current length of history (optional, unused — kept for
                        backward compatibility with discord_converter.py callers)

    Returns:
        dict: Message dict with role='user'
    """
    return {
        "role": "user",
        "content": f"{display_name}: {content}"
    }


def create_assistant_message(content):
    """
    Create an assistant message dict for history.

    Args:
        content: The message content

    Returns:
        dict: Message dict with role='assistant'
    """
    return {
        "role": "assistant",
        "content": content
    }


def create_system_update_message(content):
    """
    Create a system update message dict for history.

    Args:
        content: The system update content

    Returns:
        dict: Message dict with role='system'
    """
    return {
        "role": "system",
        "content": content
    }


def prepare_messages_for_api(channel_id):
    """
    Prepare the message history for sending to the AI API.

    Adds the system prompt as the first message and returns the full
    conversation history in the format expected by AI providers.

    Args:
        channel_id: The Discord channel ID

    Returns:
        list: List of message dicts ready for API consumption
    """
    system_prompt = get_system_prompt(channel_id)
    messages = [{"role": "system", "content": system_prompt}]

    history = channel_history.get(channel_id, [])
    for msg in history:
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    return messages


def extract_system_prompt_updates(channel_id):
    """
    Extract system prompt update records from channel history.

    Scans history for SYSTEM_PROMPT_UPDATE entries and returns them
    in chronological order.

    Args:
        channel_id: The Discord channel ID

    Returns:
        list: List of system prompt update strings, oldest first
    """
    updates = []
    history = channel_history.get(channel_id, [])
    for msg in history:
        if (msg["role"] == "system" and
                msg.get("content", "").startswith("SYSTEM_PROMPT_UPDATE:")):
            updates.append(msg["content"])
    return updates
