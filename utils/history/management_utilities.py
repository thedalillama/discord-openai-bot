# utils/history/management_utilities.py
# Version 1.0.0
"""
Utility functions for settings management operations.

This module contains utility functions extracted from settings_manager.py 
to maintain the 250-line limit while preserving all functionality.

Functions included:
- Channel cleanup operations
- Statistics generation
- Administrative utilities
"""
from utils.logging_utils import get_logger
from .storage import channel_system_prompts, channel_ai_providers

logger = get_logger('history.management_utilities')

def clear_channel_settings(channel_id):
    """
    Clear all settings for a channel.
    
    Removes all configuration settings for a channel, returning it to
    default state. Useful for cleanup or reset operations.
    
    Args:
        channel_id: Discord channel ID to clear settings for
        
    Returns:
        dict: Summary of what was cleared:
            {
                'cleared': list of setting types that were cleared,
                'not_found': list of setting types that weren't set
            }
    """
    logger.debug(f"Clearing settings for channel {channel_id}")
    
    result = {
        'cleared': [],
        'not_found': []
    }
    
    # Clear system prompt
    if channel_id in channel_system_prompts:
        del channel_system_prompts[channel_id]
        result['cleared'].append('system_prompt')
        logger.debug(f"Cleared system prompt for channel {channel_id}")
    else:
        result['not_found'].append('system_prompt')
    
    # Clear AI provider
    if channel_id in channel_ai_providers:
        del channel_ai_providers[channel_id]
        result['cleared'].append('ai_provider')
        logger.debug(f"Cleared AI provider for channel {channel_id}")
    else:
        result['not_found'].append('ai_provider')
    
    # Note: Auto-respond and thinking settings are handled by other modules
    # and would need to be cleared separately
    
    logger.info(f"Settings clearing complete for channel {channel_id}: {len(result['cleared'])} cleared, {len(result['not_found'])} not found")
    
    return result

def get_settings_statistics():
    """
    Get statistics about current settings usage across all channels.
    
    Provides overview statistics about settings usage across the bot
    for monitoring and analysis purposes.
    
    Returns:
        dict: Statistics about current settings:
            {
                'channels_with_prompts': int,
                'channels_with_providers': int,
                'total_channels_configured': int,
                'provider_usage': dict mapping provider names to counts,
                'average_prompt_length': float
            }
    """
    logger.debug("Generating settings statistics")
    
    stats = {
        'channels_with_prompts': len(channel_system_prompts),
        'channels_with_providers': len(channel_ai_providers),
        'total_channels_configured': 0,
        'provider_usage': {},
        'average_prompt_length': 0.0
    }
    
    # Calculate unique channels with any settings
    configured_channels = set()
    configured_channels.update(channel_system_prompts.keys())
    configured_channels.update(channel_ai_providers.keys())
    stats['total_channels_configured'] = len(configured_channels)
    
    # Calculate provider usage statistics
    for provider in channel_ai_providers.values():
        stats['provider_usage'][provider] = stats['provider_usage'].get(provider, 0) + 1
    
    # Calculate average prompt length
    if channel_system_prompts:
        total_length = sum(len(prompt) for prompt in channel_system_prompts.values())
        stats['average_prompt_length'] = round(total_length / len(channel_system_prompts), 1)
    
    logger.debug(f"Generated settings statistics: {stats['total_channels_configured']} configured channels")
    
    return stats

def validate_setting_value(setting_type, value):
    """
    Validate an individual setting value for correctness.
    
    Helper function for validating specific setting types and values.
    
    Args:
        setting_type: Type of setting ('system_prompt', 'ai_provider', etc.)
        value: The value to validate
        
    Returns:
        tuple: (is_valid, error_message)
            is_valid: bool indicating if value is valid
            error_message: str error description if invalid, None if valid
    """
    if setting_type == 'system_prompt':
        if not isinstance(value, str):
            return False, "System prompt must be a string"
        elif len(value.strip()) == 0:
            return False, "System prompt cannot be empty"
        elif len(value) > 10000:
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

def get_channel_setting_summary(channel_id):
    """
    Get a summary of all current settings for a specific channel.
    
    Utility function to retrieve and format all settings for a channel
    for display or debugging purposes.
    
    Args:
        channel_id: Discord channel ID to get summary for
        
    Returns:
        dict: Summary of current channel settings:
            {
                'channel_id': int,
                'system_prompt': str or None,
                'ai_provider': str or None,
                'settings_count': int,
                'summary_text': str
            }
    """
    logger.debug(f"Getting setting summary for channel {channel_id}")
    
    summary = {
        'channel_id': channel_id,
        'system_prompt': channel_system_prompts.get(channel_id),
        'ai_provider': channel_ai_providers.get(channel_id),
        'settings_count': 0,
        'summary_text': ''
    }
    
    # Count non-None settings
    summary['settings_count'] = sum(1 for v in [summary['system_prompt'], summary['ai_provider']] if v is not None)
    
    # Generate summary text
    parts = []
    if summary['system_prompt']:
        prompt_preview = summary['system_prompt'][:30] + "..." if len(summary['system_prompt']) > 30 else summary['system_prompt']
        parts.append(f"Prompt: '{prompt_preview}'")
    
    if summary['ai_provider']:
        parts.append(f"Provider: {summary['ai_provider']}")
    
    summary['summary_text'] = "; ".join(parts) if parts else "No custom settings"
    
    logger.debug(f"Generated summary for channel {channel_id}: {summary['settings_count']} settings")
    
    return summary

def bulk_clear_settings(channel_ids):
    """
    Clear settings for multiple channels at once.
    
    Utility function for administrative operations that need to clear
    settings across multiple channels.
    
    Args:
        channel_ids: List of Discord channel IDs to clear settings for
        
    Returns:
        dict: Summary of bulk operation:
            {
                'total_channels': int,
                'channels_cleared': int,
                'channels_not_found': int,
                'results': dict mapping channel_id to clear result
            }
    """
    logger.info(f"Starting bulk clear operation for {len(channel_ids)} channels")
    
    results = {}
    channels_cleared = 0
    channels_not_found = 0
    
    for channel_id in channel_ids:
        try:
            result = clear_channel_settings(channel_id)
            results[channel_id] = result
            
            if result['cleared']:
                channels_cleared += 1
            if not result['cleared'] and result['not_found']:
                channels_not_found += 1
                
        except Exception as e:
            logger.error(f"Error clearing settings for channel {channel_id}: {e}")
            results[channel_id] = {'error': str(e)}
    
    summary = {
        'total_channels': len(channel_ids),
        'channels_cleared': channels_cleared,
        'channels_not_found': channels_not_found,
        'results': results
    }
    
    logger.info(f"Bulk clear complete: {channels_cleared} cleared, {channels_not_found} not found")
    
    return summary
