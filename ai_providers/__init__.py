# ai_providers/__init__.py
# Version 1.3.0
"""
AI Providers package - factory for creating AI provider instances.

CHANGES v1.3.0: Provider singleton caching (SOW v2.22.0)
- ADDED: _provider_cache module-level dictionary
- MODIFIED: get_provider() checks cache before instantiating new provider
- ADDED: clear_provider_cache() utility for testing and future use
- FIXED: Prevents httpx client garbage collection RuntimeError from new
  instances being created and destroyed on every API call

CHANGES v1.2.0: Removed BaseTen provider and updated deepseek routing
- REMOVED: BaseTen DeepSeekProvider import and usage
- ADDED: OpenAICompatibleProvider import for deepseek routing
- UPDATED: deepseek provider routing to use OpenAI-compatible provider
- ENHANCED: Debug logging for provider selection transparency
- MAINTAINED: All existing provider functionality and backward compatibility
"""
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .openai_compatible_provider import OpenAICompatibleProvider
from .base import AIProvider
from utils.logging_utils import get_logger

logger = get_logger('ai_providers')

# Singleton cache — one instance per provider type for the lifetime of the bot.
# Prevents httpx client garbage collection RuntimeError caused by creating and
# destroying provider instances on every API call.
_provider_cache = {}


def get_provider(provider_name=None, channel_id=None):
    """
    Factory function to get the appropriate AI provider.

    Returns cached provider instances — each provider type is instantiated
    once and reused across all API calls.

    Args:
        provider_name: Optional provider name. If None, checks channel
                       setting then config default.
        channel_id: Optional channel ID for channel-specific provider selection.

    Returns:
        AIProvider: Cached provider instance
    """
    if provider_name is None and channel_id is not None:
        from utils.history import get_ai_provider
        provider_name = get_ai_provider(channel_id)

    if provider_name is None:
        from config import AI_PROVIDER
        provider_name = AI_PROVIDER

    provider_name = provider_name.lower()

    logger.debug(f"Provider factory selecting: {provider_name} (channel_id: {channel_id})")

    if provider_name not in _provider_cache:
        if provider_name == 'openai':
            logger.info(f"Instantiating OpenAIProvider (first use)")
            _provider_cache[provider_name] = OpenAIProvider()
        elif provider_name == 'anthropic':
            logger.info(f"Instantiating AnthropicProvider (first use)")
            _provider_cache[provider_name] = AnthropicProvider()
        elif provider_name == 'deepseek':
            logger.info(f"Instantiating OpenAICompatibleProvider for deepseek (first use)")
            _provider_cache[provider_name] = OpenAICompatibleProvider()
        else:
            error_msg = (
                f"Unsupported AI provider: {provider_name}. "
                f"Supported providers: openai, anthropic, deepseek"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
    else:
        logger.debug(f"Returning cached {provider_name} provider instance")

    return _provider_cache[provider_name]


def clear_provider_cache():
    """
    Clear all cached provider instances.
    Primarily for testing. Also useful if provider configuration changes
    at runtime and instances need to be re-initialized.
    """
    _provider_cache.clear()
    logger.info("Provider cache cleared")
