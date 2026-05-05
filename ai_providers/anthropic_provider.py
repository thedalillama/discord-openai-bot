# ai_providers/anthropic_provider.py
# Version 1.2.0
"""
Anthropic (Claude) provider implementation.

CHANGES v1.2.0: Strip trailing assistant messages before API call.
  Anthropic returns empty content[] when the last message is an assistant turn.
  Caused by context ordering where Layer 2 + selected can end on an assistant.

CHANGES v1.1.0: Token usage logging (SOW v2.23.0)
CHANGES v1.0.0: Added async executor wrapper (SOW v2.21.0)
"""
import asyncio
import concurrent.futures
import anthropic
from .base import AIProvider
from config import (ANTHROPIC_API_KEY, DEFAULT_TEMPERATURE,
                    ANTHROPIC_MODEL, ANTHROPIC_CONTEXT_LENGTH, ANTHROPIC_MAX_TOKENS)
from utils.logging_utils import get_logger
from utils.context_manager import record_usage


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider using messages API"""

    def __init__(self):
        super().__init__()
        self.name = "anthropic"
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = ANTHROPIC_MODEL
        self.max_context_length = ANTHROPIC_CONTEXT_LENGTH
        self.max_response_tokens = ANTHROPIC_MAX_TOKENS
        self.supports_images = True
        self.logger = get_logger('anthropic')

    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using Anthropic's messages API.

        Args:
            messages: List of message dicts with role and content
            max_tokens: Maximum tokens in response
            temperature: Creativity (0.0-1.0)
            channel_id: Optional Discord channel ID

        Returns:
            str: The generated response text
        """
        self.logger.debug(f"Using Anthropic provider (model: {self.model}) for API call")

        try:
            if max_tokens is None:
                max_tokens = self.max_response_tokens
            if temperature is None:
                temperature = DEFAULT_TEMPERATURE

            # Convert messages to Anthropic format
            claude_messages = []
            system_prompt = None

            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                    self.logger.debug(f"Extracted system prompt: '{system_prompt}'")
                elif msg["role"] in ["user", "assistant"]:
                    content = msg["content"]
                    if msg["role"] == "user" and "name" in msg:
                        if not content.startswith(msg["name"]):
                            content = f"{msg['name']}: {content}"
                    claude_messages.append({
                        "role": msg["role"],
                        "content": content
                    })

            # Anthropic returns empty content[] if the last message is assistant.
            while claude_messages and claude_messages[-1]["role"] == "assistant":
                self.logger.warning("Dropping trailing assistant message before Anthropic call")
                claude_messages.pop()
            if not claude_messages:
                raise ValueError("No user messages remaining after stripping trailing assistant turns")

            self.logger.debug(f"Sending system prompt to Anthropic API: '{system_prompt}'")
            self.logger.debug(f"Number of messages: {len(claude_messages)}")

            # CRITICAL: Do NOT remove this executor wrapper.
            # Synchronous API calls block the Discord event loop, causing
            # heartbeat failures, WebSocket disconnection, and bot crashes
            # under slow or large responses. Confirmed via production crash
            # during v2.20.0 development. See HANDOFF.md for details.
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: self.client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system_prompt,
                        messages=claude_messages
                    )
                )

            raw_response = response.content[0].text.strip()
            finish_reason = response.stop_reason
            self.logger.debug(f"Anthropic response finished with reason: {finish_reason}")
            self.logger.debug(f"Anthropic API response received successfully")

            # Log token usage from API response
            usage = getattr(response, 'usage', None)
            if usage:
                record_usage(
                    channel_id, self.name,
                    getattr(usage, 'input_tokens', 0),
                    getattr(usage, 'output_tokens', 0)
                )
            else:
                self.logger.debug("No usage data in Anthropic API response")

            return raw_response

        except Exception as e:
            self.logger.error(f"Error generating AI response from Anthropic: {e}")
            raise e
