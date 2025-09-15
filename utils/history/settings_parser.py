# utils/history/settings_parser.py
# Version 1.0.0
"""
Configuration settings parsing from conversation history.

This module provides parsing functionality to extract bot configuration settings
from conversation history messages. It focuses purely on parsing and extraction,
with no side effects or state modifications.

The parsing functions identify configuration changes recorded in:
- System prompt update entries (SYSTEM_PROMPT_UPDATE: format)
- Bot response messages confirming setting changes
- Command execution confirmations

This module is part of the Configuration Persistence feature and works with
settings_manager.py to provide complete settings restoration functionality.

Key Features:
- Parse system prompt changes from SYSTEM_PROMPT_UPDATE entries
- Extract AI provider changes from bot confirmation messages  
- Extract auto-response settings from command responses
- Extract thinking display settings from command responses
- Pure parsing functions with no side effects

Created in v1.0.0 by splitting settings_restoration.py to maintain 200-line limit.
"""
import re
from utils.logging_utils import get_logger

logger = get_logger('history.settings_parser')

def parse_settings_from_history(channel_history_messages, channel_id):
    """
    Extract configuration settings from conversation history messages.
    
    This is the main parsing function that scans through all messages in 
    chronological order and extracts the most recent setting for each 
    configuration type.
    
    Args:
        channel_history_messages: List of message dicts from channel history
        channel_id: Discord channel ID for logging context
        
    Returns:
        dict: Dictionary with latest settings found:
            {
                'system_prompt': str or None,
                'ai_provider': str or None,
                'auto_respond': bool or None,
                'thinking_enabled': bool or None,
                'settings_found': list of setting types that were parsed
            }
            
    Example:
        settings = parse_settings_from_history(messages, channel_id)
        if settings['system_prompt']:
            # System prompt found and can be applied
    """
    logger.debug(f"Parsing settings from {len(channel_history_messages)} history messages for channel {channel_id}")
    
    settings = {
        'system_prompt': None,
        'ai_provider': None,
        'auto_respond': None,
        'thinking_enabled': None,
        'settings_found': []
    }
    
    # Scan messages chronologically to get latest settings
    for i, msg in enumerate(channel_history_messages):
        try:
            # Parse system prompt updates (highest priority - these are canonical)
            prompt = parse_system_prompt_update(msg)
            if prompt is not None:
                settings['system_prompt'] = prompt
                if 'system_prompt' not in settings['settings_found']:
                    settings['settings_found'].append('system_prompt')
                logger.debug(f"Found system prompt update in message {i+1}")
            
            # Parse AI provider changes from bot responses
            provider = parse_ai_provider_change(msg)
            if provider is not None:
                settings['ai_provider'] = provider
                if 'ai_provider' not in settings['settings_found']:
                    settings['settings_found'].append('ai_provider')
                logger.debug(f"Found AI provider change in message {i+1}: {provider}")
            
            # Parse auto-respond setting changes
            auto_respond = parse_auto_respond_change(msg)
            if auto_respond is not None:
                settings['auto_respond'] = auto_respond
                if 'auto_respond' not in settings['settings_found']:
                    settings['settings_found'].append('auto_respond')
                logger.debug(f"Found auto-respond change in message {i+1}: {auto_respond}")
            
            # Parse thinking display setting changes
            thinking = parse_thinking_setting_change(msg)
            if thinking is not None:
                settings['thinking_enabled'] = thinking
                if 'thinking_enabled' not in settings['settings_found']:
                    settings['settings_found'].append('thinking_enabled')
                logger.debug(f"Found thinking setting change in message {i+1}: {thinking}")
                
        except Exception as e:
            logger.error(f"Error parsing settings from message {i+1}: {e}")
            continue
    
    logger.info(f"Settings parsing complete for channel {channel_id}: found {len(settings['settings_found'])} setting types")
    
    return settings

def parse_system_prompt_update(message):
    """
    Extract system prompt from a SYSTEM_PROMPT_UPDATE message.
    
    System prompt updates are stored in a canonical format for reliable parsing:
    {"role": "system", "content": "SYSTEM_PROMPT_UPDATE: [actual prompt text]"}
    
    Args:
        message: Message dict from conversation history
        
    Returns:
        str or None: The system prompt text, or None if not a system prompt update
        
    Example:
        msg = {"role": "system", "content": "SYSTEM_PROMPT_UPDATE: You are helpful"}
        prompt = parse_system_prompt_update(msg)  # Returns: "You are helpful"
    """
    if (message.get("role") == "system" and 
        message.get("content", "").startswith("SYSTEM_PROMPT_UPDATE:")):
        
        # Extract the prompt (remove the prefix)
        prompt_text = message["content"].replace("SYSTEM_PROMPT_UPDATE:", "", 1).strip()
        
        if prompt_text:
            logger.debug(f"Extracted system prompt: {prompt_text[:50]}...")
            return prompt_text
    
    return None

