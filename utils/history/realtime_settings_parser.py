# utils/history/realtime_settings_parser.py
# Version 2.2.0
"""
Real-time settings parsing orchestrator during Discord message loading.

CHANGES v2.2.0: Split helper functions into settings_appliers.py
- MOVED: _parse_and_apply_system_prompt() → settings_appliers.py
- MOVED: _parse_and_apply_ai_provider() → settings_appliers.py
- MOVED: _parse_and_apply_auto_respond() → settings_appliers.py
- MOVED: _parse_and_apply_thinking_setting() → settings_appliers.py
- MOVED: extract_prompt_from_update_message() → settings_appliers.py
- RE-EXPORTED: extract_prompt_from_update_message for backwards compatibility
- REASON: File exceeded 250-line limit (was 335 lines)

CHANGES v2.1.0: Completed settings recovery implementation
- IMPLEMENTED: _parse_and_apply_ai_provider() for AI provider change confirmations
- IMPLEMENTED: _parse_and_apply_auto_respond() for auto-respond toggle confirmations
- IMPLEMENTED: _parse_and_apply_thinking_setting() for thinking display confirmations
- COMPLETED: Full settings recovery functionality from Discord messages

CHANGES v2.0.0: Simplified to confirmed settings only
- REMOVED: Processing of unprocessed commands (!setprompt, etc.)
- FOCUSED: Only parse confirmed settings from bot confirmation messages
- SIMPLIFIED: More reliable restoration from actual conversation confirmations

This module processes messages in reverse chronological order (newest first)
to find the most recent confirmed settings. Once a setting type is found and
applied, parsing stops for that type to optimise performance.

Only restores from confirmed settings (bot confirmation messages) — there is
no settings database; settings are recovered by replaying !command confirmations
found in channel history.
"""
from utils.logging_utils import get_logger
from .settings_appliers import (
    _parse_and_apply_system_prompt,
    _parse_and_apply_ai_provider,
    _parse_and_apply_auto_respond,
    _parse_and_apply_thinking_setting,
    extract_prompt_from_update_message,  # re-exported for backwards compatibility
)

logger = get_logger('history.realtime_settings_parser')

# Re-export so existing callers (discord_loader.py) still work
__all__ = ['parse_settings_during_load', 'extract_prompt_from_update_message']


async def parse_settings_during_load(messages, channel_id):
    """
    Parse settings from Discord messages in real-time during loading.

    Processes messages in reverse chronological order (newest first) to find
    the most recent settings. Once a setting type is found and applied, parsing
    stops for that type to optimise performance.

    Only processes confirmed settings from bot confirmation messages, not
    unprocessed commands.

    Args:
        messages: List of Discord message objects (chronological order)
        channel_id: Discord channel ID to apply settings to

    Returns:
        dict: Summary of what settings were found and applied:
            {
                'system_prompt': bool,
                'ai_provider': bool,
                'auto_respond': bool,
                'thinking_enabled': bool,
                'total_found': int
            }
    """
    logger.debug(
        f"Starting real-time settings parsing for {len(messages)} messages "
        f"in channel {channel_id}"
    )

    settings_found = {
        'system_prompt': False,
        'ai_provider': False,
        'auto_respond': False,
        'thinking_enabled': False
    }

    for i, message in enumerate(reversed(messages)):
        try:
            if all(settings_found.values()):
                logger.debug(f"All settings found, stopping parsing after {i+1} messages")
                break

            if not settings_found['system_prompt']:
                if _parse_and_apply_system_prompt(message, channel_id):
                    settings_found['system_prompt'] = True
                    logger.debug(f"Found system prompt in message {i+1}")

            if not settings_found['ai_provider']:
                if _parse_and_apply_ai_provider(message, channel_id):
                    settings_found['ai_provider'] = True
                    logger.debug(f"Found AI provider change in message {i+1}")

            if not settings_found['auto_respond']:
                if _parse_and_apply_auto_respond(message, channel_id):
                    settings_found['auto_respond'] = True
                    logger.debug(f"Found auto-respond setting in message {i+1}")

            if not settings_found['thinking_enabled']:
                if _parse_and_apply_thinking_setting(message, channel_id):
                    settings_found['thinking_enabled'] = True
                    logger.debug(f"Found thinking setting in message {i+1}")

        except Exception as e:
            logger.error(f"Error parsing settings from message {i+1}: {e}")
            continue

    total_found = sum(settings_found.values())
    logger.info(
        f"Real-time settings parsing complete for channel {channel_id}: "
        f"{total_found} settings found and applied"
    )

    return {**settings_found, 'total_found': total_found}
