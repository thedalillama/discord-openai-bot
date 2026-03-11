# utils/history/settings_appliers.py
# Version 1.0.0
"""
Individual setting applier functions for real-time settings parsing.

CHANGES v1.0.0: Extracted from realtime_settings_parser.py
- EXTRACTED: _parse_and_apply_system_prompt()
- EXTRACTED: _parse_and_apply_ai_provider()
- EXTRACTED: _parse_and_apply_auto_respond()
- EXTRACTED: _parse_and_apply_thinking_setting()
- EXTRACTED: extract_prompt_from_update_message()

Each function inspects a single Discord message and, if it contains a
confirmed bot setting change, applies that setting to in-memory storage.
All functions return True if the setting was found and applied, False otherwise.
"""
from utils.logging_utils import get_logger
from .prompts import channel_system_prompts

logger = get_logger('history.settings_appliers')


def _parse_and_apply_system_prompt(message, channel_id):
    """
    Parse and apply system prompt from bot confirmation messages only.

    Only processes confirmed system prompt updates from bot response messages,
    not unprocessed commands.

    Args:
        message: Discord message object
        channel_id: Discord channel ID

    Returns:
        bool: True if system prompt was found and applied, False otherwise
    """
    try:
        if (hasattr(message, 'author') and
              hasattr(message.author, 'bot') and
              message.author.bot and
              "System prompt updated for" in message.content and
              "New prompt:" in message.content):

            extracted_prompt = extract_prompt_from_update_message(message)
            if extracted_prompt:
                channel_system_prompts[channel_id] = extracted_prompt
                logger.info(f"Applied system prompt from bot confirmation: {extracted_prompt[:50]}...")
                return True

    except Exception as e:
        logger.error(f"Error parsing system prompt: {e}")

    return False


def _parse_and_apply_ai_provider(message, channel_id):
    """
    Parse and apply AI provider setting from bot confirmation messages.

    Parses AI provider change confirmations from bot messages like:
    - "AI provider for #channel changed from **openai** to **deepseek**."
    - "AI provider for #channel reset from **deepseek** to default (**openai**)."

    Args:
        message: Discord message object
        channel_id: Discord channel ID

    Returns:
        bool: True if AI provider was found and applied, False otherwise
    """
    try:
        if (hasattr(message, 'author') and
              hasattr(message.author, 'bot') and
              message.author.bot):

            content = message.content

            if "AI provider for" in content and " to " in content:
                parts = content.split(" to ")
                if len(parts) >= 2:
                    provider_part = parts[-1].strip()

                    # Clean up formatting; handle "default (**provider**)." format
                    provider = (provider_part
                                .replace("**", "")
                                .replace(".", "")
                                .replace("(", "")
                                .replace(")", "")
                                .strip())

                    if provider.startswith("default "):
                        provider = provider.replace("default ", "").strip()

                    if provider.lower() in ['openai', 'anthropic', 'deepseek']:
                        from .storage import channel_ai_providers
                        channel_ai_providers[channel_id] = provider.lower()
                        logger.info(f"Applied AI provider from confirmation: {provider.lower()}")
                        return True

    except Exception as e:
        logger.error(f"Error parsing AI provider: {e}")

    return False


def _parse_and_apply_auto_respond(message, channel_id):
    """
    Parse and apply auto-respond setting from bot confirmation messages.

    Parses auto-respond toggle confirmations from bot messages like:
    - "Auto-response is now **enabled** in #channel"
    - "Auto-response is now **disabled** in #channel"

    Args:
        message: Discord message object
        channel_id: Discord channel ID

    Returns:
        bool: True if auto-respond setting was found and applied, False otherwise
    """
    try:
        if (hasattr(message, 'author') and
              hasattr(message.author, 'bot') and
              message.author.bot):

            content = message.content.lower()

            if "auto-response is now" in content:
                if "enabled" in content:
                    logger.info(f"Found auto-respond enabled confirmation for channel {channel_id}")
                    # TODO: integration point to apply auto-respond enabled setting
                    return True
                elif "disabled" in content:
                    logger.info(f"Found auto-respond disabled confirmation for channel {channel_id}")
                    # TODO: integration point to apply auto-respond disabled setting
                    return True

    except Exception as e:
        logger.error(f"Error parsing auto-respond setting: {e}")

    return False


def _parse_and_apply_thinking_setting(message, channel_id):
    """
    Parse and apply thinking display setting from bot confirmation messages.

    Parses thinking display confirmations from bot messages like:
    - "DeepSeek thinking display **enabled** for #channel"
    - "DeepSeek thinking display **disabled** for #channel"

    Args:
        message: Discord message object
        channel_id: Discord channel ID

    Returns:
        bool: True if thinking setting was found and applied, False otherwise
    """
    try:
        if (hasattr(message, 'author') and
              hasattr(message.author, 'bot') and
              message.author.bot):

            content = message.content.lower()

            if "deepseek thinking display" in content:
                try:
                    from commands.thinking_commands import set_thinking_enabled
                    if "enabled" in content:
                        set_thinking_enabled(channel_id, True)
                        logger.info(f"Applied thinking display enabled for channel {channel_id}")
                        return True
                    elif "disabled" in content:
                        set_thinking_enabled(channel_id, False)
                        logger.info(f"Applied thinking display disabled for channel {channel_id}")
                        return True
                except ImportError:
                    logger.warning("Could not import thinking commands for settings restoration")
                    return False

    except Exception as e:
        logger.error(f"Error parsing thinking setting: {e}")

    return False


def extract_prompt_from_update_message(message):
    """
    Extract system prompt text from a "System prompt updated" confirmation message.

    Args:
        message: Discord message object containing system prompt update confirmation

    Returns:
        str or None: The system prompt text, or None if extraction failed

    Example:
        Input:  "System prompt updated for #channel. New prompt: **You are helpful**"
        Output: "You are helpful"
    """
    try:
        content = message.content

        if "New prompt:" not in content:
            logger.debug("System prompt update message missing 'New prompt:' section")
            return None

        prompt_text = content.split("New prompt:", 1)[1].strip()
        prompt_text = prompt_text.replace("**", "").strip()

        if not prompt_text:
            logger.debug("Extracted prompt text was empty after cleaning")
            return None

        logger.debug(f"Successfully extracted prompt: {prompt_text[:50]}...")
        return prompt_text

    except Exception as e:
        logger.error(f"Error extracting prompt from update message: {e}")
        logger.debug(f"Update message content: {message.content}")
        return None
