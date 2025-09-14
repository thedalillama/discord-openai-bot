"""
AI-related utility functions for the Discord bot.
CHANGES: Added provider_override parameter to support direct provider addressing
"""
from ai_providers import get_provider
from utils.logging_utils import get_logger

# Get logger for AI utilities
logger = get_logger('ai')

async def generate_ai_response(messages, max_tokens=None, temperature=None, channel_id=None, provider_override=None):
    """
    Generate an AI response using the current provider or override provider.
    
    Args:
        messages: List of message objects with role and content
        max_tokens: Maximum number of tokens in the response
        temperature: Creativity of the response (0.0-1.0)
        channel_id: Optional Discord channel ID for channel-specific provider selection and behavior
        provider_override: Optional provider name to override channel/default settings
        
    Returns:
        str or dict: The generated response (format depends on provider)
    """
    try:
        logger.debug(f"Generating AI response for channel {channel_id}")
        
        # Determine which provider to use
        if provider_override:
            # Use override provider (from direct addressing like "openai, draw a picture")
            logger.info(f"Using provider override: {provider_override}")
            provider = get_provider(provider_name=provider_override, channel_id=channel_id)
        else:
            # Use channel-specific or default provider
            provider = get_provider(channel_id=channel_id)
        
        logger.debug(f"Using {provider.name} provider for response generation")
        
        # Generate response using the selected provider
        response = await provider.generate_ai_response(messages, max_tokens, temperature, channel_id)
        
        logger.debug(f"AI response generated successfully (length: {len(str(response))} chars)")
        return response
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        raise e  # Re-raise the exception to be handled by the caller