def parse_ai_provider_change(message):
    """
    Extract AI provider changes from bot response messages.
    
    AI provider changes are recorded in bot responses like:
    "AI provider for #channel changed from openai to deepseek"
    "AI provider for #channel reset from deepseek to default (openai)"
    
    Args:
        message: Message dict from conversation history
        
    Returns:
        str or None: The new provider name, or None if not a provider change message
        
    Example:
        msg = {"role": "assistant", "content": "AI provider for #test changed from openai to deepseek"}
        provider = parse_ai_provider_change(msg)  # Returns: "deepseek"
    """
    if message.get("role") != "assistant":
        return None
    
    content = message.get("content", "")
    
    # Pattern 1: "AI provider for #channel changed from X to Y"
    match = re.search(r"AI provider for #\w+ changed from \w+ to (\w+)", content)
    if match:
        provider = match.group(1)
        # Handle "default (provider)" format
        if provider == "default":
            default_match = re.search(r"default \((\w+)\)", content)
            if default_match:
                provider = default_match.group(1)
        logger.debug(f"Parsed AI provider change: {provider}")
        return provider
    
    # Pattern 2: "AI provider for #channel reset from X to default (Y)"
    match = re.search(r"AI provider for #\w+ reset from \w+ to default \((\w+)\)", content)
    if match:
        provider = match.group(1)
        logger.debug(f"Parsed AI provider reset: {provider}")
        return provider
    
    return None

def parse_auto_respond_change(message):
    """
    Extract auto-response setting changes from bot confirmation messages.
    
    Auto-response changes are recorded in messages like:
    "Auto-response is now **enabled** in #channel"
    "Auto-response is now **disabled** in #channel"
    
    Args:
        message: Message dict from conversation history
        
    Returns:
        bool or None: True if enabled, False if disabled, None if not an auto-respond message
        
    Example:
        msg = {"role": "assistant", "content": "Auto-response is now **enabled** in #test"}
        setting = parse_auto_respond_change(msg)  # Returns: True
    """
    if message.get("role") != "assistant":
        return None
    
    content = message.get("content", "")
    
    # Pattern: "Auto-response is now **enabled/disabled** in #channel"
    if "Auto-response is now" in content:
        if "**enabled**" in content:
            logger.debug("Parsed auto-response change: enabled")
            return True
        elif "**disabled**" in content:
            logger.debug("Parsed auto-response change: disabled")
            return False
    
    return None

def parse_thinking_setting_change(message):
    """
    Extract thinking display setting changes from command response messages.
    
    Thinking setting changes are recorded in messages like:
    "DeepSeek thinking display **enabled** for #channel"
    "DeepSeek thinking display **disabled** for #channel"
    
    Args:
        message: Message dict from conversation history
        
    Returns:
        bool or None: True if enabled, False if disabled, None if not a thinking setting message
        
    Example:
        msg = {"role": "assistant", "content": "DeepSeek thinking display **enabled** for #test"}
        setting = parse_thinking_setting_change(msg)  # Returns: True
    """
    if message.get("role") != "assistant":
        return None
    
    content = message.get("content", "")
    
    # Pattern: "DeepSeek thinking display **enabled/disabled** for #channel"
    if "DeepSeek thinking display" in content:
        if "**enabled**" in content:
            logger.debug("Parsed thinking setting change: enabled")
            return True
        elif "**disabled**" in content:
            logger.debug("Parsed thinking setting change: disabled")
            return False
    
    return None

def extract_settings_by_type(channel_history_messages, setting_type):
    """
    Extract all occurrences of a specific setting type from history.
    
    This utility function extracts all instances of a particular setting type
    rather than just the most recent one. Useful for analysis and debugging.
    
    Args:
        channel_history_messages: List of message dicts from channel history
        setting_type: Type of setting to extract ('system_prompt', 'ai_provider', etc.)
        
    Returns:
        list: List of tuples (message_index, setting_value) for all occurrences
        
    Example:
        prompts = extract_settings_by_type(messages, 'system_prompt')
        # Returns: [(5, "You are helpful"), (12, "You are a pirate")]
    """
    parser_functions = {
        'system_prompt': parse_system_prompt_update,
        'ai_provider': parse_ai_provider_change,
        'auto_respond': parse_auto_respond_change,
        'thinking_enabled': parse_thinking_setting_change
    }
    
    if setting_type not in parser_functions:
        logger.error(f"Unknown setting type: {setting_type}")
        return []
    
    parser_func = parser_functions[setting_type]
    results = []
    
    for i, msg in enumerate(channel_history_messages):
        try:
            value = parser_func(msg)
            if value is not None:
                results.append((i, value))
        except Exception as e:
            logger.error(f"Error parsing {setting_type} from message {i}: {e}")
            continue
    
    logger.debug(f"Found {len(results)} occurrences of {setting_type}")
    return results

def get_parsing_statistics(channel_history_messages):
    """
    Get statistics about what settings can be parsed from history.
    
    This utility function analyzes the history to provide statistics about
    what configuration changes are recorded and can be restored.
    
    Args:
        channel_history_messages: List of message dicts from channel history
        
    Returns:
        dict: Statistics about parseable settings:
            {
                'total_messages': int,
                'system_prompt_updates': int,
                'ai_provider_changes': int,
                'auto_respond_changes': int,
                'thinking_changes': int,
                'total_settings_changes': int
            }
    """
    stats = {
        'total_messages': len(channel_history_messages),
        'system_prompt_updates': 0,
        'ai_provider_changes': 0,
        'auto_respond_changes': 0,
        'thinking_changes': 0,
        'total_settings_changes': 0
    }
    
    setting_types = [
        ('system_prompt_updates', parse_system_prompt_update),
        ('ai_provider_changes', parse_ai_provider_change),
        ('auto_respond_changes', parse_auto_respond_change),
        ('thinking_changes', parse_thinking_setting_change)
    ]
    
    for msg in channel_history_messages:
        for stat_key, parser_func in setting_types:
            try:
                if parser_func(msg) is not None:
                    stats[stat_key] += 1
                    stats['total_settings_changes'] += 1
            except Exception:
                continue
    
    logger.debug(f"Parsing statistics: {stats['total_settings_changes']} total setting changes in {stats['total_messages']} messages")
    
    return stats
