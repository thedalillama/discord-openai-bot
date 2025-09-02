"""
AI-related utility functions for the Discord bot.
"""
from ai_providers import get_provider
from utils.logging_utils import get_logger

# Get logger for AI utilities
logger = get_logger('ai')

async def generate_ai_response(messages, max_tokens=None, temperature=None, channel_id=None):
    """
    Generate an AI response using the current provider.
    This function maintains the same interface as before but now uses the provider system.
    
    Args:
        messages: List of message objects with role and content
        max_tokens: Maximum number of tokens in the response
        temperature: Creativity of the response (0.0-1.0)
        channel_id: Optional Discord channel ID for channel-specific provider selection and behavior
        
    Returns:
        str: The generated response text
    """
    try:
        logger.debug(f"Generating AI response for channel {channel_id}")
        
        # Get the configured provider (checks channel-specific setting if channel_id provided)
        provider = get_provider(channel_id=channel_id)
        
        logger.debug(f"Using {provider.name} provider for response generation")
        
        # Generate response using the provider (now passing channel_id through)
        response = await provider.generate_ai_response(messages, max_tokens, temperature, channel_id)
        
        logger.debug(f"AI response generated successfully (length: {len(str(response))} chars)")
        return response
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        raise e  # Re-raise the exception to be handled by the caller
