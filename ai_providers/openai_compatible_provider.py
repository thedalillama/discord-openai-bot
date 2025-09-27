# ai_providers/openai_compatible_provider.py
# Version 1.0.0
"""
Generic OpenAI-compatible provider implementation.
Works with any API that follows the OpenAI client interface (DeepSeek, OpenRouter, etc.).

FEATURES:
- Configurable base URL and API key via environment variables
- Supports any OpenAI-compatible model
- Async-safe execution with thread pool executor
- Comprehensive logging and error handling
- Thinking tag filtering for DeepSeek models
"""
import asyncio
import concurrent.futures
from openai import OpenAI
from .base import AIProvider
from config import (
    OPENAI_COMPATIBLE_API_KEY, OPENAI_COMPATIBLE_BASE_URL, 
    OPENAI_COMPATIBLE_MODEL, DEFAULT_TEMPERATURE,
    OPENAI_COMPATIBLE_CONTEXT_LENGTH, OPENAI_COMPATIBLE_MAX_TOKENS
)
from utils.logging_utils import get_logger

class OpenAICompatibleProvider(AIProvider):
    """Generic OpenAI-compatible provider for any API following OpenAI standard"""
    
    def __init__(self):
        super().__init__()
        self.name = "openai_compatible"
        
        # Validate configuration
        if not OPENAI_COMPATIBLE_API_KEY:
            raise ValueError("OPENAI_COMPATIBLE_API_KEY environment variable is required")
        if not OPENAI_COMPATIBLE_BASE_URL:
            raise ValueError("OPENAI_COMPATIBLE_BASE_URL environment variable is required") 
        if not OPENAI_COMPATIBLE_MODEL:
            raise ValueError("OPENAI_COMPATIBLE_MODEL environment variable is required")
            
        self.client = OpenAI(
            api_key=OPENAI_COMPATIBLE_API_KEY,
            base_url=OPENAI_COMPATIBLE_BASE_URL
        )
        self.model = OPENAI_COMPATIBLE_MODEL
        self.max_context_length = OPENAI_COMPATIBLE_CONTEXT_LENGTH
        self.max_response_tokens = OPENAI_COMPATIBLE_MAX_TOKENS
        self.supports_images = False  # Generic provider assumes text-only
        self.logger = get_logger('openai_compatible')
        
        # Log provider configuration (without sensitive API key)
        self.logger.info(f"Initialized OpenAI-compatible provider:")
        self.logger.info(f"  Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
        self.logger.info(f"  Model: {OPENAI_COMPATIBLE_MODEL}")
        self.logger.info(f"  Max tokens: {OPENAI_COMPATIBLE_MAX_TOKENS}")
    
    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using the configured OpenAI-compatible API.
        
        Args:
            messages: List of message objects with role and content
            max_tokens: Maximum number of tokens in the response
            temperature: Creativity of the response (0.0-1.0)
            channel_id: Optional Discord channel ID for thinking display control
            
        Returns:
            str: The generated response text, with thinking tags filtered if applicable
        """
        self.logger.debug(f"Using OpenAI-compatible provider (model: {self.model}) for API call")
        self.logger.debug(f"Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
        self.logger.debug(f"Max tokens being used: {max_tokens}")
        
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
                self.logger.debug(f"Sending system prompt to API: '{system_prompt}'")
            
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
            
            # Use async executor to prevent Discord heartbeat blocking
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=api_messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=1,
                        presence_penalty=0,
                        frequency_penalty=0,
                        stop=[]
                    )
                )
            
            # Extract the response text
            raw_response = response.choices[0].message.content.strip()
            
            # Log completion reason for debugging
            finish_reason = response.choices[0].finish_reason
            self.logger.debug(f"API response finished with reason: {finish_reason}")
            
            # Filter thinking tags if this appears to be a DeepSeek model
            filtered_response = raw_response
            if channel_id is not None and self._is_deepseek_model():
                # Import here to avoid circular imports
                from commands.thinking_commands import get_thinking_enabled, filter_thinking_tags
                
                show_thinking = get_thinking_enabled(channel_id)
                filtered_response = filter_thinking_tags(raw_response, show_thinking)
                
                self.logger.debug(f"Applied thinking filter for channel {channel_id}: show_thinking={show_thinking}")
                self.logger.debug(f"Raw response contained <think> tags: {'<think>' in raw_response}")
                self.logger.debug(f"Response length: raw={len(raw_response)}, filtered={len(filtered_response)}")
                
                if not show_thinking and '<think>' in raw_response:
                    self.logger.info(f"Filtered thinking content from response (channel {channel_id})")
            elif self._is_deepseek_model():
                self.logger.warning(f"No channel_id provided to DeepSeek-like model - thinking filter not applied")
            
            self.logger.debug(f"API response received successfully")
            return filtered_response
            
        except Exception as e:
            self.logger.error(f"Error generating AI response from OpenAI-compatible API: {e}")
            self.logger.error(f"Model: {self.model}, Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
            raise e
    
    def _is_deepseek_model(self):
        """Check if the configured model appears to be a DeepSeek model based on naming patterns"""
        model_lower = self.model.lower()
        return ('deepseek' in model_lower or 
                'deepseek-reasoner' in model_lower or 
                'deepseek-chat' in model_lower or
                'deepseek-ai' in model_lower)
