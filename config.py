# config.py
# Version 1.8.0
"""
Bot configuration module.
Loads and provides access to environment variables and other configuration.

CHANGES v1.8.0: Summarizer provider configuration (SOW v3.2.0)
- ADDED: SUMMARIZER_PROVIDER env var (default: AI_PROVIDER) — provider used
  for summarization calls; independent of per-channel conversation providers
- ADDED: SUMMARIZER_MODEL env var (default: deepseek-chat) — stored in summary
  meta for reference; actual model is determined by provider initialisation

CHANGES v1.7.0: SQLite message persistence (SOW v3.0.0)
- ADDED: DATABASE_PATH env var (default ./data/messages.db) — path to SQLite
  database file for message persistence. Directory created automatically on
  first run. No .env change needed unless overriding the default location.

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

# Database configuration
# Path to SQLite database file for message persistence. The data/ directory
# is created automatically on first run. Override via env var or .env if you
# prefer a different location (e.g., /var/lib/discord-bot/messages.db).
DATABASE_PATH = os.environ.get('DATABASE_PATH', './data/messages.db')

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

# Summarizer configuration
# SUMMARIZER_PROVIDER selects the provider for summarization calls. Defaults
# to AI_PROVIDER if not set. If both conversation and summarization use the
# same provider type (e.g. both 'deepseek'), they share the singleton instance
# and therefore the same model. Use a different provider type to get a separate
# instance with a different model.
SUMMARIZER_PROVIDER = os.environ.get('SUMMARIZER_PROVIDER', AI_PROVIDER)
SUMMARIZER_MODEL = os.environ.get('SUMMARIZER_MODEL', 'deepseek-chat')

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
