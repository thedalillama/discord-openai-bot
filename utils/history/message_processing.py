# utils/history/message_processing.py
# Version 2.2.3
"""
Message processing and filtering for Discord bot history.

CHANGES v2.2.3: Complete help output filtering (SOW v2.14.0)
- ADDED: Pattern for !help <command> output

CHANGES v2.2.2: Add v2.13.0 command noise patterns (SOW v2.14.0)
- ADDED: !status, !history, !ai/!autorespond/!thinking noise filtering

CHANGES v2.2.1: Fix create_user_message() backward compatibility
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

    # Core patterns from original commands (pre-v2.13.0)
    is_output = (
        "**Conversation History**" in message_text or          # !history header
        HISTORY_LINE_PREFIX in message_text or                  # history line marker
        message_text.startswith("**1.") or                      # numbered history entries
        message_text.startswith("**2.") or
        (("Loaded " in message_text) and
         (" messages from channel history" in message_text)) or  # !history reload response
        "Cleaned history: removed " in message_text or           # !history clean response
        
        # New patterns from v2.13.0 command redesign
        "**Bot Status for" in message_text or                   # !status output block
        "Usage: !history" in message_text or                    # !history usage hint
        "Options: on, off" in message_text or                   # !autorespond / !thinking options
        "Available providers:" in message_text or               # !ai options line
        "DeepSeek thinking display is currently" in message_text or  # !thinking status
        "DeepSeek thinking display is already" in message_text or    # !thinking no-change
        "Auto-response is currently " in message_text or        # !autorespond status
        "Auto-response is already" in message_text or           # !autorespond no-change
        "is already set to" in message_text or                  # !ai no-change
        "is already using the default" in message_text or       # !ai reset no-change
        ("System prompt for" in message_text and
         "is already" in message_text) or                        # !prompt reset no-change
        "Current system prompt for" in message_text or          # !prompt no-arg display
        "You need administrator permissions" in message_text or  # permission denied
        "Invalid setting:" in message_text or                    # bad !autorespond/!thinking arg
        "Invalid AI provider:" in message_text or               # bad !ai arg
        "Unknown history command:" in message_text or           # bad !history subcommand
        "No Category:" in message_text or                        # !help output (top level)
        ("Manage the" in message_text and "provider" in message_text)  # !help <command> output
    )
    
    # CRITICAL: Do NOT add patterns that match settings persistence messages
    # These MUST remain in history for realtime_settings_parser.py:
    # - "Auto-response is now" (without "currently" or "already")
    # - "DeepSeek thinking display **enabled/disabled**" (action, not status)
    # - "AI provider for #channel changed from ... to"
    # - "AI provider for #channel reset from ... to"

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
