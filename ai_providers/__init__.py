"""
AI Providers package - factory for creating AI provider instances.
"""
from .openai_provider import OpenAIProvider

def get_provider(provider_name=None):
    """
    Factory function to get the appropriate AI provider.
    
    Args:
        provider_name: Optional provider name. If None, uses config default.
        
    Returns:
        AIProvider instance
    """
    if provider_name is None:
        from config import AI_PROVIDER
        provider_name = AI_PROVIDER
    
    provider_name = provider_name.lower()
    
    if provider_name == 'openai':
        return OpenAIProvider()
    else:
        raise ValueError(f"Unsupported AI provider: {provider_name}")

# For convenience, also export the base class
from .base import AIProvider
