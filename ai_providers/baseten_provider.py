"""
BaseTen (DeepSeek R1) provider implementation.
"""
from openai import OpenAI
from .base import AIProvider
from config import BASETEN_DEEPSEEK_KEY, DEFAULT_TEMPERATURE
from utils.logging_utils import get_logger

class DeepSeekProvider(AIProvider):
    """BaseTen DeepSeek R1 provider using OpenAI-compatible API"""
    
    def __init__(self):
        super().__init__()
        self.name = "deepseek"
        self.client = OpenAI(
            api_key=BASETEN_DEEPSEEK_KEY,
            base_url="https://inference.baseten.co/v1"
        )
        self.model = "deepseek-ai/DeepSeek-R1"
        self.max_context_length = 64000  # DeepSeek R1 context window
        self.max_response_tokens = 8000   # Max tokens from example
        self.supports_images = False      # Text-only model
        self.logger = get_logger('deepseek')
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None):
        """
        Generate an AI response using BaseTen's DeepSeek R1 model.
        """
        self.logger.debug(f"Using DeepSeek provider (model: {self.model}) for API call")
        
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
                self.logger.debug(f"Sending system prompt to DeepSeek API: '{system_prompt}'")
            
            self.logger.debug(f"Number of messages: {len(messages)}")
            
            # Convert messages to standard OpenAI format
            api_messages = []
            for msg in messages:
                if msg["role"] in ["system", "user", "assistant"]:
                    # For user messages, include the name info in content if it exists
                    content = msg["content"]
                    if msg["role"] == "user" and "name" in msg:
                        # Embed name in content if not already there
                        if not content.startswith(msg["name"]):
                            content = f"{msg['name']}: {content}"
                    
                    api_messages.append({
                        "role": msg["role"],
                        "content": content
                    })
            
            # Create the completion (non-streaming for consistency)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1,
                presence_penalty=0,
                frequency_penalty=0,
                stop=[]
            )
            
            # Extract the response text
            raw_response = response.choices[0].message.content.strip()
            
            # Check if the response was cut off due to length
            if response.choices[0].finish_reason == "length":
                self.logger.warning(f"Response was truncated due to token limit")
                raw_response += "\n\n[Note: Response was truncated due to length. Feel free to ask for more details.]"
            
            self.logger.debug(f"DeepSeek API response received successfully")
            return raw_response
            
        except Exception as e:
            self.logger.error(f"Error generating AI response from DeepSeek: {e}")
            raise e
