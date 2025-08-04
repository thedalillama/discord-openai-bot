"""
AI-related utility functions for the Discord bot.
"""
from ai_providers import get_provider

async def generate_ai_response(messages, max_tokens=None, temperature=None, channel_id=None):
    """
    Generate an AI response using the current provider.
    This function maintains the same interface as before but now uses the provider system.
    
    Args:
        messages: List of message objects with role and content
        max_tokens: Maximum number of tokens in the response
        temperature: Creativity of the response (0.0-1.0)
        channel_id: Optional Discord channel ID for channel-specific provider selection
        
    Returns:
        str: The generated response text
    """
    try:
        # Get the configured provider (checks channel-specific setting if channel_id provided)
        provider = get_provider(channel_id=channel_id)
        
        # Generate response using the provider
        return await provider.generate_ai_response(messages, max_tokens, temperature)
        
    except Exception as e:
        print(f"Error generating AI response: {e}")
        raise e  # Re-raise the exception to be handled by the caller
