# config.py
# Version 1.6.0
"""
Bot configuration module.
Loads and provides access to environment variables and other configuration.

CHANGES v1.6.0: Token-budget context management (SOW v2.23.0)
- ADDED: CONTEXT_BUDGET_PERCENT env var (default 80) — percentage of context
  window to use for input token budget. The remaining headroom absorbs
  tokenizer estimation variance and provider-side formatting overhead.
- FIXED: OPENAI_COMPATIBLE_CONTEXT_LENGTH default 128000 → 64000. DeepSeek
  pricing-details page shows 64K for deepseek-chat and deepseek-reasoner.
  Their models page says "128K context limit" for V3.2 but API enforces 64K.
  Override via env var if higher limit confirmed.
- UPDATED: ANTHROPIC_MODEL default synced to current Haiku 4.5
  (claude-haiku-4-5-20251001). Previous default claude-3-haiku-20240307 was
  stale; README_ENV.md already referenced the new model.

CHANGES v1.5.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: INITIAL_HISTORY_LOAD variable (no longer needed; full history fetch
  is now unconditional via limit=None in discord_fetcher.py)

CHANGES v1.4.0: Final BaseTen cleanup - removed all legacy references
- REMOVED: BASETEN_DEEPSEEK_KEY environment variable
- REMOVED: DEEPSEEK_MODEL, DEEPSEEK_CONTEXT_LENGTH, DEEPSEEK_MAX_TOKENS variables
- REMOVED: BaseTen DeepSeek configuration comment block
- NOTE: DeepSeek is now fully handled via OPENAI_COMPATIBLE_* variables
- MAINTAINED: All other provider configurations unchanged

CHANGES v1.3.0: Added CHANNEL_LOCK_TIMEOUT as configurable env var
CHANGES v1.2.0: Added OpenAI-compatible provider configuration
CHANGES v1.1.0: Added ENABLE_IMAGE_GENERATION flag
"""
import os

# Bot configuration
DEFAULT_AUTO_RESPOND = os.environ.get('AUTO_RESPOND', 'false').lower() == 'true'
MAX_HISTORY = int(os.environ.get('MAX_HISTORY', 10))
MAX_RESPONSE_TOKENS = int(os.environ.get('MAX_RESPONSE_TOKENS', 800))
BOT_PREFIX = os.environ.get('BOT_PREFIX', 'Bot, ')
CHANNEL_LOCK_TIMEOUT = int(os.environ.get('CHANNEL_LOCK_TIMEOUT', 30))

# Default AI provider
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai')
DEFAULT_TEMPERATURE = float(os.environ.get('DEFAULT_TEMPERATURE', 0.7))

# Token budget configuration
# Percentage of provider context window to use for input token budget.
# The remaining headroom (default 20%) absorbs tiktoken estimation variance
# (especially for Anthropic where tiktoken is approximate ~10-15%), per-message
# formatting overhead, and provider-side hidden tokens.
CONTEXT_BUDGET_PERCENT = int(os.environ.get('CONTEXT_BUDGET_PERCENT', 80))

# OpenAI configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_CONTEXT_LENGTH = int(os.environ.get('OPENAI_CONTEXT_LENGTH', 128000))
OPENAI_MAX_TOKENS = int(os.environ.get('OPENAI_MAX_TOKENS', 1500))

# Image generation configuration
ENABLE_IMAGE_GENERATION = os.environ.get('ENABLE_IMAGE_GENERATION', 'true').lower() == 'true'

# Anthropic configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
ANTHROPIC_CONTEXT_LENGTH = int(os.environ.get('ANTHROPIC_CONTEXT_LENGTH', 200000))
ANTHROPIC_MAX_TOKENS = int(os.environ.get('ANTHROPIC_MAX_TOKENS', 2000))

# Generic OpenAI-compatible provider configuration
# NOTE: OPENAI_COMPATIBLE_CONTEXT_LENGTH default is 64000 based on DeepSeek's
# pricing-details page (verified 2025-02-26). Their models page claims "128K
# context limit" for V3.2 but the API endpoint enforces 64K. Override via env
# var if your provider supports a higher limit.
OPENAI_COMPATIBLE_API_KEY = os.environ.get('OPENAI_COMPATIBLE_API_KEY')
OPENAI_COMPATIBLE_BASE_URL = os.environ.get('OPENAI_COMPATIBLE_BASE_URL')
OPENAI_COMPATIBLE_MODEL = os.environ.get('OPENAI_COMPATIBLE_MODEL', 'deepseek-chat')
OPENAI_COMPATIBLE_CONTEXT_LENGTH = int(os.environ.get('OPENAI_COMPATIBLE_CONTEXT_LENGTH', 64000))
OPENAI_COMPATIBLE_MAX_TOKENS = int(os.environ.get('OPENAI_COMPATIBLE_MAX_TOKENS', 8000))

# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.environ.get('LOG_FILE', 'stdout')
LOG_FORMAT = os.environ.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')

# History display configuration
HISTORY_LINE_PREFIX = os.environ.get('HISTORY_LINE_PREFIX', '➤ ')

# System prompts
DEFAULT_SYSTEM_PROMPT = os.environ.get('DEFAULT_SYSTEM_PROMPT',
    "You are a helpful assistant in a Discord server. Respond in a friendly, concise manner. "
    "You have been listening to the conversation and can reference it in your replies."
)
