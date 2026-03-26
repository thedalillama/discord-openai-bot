# config.py
# Version 1.12.3
"""
Bot configuration module.
Loads and provides access to environment variables and other configuration.

CHANGES v1.12.3: Add MAX_RECENT_MESSAGES config (default 5)

CHANGES v1.12.2: Switch embedding provider to OpenAI
- CHANGED: EMBEDDING_MODEL default gemini-embedding-001 → text-embedding-3-small

CHANGES v1.12.1: Fix EMBEDDING_MODEL default
- FIXED: default changed from text-embedding-004 → gemini-embedding-001

CHANGES v1.12.0: Semantic retrieval configuration (SOW v4.0.0)
- ADDED: EMBEDDING_MODEL — Gemini embedding model (default gemini-embedding-001)
- ADDED: RETRIEVAL_TOP_K — topics to retrieve per query (default 5)
- ADDED: TOPIC_MSG_LIMIT — messages linked per topic via similarity (default 20)

CHANGES v1.11.0: Reduce default batch size to prevent response truncation
- CHANGED: SUMMARIZER_BATCH_SIZE default 200 → 50 — 200-message batches caused
  Gemini to generate too many ops, truncating the JSON before closing braces;
  50 messages keeps output well within the response token window

CHANGES v1.10.0: Summarizer batch size + Gemini output limit (SOW v3.2.0)
- ADDED: SUMMARIZER_BATCH_SIZE env var (default 200) — messages per Gemini call
- CHANGED: GEMINI_MAX_TOKENS default 8192 → 32768 — previous limit truncated
  delta JSON for batches of 200 messages (~8K output tokens needed)

CHANGES v1.9.0: Gemini provider configuration (SOW v3.2.0)
- ADDED: GEMINI_API_KEY, GEMINI_MODEL, GEMINI_CONTEXT_LENGTH, GEMINI_MAX_TOKENS
- CHANGED: SUMMARIZER_PROVIDER default 'AI_PROVIDER' → 'gemini'
- CHANGED: SUMMARIZER_MODEL default 'deepseek-chat' → 'gemini-2.5-flash-lite'

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

# Gemini configuration
# Used primarily for summarization (1M token context fits full message history).
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')
GEMINI_CONTEXT_LENGTH = int(os.environ.get('GEMINI_CONTEXT_LENGTH', 1000000))
GEMINI_MAX_TOKENS = int(os.environ.get('GEMINI_MAX_TOKENS', 32768))

# Summarizer configuration
# SUMMARIZER_PROVIDER defaults to 'gemini' — 1M context handles full history
# in a single pass without recursive chunking. Set to another provider to
# override (shares that provider's singleton and model).
SUMMARIZER_PROVIDER = os.environ.get('SUMMARIZER_PROVIDER', 'gemini')
SUMMARIZER_MODEL = os.environ.get('SUMMARIZER_MODEL', 'gemini-2.5-flash-lite')
# SUMMARIZER_BATCH_SIZE: messages per Gemini call. Keeps output JSON small
# enough to stay within Gemini's response token limit. Default 50 — larger
# batches cause too many ops in a single response, truncating the JSON.
SUMMARIZER_BATCH_SIZE = int(os.environ.get('SUMMARIZER_BATCH_SIZE', 50))

# Semantic retrieval configuration (SOW v4.0.0)
# EMBEDDING_MODEL: OpenAI embedding model. text-embedding-3-small is 1536
# dimensions, fast, and inexpensive. Uses OPENAI_API_KEY.
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
# RETRIEVAL_TOP_K: number of topics to retrieve per query in context_manager.
RETRIEVAL_TOP_K = int(os.environ.get('RETRIEVAL_TOP_K', 5))
# TOPIC_MSG_LIMIT: max messages linked to each topic via embedding similarity.
TOPIC_MSG_LIMIT = int(os.environ.get('TOPIC_MSG_LIMIT', 20))
# MAX_RECENT_MESSAGES: hard cap on recent messages included in context window.
# Prevents recent history from overwhelming retrieved topic context.
MAX_RECENT_MESSAGES = int(os.environ.get('MAX_RECENT_MESSAGES', 5))

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
