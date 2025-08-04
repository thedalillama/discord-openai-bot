"""
AI Providers package - factory for creating AI provider instances.
"""
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from config import DEBUG_MODE

def get_provider(provider_name=None, channel_id=None):
    """
    Factory function to get the appropriate AI provider.
    
    Args:
        provider_name: Optional provider name. If None, checks channel setting then config default.
        channel_id: Optional channel ID to check for channel-specific provider setting.
        
    Returns:
        AIProvider instance
    """
    # If no provider specified, check channel-specific setting first
    if provider_name is None and channel_id is not None:
        from utils.history_utils import get_ai_provider
        provider_name = get_ai_provider(channel_id)
    
    # If still no provider, fall back to config default
    if provider_name is None:
        from config import AI_PROVIDER
        provider_name = AI_PROVIDER
    
    provider_name = provider_name.lower()
    
    if DEBUG_MODE:
        print(f"[DEBUG] Provider factory selecting: {provider_name} (channel_id: {channel_id})")

    if provider_name == 'openai':
        return OpenAIProvider()
    elif provider_name == 'anthropic':
        return AnthropicProvider()
    else:
        raise ValueError(f"Unsupported AI provider: {provider_name}. Supported providers: openai, anthropic")

# For convenience, also export the base class
from .base import AIProvider
