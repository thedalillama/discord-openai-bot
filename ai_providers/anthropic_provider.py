"""
Anthropic (Claude) provider implementation.
"""
import anthropic
from .base import AIProvider
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, DEFAULT_TEMPERATURE, DEBUG_MODE

class AnthropicProvider(AIProvider):
    """Anthropic Claude provider using messages API"""
    
    def __init__(self):
        super().__init__()
        self.name = "anthropic"
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = ANTHROPIC_MODEL      # Use config.py variable
        self.max_context_length = 200000  # Claude has 200k context window
        self.max_response_tokens = 300    # Keep same limit as OpenAI for consistency
        self.supports_images = True       # Claude supports vision
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None):
        """
        Generate an AI response using Anthropic's messages API.
        """

        if DEBUG_MODE:
            print(f"[DEBUG] Using Anthropic provider (model: {self.model}) for API call")

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
       
            # Create the completion
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=claude_messages
            )
        
            raw_response = response.content[0].text.strip()
        
            # Check if the response was cut off due to length
            if response.stop_reason == "max_tokens":
                print(f"Response was truncated due to token limit")
                return raw_response + "\n\n[Note: Response was truncated due to length. Feel free to ask for more details.]"

            return raw_response
        
        except Exception as e:
            print(f"Error generating AI response from Anthropic: {e}")
            raise e
