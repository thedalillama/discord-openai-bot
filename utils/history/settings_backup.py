# utils/history/settings_backup.py
# Version 1.0.0
"""
Settings backup and restore functionality for Discord bot configuration.

This module provides backup and restore capabilities for bot configuration
settings. Functions were extracted from settings_manager.py in v1.0.0 to
maintain the 250-line limit while preserving all backup functionality.

Key Responsibilities:
- Create backups of current channel settings
- Restore settings from backup data
- Get current settings for comparison and analysis
- Handle backup data validation and safety checks
- Support for disaster recovery and testing scenarios

These backup operations are separated from core settings management to keep
the main workflow focused while providing comprehensive backup capabilities
for system administrators and Configuration Persistence features.
"""
import json
import datetime
from utils.logging_utils import get_logger
from .storage import channel_system_prompts, channel_ai_providers

logger = get_logger('history.settings_backup')

def create_settings_backup(channel_id):
    """
    Create a backup of current channel settings.
    
    Creates a comprehensive backup of all current channel configuration
    that can be used for disaster recovery or testing purposes.
    
    Args:
        channel_id: Discord channel ID to backup settings for
        
    Returns:
        dict: Backup data with keys:
            - 'channel_id': The channel ID
            - 'backup_timestamp': When backup was created
            - 'settings': Current settings data
            - 'metadata': Additional backup information
    """
    logger.debug(f"Creating settings backup for channel {channel_id}")
    
    current_settings = get_current_settings(channel_id)
    
    backup_data = {
        'channel_id': channel_id,
        'backup_timestamp': datetime.datetime.now().isoformat(),
        'settings': current_settings,
        'metadata': {
            'backup_version': '1.0',
            'created_by': 'settings_backup.py',
            'settings_count': sum(1 for v in current_settings.values() if v is not None)
        }
    }
    
    logger.info(f"Created settings backup for channel {channel_id} with {backup_data['metadata']['settings_count']} settings")
    
    return backup_data

def restore_from_backup(backup_data, channel_id):
    """
    Restore settings from backup data.
    
    Restores channel configuration from previously created backup data
    with validation and safety checks.
    
    Args:
        backup_data: Backup data dict from create_settings_backup()
        channel_id: Discord channel ID to restore settings to
        
    Returns:
        dict: Restoration result with keys:
            - 'success': bool indicating if restoration succeeded
            - 'restored': list of setting types that were restored
            - 'errors': list of any errors encountered
            - 'metadata': restoration metadata
    """
    logger.info(f"Restoring settings from backup for channel {channel_id}")
    
    result = {
        'success': False,
        'restored': [],
        'errors': [],
        'metadata': {
            'restore_timestamp': datetime.datetime.now().isoformat(),
            'backup_timestamp': backup_data.get('backup_timestamp', 'unknown')
        }
    }
    
    try:
        # Validate backup data structure
        if not isinstance(backup_data, dict):
            raise ValueError("Backup data must be a dictionary")
        
        if 'settings' not in backup_data:
            raise ValueError("Backup data missing 'settings' key")
        
        settings = backup_data['settings']
        
        # Restore system prompt
        if settings.get('system_prompt') is not None:
            if isinstance(settings['system_prompt'], str) and len(settings['system_prompt'].strip()) > 0:
                channel_system_prompts[channel_id] = settings['system_prompt']
                result['restored'].append('system_prompt')
                logger.debug(f"Restored system prompt: {settings['system_prompt'][:50]}...")
            else:
                result['errors'].append("Invalid system prompt in backup data")
        
        # Restore AI provider
        if settings.get('ai_provider') is not None:
            valid_providers = ['openai', 'anthropic', 'deepseek']
            if settings['ai_provider'] in valid_providers:
                channel_ai_providers[channel_id] = settings['ai_provider']
                result['restored'].append('ai_provider')
                logger.debug(f"Restored AI provider: {settings['ai_provider']}")
            else:
                result['errors'].append(f"Invalid AI provider in backup: {settings['ai_provider']}")
        
        # Note: Auto-respond and thinking settings would require access to their respective modules
        # For now, log what we found but don't restore them
        if settings.get('auto_respond') is not None:
            logger.debug(f"Found auto-respond setting in backup: {settings['auto_respond']} (not restored - requires auto_respond module)")
        
        if settings.get('thinking_enabled') is not None:
            logger.debug(f"Found thinking setting in backup: {settings['thinking_enabled']} (not restored - requires thinking module)")
        
        result['success'] = len(result['errors']) == 0
        result['metadata']['settings_restored'] = len(result['restored'])
        
        logger.info(f"Backup restoration complete for channel {channel_id}: {len(result['restored'])} restored, {len(result['errors'])} errors")
        
    except Exception as e:
        logger.error(f"Error during backup restoration for channel {channel_id}: {e}")
        result['errors'].append(str(e))
        result['success'] = False
    
    return result

