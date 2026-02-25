# ai_providers/openai_compatible_provider.py
# Version 1.1.2
"""
Generic OpenAI-compatible provider implementation.
Works with any API that follows the OpenAI client interface (DeepSeek, OpenRouter, etc.).

CHANGES v1.1.2: Add critical executor wrapper warning comment (SOW v2.21.0)
- ADDED: Warning comment on executor block explaining why it must not be removed

CHANGES v1.1.1: Fix reasoning/answer split boundary (SOW v2.20.0 bugfix)
- CHANGED: REASONING_SEPARATOR added as explicit boundary between reasoning
  block and answer — prevents reasoning paragraphs from being mistaken for
  the split point when reasoning_content contains blank lines

CHANGES v1.1.0: DeepSeek reasoning_content display (SOW v2.20.0)
- REMOVED: filter_thinking_tags() / <think> tag logic — dead code for DeepSeek official API
- ADDED: reasoning_content extraction from DeepSeek reasoner responses
- ADDED: [DEEPSEEK_REASONING]: prefixed message prepended to content when thinking enabled
- ADDED: Full reasoning_content logged at INFO when thinking on, DEBUG when off
- ADDED: _build_reasoning_response() helper

FEATURES:
- Configurable base URL and API key via environment variables
- Supports any OpenAI-compatible model
- Async-safe execution with thread pool executor
- Comprehensive logging and error handling
- DeepSeek reasoning_content extraction and display
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

# Prefix for reasoning content messages — unique enough to never appear in
# normal conversation. Used by is_history_output() to filter reasoning from
# channel_history at runtime, load time, and API payload build.
REASONING_PREFIX = "[DEEPSEEK_REASONING]:"

# Separator between reasoning block and answer. Must be unique enough to
# never appear in reasoning content or normal conversation.
REASONING_SEPARATOR = "\n[DEEPSEEK_ANSWER]:\n"


class OpenAICompatibleProvider(AIProvider):
    """Generic OpenAI-compatible provider for any API following OpenAI standard"""

    def __init__(self):
        super().__init__()
        self.name = "openai_compatible"

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
        self.supports_images = False
        self.logger = get_logger('openai_compatible')

        self.logger.info(f"Initialized OpenAI-compatible provider:")
        self.logger.info(f"  Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
        self.logger.info(f"  Model: {OPENAI_COMPATIBLE_MODEL}")
        self.logger.info(f"  Max tokens: {OPENAI_COMPATIBLE_MAX_TOKENS}")

    async def generate_ai_response(self, messages, max_tokens=None, temperature=None, channel_id=None):
        """
        Generate an AI response using the configured OpenAI-compatible API.

        For DeepSeek reasoner models, extracts reasoning_content and prepends
        it as a [DEEPSEEK_REASONING]: prefixed block when thinking is enabled.
        Reasoning is always logged regardless of thinking display setting.

        Args:
            messages: List of message dicts with role and content
            max_tokens: Maximum tokens in response
            temperature: Creativity (0.0-1.0)
            channel_id: Discord channel ID for thinking display control

        Returns:
            str: Response text, with reasoning block prepended if thinking enabled
        """
        self.logger.debug(f"Using OpenAI-compatible provider (model: {self.model})")
        self.logger.debug(f"Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
        self.logger.debug(f"Max tokens: {max_tokens}")

        try:
            if max_tokens is None:
                max_tokens = self.max_response_tokens
            if temperature is None:
                temperature = DEFAULT_TEMPERATURE

            system_prompt = next(
                (m["content"] for m in messages if m["role"] == "system"), None
            )
            if system_prompt:
                self.logger.debug(f"System prompt: '{system_prompt[:80]}...'")
            self.logger.debug(f"Number of messages: {len(messages)}")

            api_messages = []
            for msg in messages:
                if msg["role"] in ["system", "user", "assistant"]:
                    content = msg["content"]
                    if msg["role"] == "user" and "name" in msg:
                        if not content.startswith(msg["name"]):
                            content = f"{msg['name']}: {content}"
                    api_messages.append({"role": msg["role"], "content": content})

            # CRITICAL: Do NOT remove this executor wrapper.
            # deepseek-reasoner generates up to 32K reasoning tokens before
            # responding, causing API calls that can take 60+ seconds. Without
            # run_in_executor(), the synchronous API call blocks the Discord
            # event loop, causing heartbeat failures, WebSocket disconnection,
            # and bot crashes. Confirmed via production crash during v2.20.0
            # development. See HANDOFF.md for details.
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

            message_obj = response.choices[0].message
            content = message_obj.content.strip()
            finish_reason = response.choices[0].finish_reason
            self.logger.debug(f"API response finished with reason: {finish_reason}")

            # Extract reasoning_content if present (deepseek-reasoner)
            reasoning_content = getattr(message_obj, 'reasoning_content', None)
            if reasoning_content and self._is_deepseek_model():
                return self._build_reasoning_response(content, reasoning_content, channel_id)

            self.logger.debug(f"Response received: {len(content)} chars")
            return content

        except Exception as e:
            self.logger.error(f"Error generating AI response: {e}")
            self.logger.error(f"Model: {self.model}, Base URL: {OPENAI_COMPATIBLE_BASE_URL}")
            raise e

    def _build_reasoning_response(self, content, reasoning_content, channel_id):
        """
        Build response string with reasoning block when reasoning_content present.

        Uses REASONING_SEPARATOR as an unambiguous boundary between the reasoning
        block and the answer, preventing false splits on blank lines within
        reasoning_content.

        Args:
            content: Final answer text from API
            reasoning_content: Full reasoning/CoT text from API
            channel_id: Discord channel ID for thinking display check

        Returns:
            str: Combined string with reasoning block + separator + content,
                 or content only if thinking disabled
        """
        show_thinking = False
        if channel_id is not None:
            try:
                from commands.thinking_commands import get_thinking_enabled
                show_thinking = get_thinking_enabled(channel_id)
            except ImportError:
                self.logger.warning("Could not import thinking_commands")

        reasoning_len = len(reasoning_content)

        if show_thinking:
            self.logger.info(
                f"DeepSeek reasoning for channel {channel_id} "
                f"({reasoning_len} chars): {reasoning_content}"
            )
            return f"{REASONING_PREFIX}\n{reasoning_content}{REASONING_SEPARATOR}{content}"
        else:
            self.logger.debug(
                f"DeepSeek reasoning present ({reasoning_len} chars), "
                f"thinking display disabled for channel {channel_id}"
            )
            return content

    def _is_deepseek_model(self):
        """Return True if configured model appears to be a DeepSeek model."""
        return 'deepseek' in self.model.lower()
