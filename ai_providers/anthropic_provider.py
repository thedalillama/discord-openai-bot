"""
Anthropic (Claude) provider implementation.
CHANGES: Removed artificial truncation logic - let AI complete thoughts naturally
"""
import anthropic
from .base import AIProvider
from config import (ANTHROPIC_API_KEY, DEFAULT_TEMPERATURE,
                    ANTHROPIC_MODEL, ANTHROPIC_CONTEXT_LENGTH, ANTHROPIC_MAX_TOKENS)
from utils.logging_utils import get_logger

class AnthropicProvider(AIProvider):
    """Anthropic Claude provider using messages API"""
    
    def __init__(self):
        super().__init__()
        self.name = "anthropic"
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = ANTHROPIC_MODEL
        self.max_context_length = ANTHROPIC_CONTEXT_LENGTH
        self.max_response_tokens = ANTHROPIC_MAX_TOKENS
        self.supports_images = True       # Claude supports vision
        self.logger = get_logger('anthropic')
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using Anthropic's messages API.
        
        Args:
            messages: List of message objects with role and content
            max_tokens: Maximum number of tokens in the response
            temperature: Creativity of the response (0.0-1.0)
            channel_id: Optional Discord channel ID (not used by Anthropic provider)
        """

        self.logger.debug(f"Using Anthropic provider (model: {self.model}) for API call")

        try:
            # Use default values if not specified
            if max_tokens is None:
                max_tokens = self.max_response_tokens
            if temperature is None:
                temperature = DEFAULT_TEMPERATURE
        
            # Convert messages to Anthropic format
            claude_messages = []
            system_prompt = None
        
            for msg in messages:
                if msg["role"] == "system":
                    # Use the last system message as the system prompt
                    system_prompt = msg["content"]
                    self.logger.debug(f"Extracted system prompt: '{system_prompt}'")
                elif msg["role"] in ["user", "assistant"]:
                    # For user messages, include the name info in content if it exists
                    content = msg["content"]
                    if msg["role"] == "user" and "name" in msg:
                        # Claude doesn't have 'name' field, so embed it in content
                        content = f"{msg['name']}: {content}" if not content.startswith(msg['name']) else content
                
                    claude_messages.append({
                        "role": msg["role"],
                        "content": content
                    })
            
            # Log the final system prompt being sent to API
            self.logger.debug(f"Sending system prompt to Anthropic API: '{system_prompt}'")
            self.logger.debug(f"Number of messages: {len(claude_messages)}")
       
            # Create the completion
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=claude_messages
            )
        
            raw_response = response.content[0].text.strip()
            
            # Log completion reason for debugging
            finish_reason = response.stop_reason
            self.logger.debug(f"Anthropic response finished with reason: {finish_reason}")

            self.logger.debug(f"Anthropic API response received successfully")
            return raw_response
        
        except Exception as e:
            self.logger.error(f"Error generating AI response from Anthropic: {e}")
            raise e
