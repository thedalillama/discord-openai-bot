# ai_providers/gemini_provider.py
# Version 1.2.1
"""
Gemini provider implementation for summarization.

CHANGES v1.2.1: Fix _convert_messages() to use types.Content/Part objects
- FIXED: v1.2.0 broke message format by using plain dicts instead of
  types.Content and types.Part objects, causing pydantic validation errors

CHANGES v1.2.0: Support response_json_schema for anyOf schemas (SOW v3.5.0)
- ADDED: use_json_schema kwarg to generate_ai_response(). When True, passes
  schema via response_json_schema (JSON Schema format) instead of
  response_schema (OpenAPI format). Required for anyOf discriminated unions.

CHANGES v1.1.0: Structured output support (SOW v3.2.0)
- ADDED: response_mime_type and response_json_schema kwargs

CREATED v1.0.0: Gemini summarization provider (SOW v3.2.0)
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
    """Gemini provider using google-genai SDK."""

    def __init__(self):
        super().__init__()
        self.name = "gemini"

        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL
        self.max_context_length = GEMINI_CONTEXT_LENGTH
        self.max_response_tokens = GEMINI_MAX_TOKENS
        self.supports_images = False
        self.logger = get_logger('gemini')

        self.logger.info(
            f"Initialized Gemini provider: model={self.model}, "
            f"context={self.max_context_length}, "
            f"max_tokens={self.max_response_tokens}")

    async def generate_ai_response(
        self, messages, max_tokens=None, temperature=None,
        channel_id=None, response_mime_type=None,
        response_json_schema=None, use_json_schema=False,
    ):
        """Generate a response using the Gemini API.

        Args:
            messages: List of dicts with 'role' and 'content'.
            max_tokens: Max output tokens (defaults to GEMINI_MAX_TOKENS).
            temperature: Sampling temperature.
            channel_id: Discord channel ID for usage logging.
            response_mime_type: e.g. "application/json".
            response_json_schema: JSON Schema dict for structured output.
            use_json_schema: If True, pass schema as response_json_schema
                (JSON Schema format, supports anyOf). If False, pass as
                response_schema (OpenAPI format, default).

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
            if use_json_schema:
                config_kwargs["response_json_schema"] = (
                    response_json_schema)
            else:
                config_kwargs["response_schema"] = (
                    response_json_schema)

        config = types.GenerateContentConfig(**config_kwargs)

        self.logger.debug(
            f"Gemini call: model={self.model}, "
            f"turns={len(contents)}, max_tokens={max_tokens}, "
            f"temperature={temperature}, "
            f"json_schema={use_json_schema}")

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
                self.logger.debug(
                    "No usage_metadata in Gemini response")

            text = getattr(response, 'text', None)
            if not text:
                self.logger.warning(
                    "Gemini returned empty response text")
                return ""
            return text

        except Exception as e:
            self.logger.error(f"Gemini API call failed: {e}")
            raise

    def _convert_messages(self, messages):
        """Convert OpenAI-style messages to Gemini format.

        system → system_instruction (string)
        user → role "user"
        assistant → role "model"

        Returns:
            tuple: (system_instruction_str_or_None, list_of_Content)
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
                    types.Content(
                        role="user",
                        parts=[types.Part(text=content)]))
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part(text=content)]))
        return system_instruction, contents
