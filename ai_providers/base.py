"""
Base class for AI providers.
"""
from abc import ABC, abstractmethod

class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    def __init__(self):
        self.name = "unknown"
        self.max_context_length = 4096
        self.max_response_tokens = 300
        self.supports_images = False
    
    @abstractmethod
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None):
        """Generate AI response from messages"""
        pass
    
    def get_effective_max_tokens(self, max_tokens=None):
        """Get the effective max tokens, respecting provider limits"""
        if max_tokens is None:
            return self.max_response_tokens
        return min(max_tokens, self.max_response_tokens)
    
    def validate_context_length(self, messages):
        """Check if messages fit within context window"""
        # Simple estimation - we can improve this later
        total_chars = sum(len(str(msg.get('content', ''))) for msg in messages)
        estimated_tokens = total_chars // 4  # Rough estimate
        return estimated_tokens <= self.max_context_length
