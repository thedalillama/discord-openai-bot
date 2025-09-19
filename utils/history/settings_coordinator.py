# utils/history/settings_coordinator.py
# Version 1.0.0
"""
Settings restoration coordination for Discord bot configuration persistence.

This module coordinates the restoration of bot configuration settings from
conversation history. It serves as a backup/validation system for the real-time
settings parsing that occurs during message loading, and handles edge cases
where settings might need post-processing.

Key Responsibilities:
- Coordinate settings parsing from conversation history
- Validate parsed settings for correctness and safety
- Apply validated settings to in-memory storage
- Handle settings restoration errors gracefully
- Provide detailed logging and status reporting

This module works in conjunction with:
- settings_parser.py: Extracts settings from conversation history
- settings_manager.py: Validates and applies settings to storage
- realtime_settings_parser.py: Handles real-time parsing during load

Created in refactoring to maintain under 200-line limit while preserving
comprehensive settings restoration functionality.
"""
from utils.logging_utils import get_logger
from .storage import channel_history
from .settings_parser import parse_settings_from_history
from .settings_manager import apply_restored_settings, get_restoration_summary, validate_parsed_settings

logger = get_logger('history.settings_coordinator')

async def coordinate_settings_restoration(channel_id):
    """
    Coordinate the complete settings restoration process for a channel.
    
    This function implements the Configuration Persistence feature by parsing
    the loaded conversation history to extract and restore channel settings.
    It serves as a backup to the real-time settings parsing and handles any
    settings that might require post-processing validation.
    
    Args:
        channel_id: Discord channel ID to restore settings for
        
    Returns:
        dict: Summary of restoration results:
            {
                'applied': list of setting types that were applied,
                'skipped': list of setting types that were skipped,
                'errors': list of any errors encountered,
                'total_found': int count of settings processed
            }
    """
    logger.debug(f"Starting settings restoration coordination for channel {channel_id}")
    
    # Validate that we have history to work with
    validation_result = _validate_history_for_settings(channel_id)
    if not validation_result['valid']:
        logger.debug(f"History validation failed: {validation_result['reason']}")
        return {
            'applied': [], 
            'skipped': [], 
            'errors': [validation_result['reason']],
            'total_found': 0
        }
    
    history_messages = channel_history[channel_id]
    
    # Parse settings from the conversation history
    try:
        logger.debug(f"Parsing settings from {len(history_messages)} history messages")
        settings = parse_settings_from_history(history_messages, channel_id)
        
        if not settings['settings_found']:
            logger.debug(f"No settings found in history for channel {channel_id}")
            return {
                'applied': [], 
                'skipped': [], 
                'errors': [],
                'total_found': 0
            }
        
        logger.debug(f"Found {len(settings['settings_found'])} setting types: {settings['settings_found']}")
        
    except Exception as e:
        logger.error(f"Error parsing settings from history: {e}")
        return {
            'applied': [], 
            'skipped': [], 
            'errors': [f"Parsing error: {str(e)}"],
            'total_found': 0
        }
    
    # Validate the parsed settings before applying
    try:
        is_valid, validation_errors = validate_parsed_settings(settings)
        
        if not is_valid:
            logger.warning(f"Settings validation failed for channel {channel_id}: {validation_errors}")
            return {
                'applied': [], 
                'skipped': [], 
                'errors': validation_errors,
                'total_found': len(settings['settings_found'])
            }
        
        logger.debug(f"Settings validation passed for channel {channel_id}")
        
    except Exception as e:
        logger.error(f"Error validating parsed settings: {e}")
        return {
            'applied': [], 
            'skipped': [], 
            'errors': [f"Validation error: {str(e)}"],
            'total_found': len(settings['settings_found'])
        }
    
    # Apply the validated settings
    try:
        logger.debug(f"Applying validated settings for channel {channel_id}")
        result = apply_restored_settings(settings, channel_id)
        
        # Enhance result with total found count
        result['total_found'] = len(settings['settings_found'])
        
        # Log comprehensive restoration summary
        if result['applied']:
            summary = get_restoration_summary(settings)
            logger.info(f"Settings restored for channel {channel_id}: {summary}")
        else:
            logger.debug(f"No new settings applied for channel {channel_id} (may already be set)")
        
        if result['errors']:
            logger.warning(f"Settings restoration errors for channel {channel_id}: {result['errors']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error applying restored settings: {e}")
        return {
            'applied': [], 
            'skipped': [], 
            'errors': [f"Application error: {str(e)}"],
            'total_found': len(settings['settings_found'])
        }

def _validate_history_for_settings(channel_id):
    """
    Validate that channel history is available and suitable for settings restoration.
    
    Args:
        channel_id: Discord channel ID to validate
        
    Returns:
        dict: Validation result with 'valid' boolean and 'reason' string
    """
    if channel_id not in channel_history:
        return {
            'valid': False,
            'reason': 'No history loaded for channel'
        }
    
    history_messages = channel_history[channel_id]
    
    if not history_messages:
        return {
            'valid': False,
            'reason': 'History is empty'
        }
    
    if len(history_messages) < 1:
        return {
            'valid': False,
            'reason': 'Insufficient history for settings analysis'
        }
    
    return {
        'valid': True,
        'reason': 'History validation passed'
    }

async def get_settings_restoration_status(channel_id):
    """
    Get the current status of settings restoration for a channel.
    
    Args:
        channel_id: Discord channel ID to check
        
    Returns:
        dict: Status information about settings restoration capabilities
    """
    validation_result = _validate_history_for_settings(channel_id)
    
    if not validation_result['valid']:
        return {
            'can_restore': False,
            'reason': validation_result['reason'],
            'message_count': 0,
            'estimated_settings': 0
        }
    
    history_messages = channel_history[channel_id]
    
    # Quick scan to estimate settings without full parsing
    estimated_settings = 0
    for msg in history_messages:
        content = msg.get('content', '')
        
        # Quick heuristics for common settings patterns
        if 'SYSTEM_PROMPT_UPDATE:' in content:
            estimated_settings += 1
        elif 'AI provider for' in content and 'changed' in content:
            estimated_settings += 1
        elif 'Auto-response is now' in content:
            estimated_settings += 1
        elif 'DeepSeek thinking display' in content:
            estimated_settings += 1
    
    return {
        'can_restore': True,
        'reason': 'Ready for settings restoration',
        'message_count': len(history_messages),
        'estimated_settings': estimated_settings
    }
