# utils/history/realtime_settings_parser.py
# Version 1.0.0
"""
Real-time settings parsing during Discord message loading.

This module provides real-time parsing of bot configuration settings as Discord
messages are being loaded. It detects the most recent settings and applies them
immediately to in-memory storage, stopping parsing once each setting type is found.

This is part of the Configuration Persistence feature architecture and provides
more efficient settings restoration than post-processing approaches.

Key Features:
- Parse settings in reverse chronological order (newest first)
- Stop parsing each setting type once found and applied
- Apply settings immediately to in-memory dictionaries
- Handle errors gracefully without stopping message loading
- Support for system prompts, AI providers, auto-respond, thinking settings
"""
import datetime
from utils.logging_utils import get_logger
from .storage import add_message_to_history
from .message_processing import create_system_update_message
from .prompts import channel_system_prompts

logger = get_logger('history.realtime_settings_parser')

async def parse_settings_during_load(messages, channel_id):
    """
    Parse settings from Discord messages in real-time during loading.
    
    This function processes messages in reverse chronological order (newest first)
    to find the most recent settings. Once a setting type is found and applied,
    parsing stops for that type to optimize performance.
    
    Args:
        messages: List of Discord message objects (should be in chronological order)
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
    logger.debug(f"Starting real-time settings parsing for {len(messages)} messages in channel {channel_id}")
    
    # Track which settings have been found to enable early termination
    settings_found = {
        'system_prompt': False,
        'ai_provider': False,
        'auto_respond': False,
        'thinking_enabled': False
    }
    
    # Process messages in reverse order (newest first) for efficiency
    for i, message in enumerate(reversed(messages)):
        try:
            # Early termination if all settings found
            if all(settings_found.values()):
                logger.debug(f"All settings found, stopping parsing after {i+1} messages")
                break
            
            # Parse system prompt updates (highest priority)
            if not settings_found['system_prompt']:
                if _parse_and_apply_system_prompt(message, channel_id):
                    settings_found['system_prompt'] = True
                    logger.debug(f"Found system prompt in message {i+1}")
            
            # Parse AI provider changes
            if not settings_found['ai_provider']:
                if _parse_and_apply_ai_provider(message, channel_id):
                    settings_found['ai_provider'] = True
                    logger.debug(f"Found AI provider change in message {i+1}")
            
            # Parse auto-respond setting changes
            if not settings_found['auto_respond']:
                if _parse_and_apply_auto_respond(message, channel_id):
                    settings_found['auto_respond'] = True
                    logger.debug(f"Found auto-respond setting in message {i+1}")
            
            # Parse thinking display setting changes
            if not settings_found['thinking_enabled']:
                if _parse_and_apply_thinking_setting(message, channel_id):
                    settings_found['thinking_enabled'] = True
                    logger.debug(f"Found thinking setting in message {i+1}")
                    
        except Exception as e:
            logger.error(f"Error parsing settings from message {i+1}: {e}")
            # Continue parsing other messages despite errors
            continue
    
    total_found = sum(settings_found.values())
    logger.info(f"Real-time settings parsing complete for channel {channel_id}: {total_found} settings found and applied")
    
    return {
        **settings_found,
        'total_found': total_found
    }

def _parse_and_apply_system_prompt(message, channel_id):
    """
    Parse and apply system prompt from a Discord message.
    
    Handles both setprompt commands and system prompt update confirmations.
    
    Args:
        message: Discord message object
        channel_id: Discord channel ID
        
    Returns:
        bool: True if system prompt was found and applied, False otherwise
    """
    try:
        # Handle unprocessed setprompt commands
        if message.content.startswith('!setprompt '):
            prompt_text = message.content[len('!setprompt '):].strip()
            if prompt_text:
                # Apply directly to storage
                channel_system_prompts[channel_id] = prompt_text
                
                # Also add to history for consistency
                system_update = create_system_update_message(prompt_text)
                add_message_to_history(channel_id, system_update)
                
                logger.info(f"Applied system prompt from setprompt command: {prompt_text[:50]}...")
                return True
        
        # Handle system prompt update confirmations from bot
        elif (hasattr(message, 'author') and 
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
    Parse and apply AI provider setting from a Discord message.
    
    TODO: Implement parsing of AI provider change confirmations.
    
    Args:
        message: Discord message object
        channel_id: Discord channel ID
        
    Returns:
        bool: True if AI provider was found and applied, False otherwise
    """
    # TODO: Implement AI provider parsing
    # Look for messages like "AI provider for #channel changed from openai to deepseek"
    logger.debug("AI provider parsing not yet implemented (dummy function)")
    return False

def _parse_and_apply_auto_respond(message, channel_id):
    """
    Parse and apply auto-respond setting from a Discord message.
    
    TODO: Implement parsing of auto-respond toggle confirmations.
    
    Args:
        message: Discord message object
        channel_id: Discord channel ID
        
    Returns:
        bool: True if auto-respond setting was found and applied, False otherwise
    """
    # TODO: Implement auto-respond parsing
    # Look for messages like "Auto-response is now **enabled** in #channel"
    logger.debug("Auto-respond parsing not yet implemented (dummy function)")
    return False

def _parse_and_apply_thinking_setting(message, channel_id):
    """
    Parse and apply thinking display setting from a Discord message.
    
    TODO: Implement parsing of thinking setting confirmations.
    
    Args:
        message: Discord message object
        channel_id: Discord channel ID
        
    Returns:
        bool: True if thinking setting was found and applied, False otherwise
    """
    # TODO: Implement thinking setting parsing
    # Look for messages like "DeepSeek thinking display **enabled** for #channel"
    logger.debug("Thinking setting parsing not yet implemented (dummy function)")
    return False

def extract_prompt_from_update_message(message):
    """
    Extract system prompt text from a "System prompt updated" confirmation message.
    
    This function parses bot confirmation messages that contain system prompt updates
    to restore the actual prompt text for history tracking.
    
    Args:
        message: Discord message object containing system prompt update confirmation
        
    Returns:
        str or None: The system prompt text, or None if extraction failed
        
    Example:
        Input message: "System prompt updated for #channel. New prompt: **You are helpful**"
        Output: "You are helpful"
    """
    try:
        content = message.content
        
        # Extract the prompt from the confirmation message format
        # Expected format: "System prompt updated for #channel. New prompt: **[prompt text]**"
        if "New prompt:" not in content:
            logger.debug(f"System prompt update message missing 'New prompt:' section")
            return None
            
        prompt_text = content.split("New prompt:", 1)[1].strip()
        
        # Remove any Discord formatting (like ** for bold)
        prompt_text = prompt_text.replace("**", "").strip()
        
        if not prompt_text:
            logger.debug(f"Extracted prompt text was empty after cleaning")
            return None
        
        logger.debug(f"Successfully extracted prompt from update message: {prompt_text[:50]}...")
        return prompt_text
        
    except Exception as e:
        logger.error(f"Error extracting prompt from update message: {e}")
        logger.debug(f"Update message content: {message.content}")
        return None
