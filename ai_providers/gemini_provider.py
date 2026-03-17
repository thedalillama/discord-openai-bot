# ai_providers/gemini_provider.py
# Version 1.1.0
"""
Gemini provider implementation for summarization.

CHANGES v1.1.0: Structured output support (SOW v3.2.0)
- ADDED: response_mime_type and response_json_schema kwargs to
  generate_ai_response(); included in GenerateContentConfig when provided.
  Enables Gemini Structured Outputs (Layer 1 delta schema enforcement).

CREATED v1.0.0: Gemini summarization provider (SOW v3.2.0)
- ADDED: GeminiProvider — extends AIProvider; uses google-genai SDK
- ADDED: generate_ai_response() — converts OpenAI-style messages to Gemini
  format (system_instruction + contents), calls via run_in_executor(), logs
  usage from response.usage_metadata
- ADDED: _convert_messages() — maps system → system_instruction, user →
  role "user", assistant → role "model"

Provider calls use loop.run_in_executor() with ThreadPoolExecutor —
established pattern for all providers; prevents heartbeat blocking.
"""
import asyncio
import concurrent.futures
from google import genai
from google.genai import types
from .base import AIProvider
from config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GEMINI_CONTEXT_LENGTH, GEMINI_MAX_TOKENS, DEFAULT_TEMPERATURE,
)
from utils.logging_utils import get_logger
from utils.context_manager import record_usage


class GeminiProvider(AIProvider):
    """Gemini provider using google-genai SDK. Used primarily for summarization."""

    def __init__(self):
        super().__init__()
        self.name = "gemini"

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.max_context_length = GEMINI_CONTEXT_LENGTH
        self.max_response_tokens = GEMINI_MAX_TOKENS
        self.supports_images = False
        self.logger = get_logger('gemini')

        self.logger.info(f"Initialized Gemini provider: model={self.model}, "
                         f"context={self.max_context_length}, "
                         f"max_tokens={self.max_response_tokens}")

    async def generate_ai_response(
        self, messages, max_tokens=None, temperature=None, channel_id=None,
        response_mime_type=None, response_json_schema=None,
    ):
        """
        Generate a response using the Gemini API.

        Converts OpenAI-style messages (system/user/assistant) to Gemini
        format: system message → system_instruction in config; user/assistant
        turns → contents list with roles "user"/"model".

        Args:
            messages: List of dicts with 'role' and 'content'.
            max_tokens: Max output tokens (defaults to GEMINI_MAX_TOKENS).
            temperature: Sampling temperature (defaults to DEFAULT_TEMPERATURE).
            channel_id: Discord channel ID for usage logging.
            response_mime_type: e.g. "application/json" for structured output.
            response_json_schema: JSON Schema dict for Gemini Structured Outputs.

        Returns:
            str: Response text from Gemini.
        """
        if max_tokens is None:
            max_tokens = self.max_response_tokens
        if temperature is None:
            temperature = DEFAULT_TEMPERATURE

        system_instruction, contents = self._convert_messages(messages)

        config_kwargs = dict(
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type
        if response_json_schema is not None:
            config_kwargs["response_schema"] = response_json_schema

        config = types.GenerateContentConfig(**config_kwargs)

        self.logger.debug(
            f"Gemini call: model={self.model}, turns={len(contents)}, "
            f"max_tokens={max_tokens}, temperature={temperature}"
        )

        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: self.client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                )

            usage = getattr(response, 'usage_metadata', None)
            if usage:
                record_usage(
                    channel_id, self.name,
                    getattr(usage, 'prompt_token_count', 0),
                    getattr(usage, 'candidates_token_count', 0),
                )
            else:
                self.logger.debug("No usage_metadata in Gemini response")

            text = getattr(response, 'text', None)
            if not text:
                self.logger.warning("Gemini returned empty response text")
                return ""
            return text

        except Exception as e:
            self.logger.error(f"Gemini API call failed: {e}")
            raise

    def _convert_messages(self, messages):
        """
        Convert OpenAI-style message list to Gemini (system_instruction, contents).

        Returns:
            tuple: (system_instruction_str_or_None, list_of_Content_objects)
        """
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=content)])
                )
            elif role == "assistant":
                contents.append(
                    types.Content(role="model", parts=[types.Part(text=content)])
                )

        return system_instruction, contents