def get_current_settings(channel_id):
    """
    Get current settings for a channel.
    
    Retrieves all current configuration settings for a channel for
    comparison, analysis, or backup purposes.
    
    Args:
        channel_id: Discord channel ID to get settings for
        
    Returns:
        dict: Current settings with keys:
            - 'system_prompt': Current system prompt or None
            - 'ai_provider': Current AI provider or None
            - 'auto_respond': Current auto-respond setting or None
            - 'thinking_enabled': Current thinking setting or None
    """
    logger.debug(f"Getting current settings for channel {channel_id}")
    
    current_settings = {
        'system_prompt': channel_system_prompts.get(channel_id),
        'ai_provider': channel_ai_providers.get(channel_id),
        'auto_respond': None,  # Would need access to auto_respond_channels set
        'thinking_enabled': None  # Would need access to thinking settings dict
    }
    
    # Count non-None settings
    settings_count = sum(1 for v in current_settings.values() if v is not None)
    
    logger.debug(f"Retrieved {settings_count} current settings for channel {channel_id}")
    
    return current_settings

def validate_backup_data(backup_data):
    """
    Validate backup data for integrity and correctness.
    
    Performs comprehensive validation of backup data to ensure it's
    safe to restore and contains valid configuration values.
    
    Args:
        backup_data: Backup data dict to validate
        
    Returns:
        tuple: (is_valid, validation_errors)
            is_valid: bool indicating if backup data is valid
            validation_errors: list of validation error messages
    """
    errors = []
    
    try:
        # Check basic structure
        if not isinstance(backup_data, dict):
            errors.append("Backup data must be a dictionary")
            return False, errors
        
        required_keys = ['channel_id', 'backup_timestamp', 'settings']
        for key in required_keys:
            if key not in backup_data:
                errors.append(f"Missing required key: {key}")
        
        if 'settings' in backup_data:
            settings = backup_data['settings']
            
            # Validate system prompt
            if 'system_prompt' in settings and settings['system_prompt'] is not None:
                if not isinstance(settings['system_prompt'], str):
                    errors.append("System prompt in backup must be a string")
                elif len(settings['system_prompt'].strip()) == 0:
                    errors.append("System prompt in backup cannot be empty")
                elif len(settings['system_prompt']) > 10000:
                    errors.append("System prompt in backup is too long (>10000 characters)")
            
            # Validate AI provider
            if 'ai_provider' in settings and settings['ai_provider'] is not None:
                valid_providers = ['openai', 'anthropic', 'deepseek']
                if settings['ai_provider'] not in valid_providers:
                    errors.append(f"Invalid AI provider in backup: {settings['ai_provider']}")
            
            # Validate boolean settings
            for setting_name in ['auto_respond', 'thinking_enabled']:
                if setting_name in settings and settings[setting_name] is not None:
                    if not isinstance(settings[setting_name], bool):
                        errors.append(f"{setting_name} in backup must be boolean")
        
        # Validate timestamp format
        if 'backup_timestamp' in backup_data:
            try:
                datetime.datetime.fromisoformat(backup_data['backup_timestamp'])
            except ValueError:
                errors.append("Invalid backup timestamp format")
        
    except Exception as e:
        errors.append(f"Error during backup validation: {str(e)}")
    
    is_valid = len(errors) == 0
    
    if not is_valid:
        logger.warning(f"Backup data validation failed: {errors}")
    else:
        logger.debug("Backup data validation passed")
    
    return is_valid, errors

def export_backup_to_json(backup_data):
    """
    Export backup data to JSON format for storage or transfer.
    
    Args:
        backup_data: Backup data dict to export
        
    Returns:
        str: JSON representation of backup data
    """
    try:
        return json.dumps(backup_data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error exporting backup to JSON: {e}")
        raise

def import_backup_from_json(json_data):
    """
    Import backup data from JSON format.
    
    Args:
        json_data: JSON string containing backup data
        
    Returns:
        dict: Backup data dict
        
    Raises:
        ValueError: If JSON is invalid or backup data is malformed
    """
    try:
        backup_data = json.loads(json_data)
        
        # Validate imported data
        is_valid, errors = validate_backup_data(backup_data)
        if not is_valid:
            raise ValueError(f"Invalid backup data: {'; '.join(errors)}")
        
        return backup_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing backup JSON: {e}")
        raise ValueError(f"Invalid JSON format: {e}")
    except Exception as e:
        logger.error(f"Error importing backup from JSON: {e}")
        raise
