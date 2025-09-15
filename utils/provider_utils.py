# utils/provider_utils.py
# Version 1.0.0
"""
Provider utility functions for Discord bot.
Handles AI provider parsing, validation, and override logic.
"""
from utils.logging_utils import get_logger

logger = get_logger('provider_utils')

# Valid AI providers supported by the bot
VALID_PROVIDERS = ['openai', 'anthropic', 'deepseek']

def parse_provider_override(content):
    """
    Extract provider override from message start.
    
    Args:
        content (str): Message content to parse
        
    Returns:
        tuple: (provider_name, clean_content) or (None, original_content)
        
    Examples:
        parse_provider_override("openai, draw a cat") -> ("openai", "draw a cat")
        parse_provider_override("hello world") -> (None, "hello world")
        parse_provider_override("ANTHROPIC, write a poem") -> ("anthropic", "write a poem")
    """
    if not content or not isinstance(content, str):
        return None, content
    
    content_lower = content.lower()
    
    for provider in VALID_PROVIDERS:
        prefix = f"{provider},"
        if content_lower.startswith(prefix):
            # Extract clean content after provider name and comma
            clean_content = content[len(prefix):].strip()
            logger.debug(f"Provider override detected: {provider}")
            logger.debug(f"Clean content: {clean_content}")
            return provider, clean_content
    
    return None, content

def validate_provider_name(provider_name):
    """
    Validate if a provider name is supported.
    
    Args:
        provider_name (str): Provider name to validate
        
    Returns:
        bool: True if provider is valid, False otherwise
    """
    if not provider_name or not isinstance(provider_name, str):
        return False
    
    return provider_name.lower() in VALID_PROVIDERS

def normalize_provider_name(provider_name):
    """
    Normalize provider name to lowercase standard format.
    
    Args:
        provider_name (str): Provider name to normalize
        
    Returns:
        str or None: Normalized provider name, or None if invalid
    """
    if not validate_provider_name(provider_name):
        return None
    
    return provider_name.lower()

def get_valid_providers():
    """
    Get list of all valid provider names.
    
    Returns:
        list[str]: List of valid provider names
    """
    return VALID_PROVIDERS.copy()

def format_provider_list(separator=", "):
    """
    Format the list of valid providers for display.
    
    Args:
        separator (str): Separator between provider names (default: ", ")
        
    Returns:
        str: Formatted provider list
    """
    return separator.join(VALID_PROVIDERS)

def is_provider_addressing(content):
    """
    Check if a message contains provider addressing without parsing the full content.
    Useful for quick checks without full parsing overhead.
    
    Args:
        content (str): Message content to check
        
    Returns:
        bool: True if message starts with provider addressing, False otherwise
    """
    if not content or not isinstance(content, str):
        return False
    
    provider_override, _ = parse_provider_override(content)
    return provider_override is not None

def extract_addressing_info(content):
    """
    Extract comprehensive addressing information from message content.
    
    Args:
        content (str): Message content to analyze
        
    Returns:
        dict: Dictionary with addressing information:
            - 'has_override': bool
            - 'provider': str or None  
            - 'clean_content': str
            - 'original_content': str
    """
    provider_override, clean_content = parse_provider_override(content)
    
    return {
        'has_override': provider_override is not None,
        'provider': provider_override,
        'clean_content': clean_content,
        'original_content': content
    }
