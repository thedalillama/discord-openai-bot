# utils/history/management_utilities.py
# Version 2.0.0
"""
Setting value validation for history settings management.

CHANGES v2.0.0: Dead code cleanup (SOW v5.11.0)
- REMOVED: clear_channel_settings() — no external callers
- REMOVED: get_settings_statistics() — no external callers
- REMOVED: get_channel_setting_summary() — no external callers
- REMOVED: bulk_clear_settings() — no external callers
- KEPT: validate_setting_value() — actively called by settings_manager.py
"""
from utils.logging_utils import get_logger

logger = get_logger('history.management_utilities')


def validate_setting_value(setting_type, value):
    """
    Validate an individual setting value for correctness.

    Args:
        setting_type: Type of setting ('system_prompt', 'ai_provider',
                      'auto_respond', 'thinking_enabled')
        value: The value to validate

    Returns:
        tuple: (is_valid, error_message)
            is_valid: bool — True if value passes validation
            error_message: str if invalid, None if valid
    """
    if setting_type == 'system_prompt':
        if not isinstance(value, str):
            return False, "System prompt must be a string"
        if len(value.strip()) == 0:
            return False, "System prompt cannot be empty"
        if len(value) > 10000:
            return False, "System prompt is too long (>10000 characters)"
    elif setting_type == 'ai_provider':
        valid_providers = ['openai', 'anthropic', 'deepseek']
        if value not in valid_providers:
            return False, f"Invalid AI provider: {value}. Valid: {valid_providers}"
    elif setting_type == 'auto_respond':
        if not isinstance(value, bool):
            return False, "Auto-respond setting must be boolean"
    elif setting_type == 'thinking_enabled':
        if not isinstance(value, bool):
            return False, "Thinking enabled setting must be boolean"
    else:
        return False, f"Unknown setting type: {setting_type}"
    return True, None
