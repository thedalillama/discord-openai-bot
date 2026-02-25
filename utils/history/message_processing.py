# utils/history/message_processing.py
# Version 2.2.6
"""
Message processing and filtering for Discord bot history.

CHANGES v2.2.6: Add DEEPSEEK_REASONING noise pattern (SOW v2.20.0)
- ADDED: REASONING_PREFIX constant matching openai_compatible_provider.py
- ADDED: REASONING_PREFIX pattern to is_history_output() so reasoning messages
  are filtered from channel_history at runtime, load time, and API payload

CHANGES v2.2.5: Filter settings persistence messages from API payload (SOW v2.19.0)
- MODIFIED: prepare_messages_for_api() filters both is_history_output() and
  is_settings_persistence_message() before building the API payload
- ADDED: is_settings_persistence_message()

CHANGES v2.2.4: Add API error message filter pattern (SOW v2.19.0)
CHANGES v2.2.3: Complete help output filtering (SOW v2.14.0)
CHANGES v2.2.2: Add v2.13.0 command noise patterns (SOW v2.14.0)
CHANGES v2.2.1: Fix create_user_message() backward compatibility
"""
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger
from .storage import channel_history
from .prompts import get_system_prompt

logger = get_logger('history.message_processing')

# Must match API_ERROR_PREFIX in utils/response_handler.py exactly.
API_ERROR_PREFIX = "I'm sorry an API error occurred when attempting to respond: "

# Must match REASONING_PREFIX in ai_providers/openai_compatible_provider.py exactly.
REASONING_PREFIX = "[DEEPSEEK_REASONING]:"


def is_bot_command(message_text):
    """Return True if message is a bot command (except !prompt which carries settings data)."""
    if message_text.startswith('!prompt'):
        return False
    return (message_text.startswith('!') or
            ': !' in message_text or
            message_text.startswith('/'))


def is_history_output(message_text):
    """
    Return True if message is bot noise that should be excluded from channel_history.

    Never filters settings persistence messages — those are handled separately
    by is_settings_persistence_message() and filtered only from the API payload.
    """
    if "System prompt updated for" in message_text:
        logger.debug("Not filtering 'System prompt updated for' message")
        return False

    return (
        # DeepSeek reasoning content (filtered as noise — never store in history)
        message_text.startswith(REASONING_PREFIX) or

        # API error messages from response_handler.py
        message_text.startswith(API_ERROR_PREFIX) or

        # Core history command output
        "**Conversation History**" in message_text or
        HISTORY_LINE_PREFIX in message_text or
        message_text.startswith("**1.") or
        message_text.startswith("**2.") or
        (("Loaded " in message_text) and
         (" messages from channel history" in message_text)) or
        "Cleaned history: removed " in message_text or

        # v2.13.0 command output patterns
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

    # CRITICAL: Do NOT add patterns that match settings persistence messages.
    # These MUST remain in channel_history for realtime_settings_parser.py but
    # are filtered from the API payload in prepare_messages_for_api() via
    # is_settings_persistence_message():
    # - "Auto-response is now" (without "currently" or "already")
    # - "DeepSeek thinking display **enabled/disabled**" (action, not status)
    # - "AI provider for #channel changed from ... to"
    # - "AI provider for #channel reset from ... to"


def is_settings_persistence_message(message_text):
    """
    Return True if message is a settings persistence message.

    These must stay in channel_history for realtime_settings_parser.py to restore
    settings after restart, but are filtered from the API payload in
    prepare_messages_for_api() as they are administrative noise for the AI.

    CRITICAL: Patterns must match confirmation strings in command modules exactly:
    - auto_respond_commands.py: "Auto-response is now **enabled/disabled**"
    - ai_provider_commands.py:  "AI provider for #channel changed/reset from..."
    - thinking_commands.py:     "DeepSeek thinking display **enabled/disabled**"
    """
    return (
        "Auto-response is now **enabled**" in message_text or
        "Auto-response is now **disabled**" in message_text or
        ("AI provider for" in message_text and "changed from" in message_text) or
        ("AI provider for" in message_text and "reset from" in message_text) or
        "DeepSeek thinking display **enabled**" in message_text or
        "DeepSeek thinking display **disabled**" in message_text
    )


def should_skip_message_from_history(message, is_bot_message=False):
    """Return (should_skip, reason) for a Discord message object during history load."""
    content = message.content
    if content.startswith('!'):
        if not is_bot_command(content):
            return False, "kept (settings command)"
        return True, "bot command"
    return False, "normal message"


def format_user_message_for_history(display_name, content, history_length):
    """Format a user message dict for storage in channel_history."""
    return {"role": "user", "content": f"{display_name}: {content}"}


def create_user_message(display_name, content, history_length=None):
    """Create a user message dict. history_length unused, kept for backward compatibility."""
    return {"role": "user", "content": f"{display_name}: {content}"}


def create_assistant_message(content):
    """Create an assistant message dict."""
    return {"role": "assistant", "content": content}


def create_system_update_message(content):
    """Create a system message dict."""
    return {"role": "system", "content": content}


def prepare_messages_for_api(channel_id):
    """
    Prepare messages for API submission.

    Excludes from the API payload:
    1. is_history_output() matches — noise that should never reach the API
    2. is_settings_persistence_message() matches — admin messages needed by the
       settings parser but irrelevant to the AI conversation context
    """
    system_prompt = get_system_prompt(channel_id)
    messages = [{"role": "system", "content": system_prompt}]

    history = channel_history.get(channel_id, [])
    for msg in history:
        if msg["role"] not in ("user", "assistant"):
            continue
        content = msg["content"]
        if is_history_output(content):
            logger.debug(f"Excluding noise from API payload: {content[:50]}...")
            continue
        if is_settings_persistence_message(content):
            logger.debug(f"Excluding settings msg from API payload: {content[:50]}...")
            continue
        messages.append({"role": msg["role"], "content": content})

    return messages


def extract_system_prompt_updates(channel_id):
    """Extract SYSTEM_PROMPT_UPDATE records from channel_history, oldest first."""
    updates = []
    history = channel_history.get(channel_id, [])
    for msg in history:
        if (msg["role"] == "system" and
                msg.get("content", "").startswith("SYSTEM_PROMPT_UPDATE:")):
            updates.append(msg["content"])
    return updates
