# utils/ai_utils.py
# Version 1.0.0
"""
AI-related utility functions for the Discord bot.

CHANGES v1.0.0: Added version header (SOW v2.20.0)
- ADDED: Version header for tracking
- NOTE: provider_override parameter added in earlier unversioned change
"""
from ai_providers import get_provider
from utils.logging_utils import get_logger

logger = get_logger('ai')


async def generate_ai_response(messages, max_tokens=None, temperature=None,
                                channel_id=None, provider_override=None):
    """
    Generate an AI response using the current provider or override provider.

    Args:
        messages: List of message dicts with role and content
        max_tokens: Maximum tokens in response
        temperature: Creativity (0.0-1.0)
        channel_id: Discord channel ID for provider selection and behavior
        provider_override: Optional provider name to override channel/default

    Returns:
        str or dict: Response from provider (format depends on provider)
    """
    try:
        logger.debug(f"Generating AI response for channel {channel_id}")

        if provider_override:
            logger.info(f"Using provider override: {provider_override}")
            provider = get_provider(provider_name=provider_override, channel_id=channel_id)
        else:
            provider = get_provider(channel_id=channel_id)

        logger.debug(f"Using {provider.name} provider for response generation")

        response = await provider.generate_ai_response(
            messages, max_tokens, temperature, channel_id
        )

        logger.debug(f"AI response generated successfully (length: {len(str(response))} chars)")
        return response

    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        raise e
