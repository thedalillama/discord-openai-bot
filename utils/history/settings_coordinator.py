# utils/history/settings_coordinator.py
# Version 2.0.0
"""
Settings restoration coordination for Discord bot configuration persistence.

CHANGES v2.0.0: Updated for simplified architecture
- REMOVED: Import from deleted settings_parser.py module
- SIMPLIFIED: Now delegates to realtime parsing only
- MAINTAINED: Coordination functionality for backward compatibility

This module coordinates the restoration of bot configuration settings from
conversation history. With the architectural simplification, it now serves
primarily as a compatibility layer and delegates most work to the realtime
settings parser.

Key Responsibilities:
- Provide backward compatibility for existing coordination calls
- Validate that history is available for processing
- Delegate to realtime parsing infrastructure
- Handle coordination errors gracefully
- Provide detailed logging and status reporting

This module works in conjunction with:
- realtime_settings_parser.py: Handles real-time parsing during load (primary method)
- settings_manager.py: Validates and applies settings to storage

Created in refactoring to maintain under 200-line limit while preserving
comprehensive settings restoration functionality.
"""
from utils.logging_utils import get_logger
from .storage import channel_history
from .settings_manager import apply_restored_settings, get_restoration_summary, validate_parsed_settings

logger = get_logger('history.settings_coordinator')

async def coordinate_settings_restoration(channel_id):
    """
    Coordinate the complete settings restoration process for a channel.
    
    NOTE: With the simplified architecture, this function now primarily serves
    as a compatibility layer. The primary settings restoration happens during
    real-time parsing in the Discord loading process.
    
    This function can be used for post-loading validation or backup scenarios
    where settings need to be checked after the fact.
    
    Args:
        channel_id: Discord channel ID to restore settings for
        
    Returns:
        dict: Summary of restoration results:
            {
                'applied': list of setting types that were applied,
                'skipped': list of setting types that were skipped,
                'errors': list of any errors encountered,
                'total_found': int count of settings processed,
                'note': str explaining coordination approach
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
            'total_found': 0,
            'note': 'No history available for coordination'
        }
    
    logger.info(f"Settings coordination for channel {channel_id}: Primary restoration occurs during realtime parsing")
    
    # With the simplified architecture, settings are primarily restored during
    # realtime parsing. This coordination function now serves as a validation
    # and reporting layer rather than doing the primary restoration work.
    
    return {
        'applied': [], 
        'skipped': [], 
        'errors': [],
        'total_found': 0,
        'note': 'Settings restoration handled by realtime parsing during Discord loading'
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
    
    This function provides information about whether settings restoration
    is possible and what the current state is.
    
    Args:
        channel_id: Discord channel ID to check status for
        
    Returns:
        dict: Status information:
            {
                'channel_id': int,
                'history_available': bool,
                'history_message_count': int,
                'restoration_method': str,
                'can_coordinate': bool
            }
    """
    logger.debug(f"Checking settings restoration status for channel {channel_id}")
    
    validation_result = _validate_history_for_settings(channel_id)
    
    status = {
        'channel_id': channel_id,
        'history_available': validation_result['valid'],
        'history_message_count': len(channel_history.get(channel_id, [])),
        'restoration_method': 'realtime_parsing_during_load',
        'can_coordinate': validation_result['valid']
    }
    
    logger.debug(f"Settings restoration status for channel {channel_id}: {status}")
    
    return status
