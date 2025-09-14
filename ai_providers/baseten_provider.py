"""
BaseTen (DeepSeek R1) provider implementation.
CHANGES: Removed artificial truncation logic - let AI complete thoughts naturally
"""
from openai import OpenAI
from .base import AIProvider
from config import (BASETEN_DEEPSEEK_KEY, DEFAULT_TEMPERATURE, 
                    DEEPSEEK_MODEL, DEEPSEEK_CONTEXT_LENGTH, DEEPSEEK_MAX_TOKENS)
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
        self.model = DEEPSEEK_MODEL
        self.max_context_length = DEEPSEEK_CONTEXT_LENGTH
        self.max_response_tokens = DEEPSEEK_MAX_TOKENS
        self.supports_images = False      # Text-only model
        self.logger = get_logger('deepseek')
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using BaseTen's DeepSeek R1 model.
        
        Args:
            messages: List of message objects with role and content
            max_tokens: Maximum number of tokens in the response
            temperature: Creativity of the response (0.0-1.0)
            channel_id: Optional Discord channel ID for thinking display control
            
        Returns:
            str: The generated response text, with thinking tags filtered based on channel setting
        """
        self.logger.debug(f"Using DeepSeek provider (model: {self.model}) for API call")
        self.logger.debug(f"Max tokens being used: {max_tokens}")
        
        try:
            # Use default values if not specified
            if max_tokens is None:
                max_tokens = self.max_response_tokens  # Use DeepSeek's 8000 token limit
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
            
            # Log completion reason for debugging
            finish_reason = response.choices[0].finish_reason
            self.logger.debug(f"DeepSeek response finished with reason: {finish_reason}")
            
            # Filter thinking tags based on channel setting if channel_id provided
            filtered_response = raw_response
            if channel_id is not None:
                # Import here to avoid circular imports
                from commands.thinking_commands import get_thinking_enabled, filter_thinking_tags
                
                show_thinking = get_thinking_enabled(channel_id)
                filtered_response = filter_thinking_tags(raw_response, show_thinking)
                
                self.logger.debug(f"Applied thinking filter for channel {channel_id}: show_thinking={show_thinking}")
                self.logger.debug(f"Raw response contained <think> tags: {'<think>' in raw_response}")
                self.logger.debug(f"Response length: raw={len(raw_response)}, filtered={len(filtered_response)}")
                
                if not show_thinking and '<think>' in raw_response:
                    self.logger.info(f"Filtered thinking content from DeepSeek response (channel {channel_id})")
            else:
                self.logger.warning(f"No channel_id provided to DeepSeek provider - thinking filter not applied")
            
            self.logger.debug(f"DeepSeek API response received successfully")
            return filtered_response
            
        except Exception as e:
            self.logger.error(f"Error generating AI response from DeepSeek: {e}")
            raise e
