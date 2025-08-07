"""
OpenAI provider implementation.
"""
from openai import OpenAI
from .base import AIProvider
from config import OPENAI_API_KEY, AI_MODEL, DEFAULT_TEMPERATURE
from utils.logging_utils import get_logger

class OpenAIProvider(AIProvider):
    """OpenAI provider using chat completions API"""
    
    def __init__(self):
        super().__init__()
        self.name = "openai"
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = AI_MODEL
        self.max_context_length = 128000  # GPT-4o context window
        self.max_response_tokens = 300    # Our current safe limit
        self.supports_images = True       # For future use
        self.logger = get_logger('openai')
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None):
        """
        Generate an AI response using OpenAI's chat completions API.
        This is the same logic that was in ai_utils.py
        """

        self.logger.debug(f"Using OpenAI provider (model: {self.model}) for API call")

        try:
            # Use default values if not specified
            if max_tokens is None:
                max_tokens = self.max_response_tokens
            if temperature is None:
                temperature = DEFAULT_TEMPERATURE
                
            # Log the system prompt being sent to API
            system_prompt = None
            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                    break
            
            if system_prompt:
                self.logger.debug(f"Sending system prompt to OpenAI API: '{system_prompt}'")
            
            self.logger.debug(f"Number of messages: {len(messages)}")
                
            # Using the model specified in config (same as before)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                n=1,
                temperature=temperature
            )
            
            raw_response = response.choices[0].message.content.strip()
            finish_reason = response.choices[0].finish_reason
            
            # Check if the response was cut off due to length (same logic as before)
            if finish_reason == "length":
                self.logger.warning(f"Response was truncated due to token limit")
                return raw_response + "\n\n[Note: Response was truncated due to length. Feel free to ask for more details.]"
            
            self.logger.debug(f"OpenAI API response received successfully")
            return raw_response
        except Exception as e:
            self.logger.error(f"Error generating AI response from OpenAI: {e}")
            raise e  # Re-raise the exception to be handled by the caller
