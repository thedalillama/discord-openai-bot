# config.py
# Version 1.18.0
"""
Bot configuration - all settings loaded from environment variables with defaults.

CHANGES v1.18.0: RRF_K for hybrid retrieval (SOW v6.2.0)
- ADDED: RRF_K (default 15) — Reciprocal Rank Fusion constant; controls how
  much weight the top-ranked segments get when fusing BM25 and dense results.

CHANGES v1.17.0: Direct segment retrieval configuration (SOW v6.1.0)
- ADDED: RETRIEVAL_FLOOR (default 0.15) — absolute minimum score for segment
  retrieval; replaces RETRIEVAL_MIN_SCORE on the primary segment path
- ADDED: RETRIEVAL_SCORE_GAP (default 0.08) — triggers cutoff at the largest
  inter-score gap after top-K selection; set to 0 to disable

CHANGES v1.16.0: Segment pipeline configuration (SOW v6.0.0)
- ADDED: SEGMENT_BATCH_SIZE (default 500) — messages per Gemini segmentation call
- ADDED: SEGMENT_OVERLAP (default 20) — overlap window between batches to reduce
  boundary artifacts
- ADDED: SEGMENT_GAP_MINUTES (default 30) — time gap threshold for fallback
  time-gap segmentation when LLM segmentation fails

CHANGES v1.15.0: Similarity threshold rename and separation (SOW v5.12.0)
- ADDED: EMBEDDING_CONTEXT_MIN_SCORE (default 0.3) — replaces hardcoded
  CONTEXT_SIMILARITY_THRESHOLD in embedding_context.py; now env-configurable.
- ADDED: QUERY_TOPIC_SHIFT_THRESHOLD (default 0.5) — split from RETRIEVAL_MIN_SCORE;
  controls topic-shift detection in embed_query_with_smart_context().
- UPDATED: TOPIC_LINK_MIN_SCORE comment — marked as legacy (topics table dropped
  in schema/007.sql; variable retained for backward compatibility only).

CHANGES v1.14.0: Fix stale model defaults (SOW v5.10.0)
- FIXED: GEMINI_MODEL default 'gemini-2.5-flash-lite' → 'gemini-3.1-flash-lite-preview'
- FIXED: SUMMARIZER_MODEL default 'gemini-2.5-flash-lite' → 'gemini-3.1-flash-lite-preview'
- Production .env already overrode these; this aligns defaults with production.

CHANGES v1.13.0: HDBSCAN clustering configuration (SOW v5.1.0)
- ADDED: CLUSTER_MIN_CLUSTER_SIZE (default 5) — minimum messages per cluster
- ADDED: CLUSTER_MIN_SAMPLES (default 3) — HDBSCAN noise sensitivity
- ADDED: UMAP_N_NEIGHBORS (default 15) — UMAP neighborhood size
- ADDED: UMAP_N_COMPONENTS (default 5) — UMAP output dimensions

CHANGES v1.12.6: Semantic retrieval configuration (SOW v4.1.0)
- ADDED: RETRIEVAL_MSG_FALLBACK (default 15) — max messages for direct fallback

CHANGES v1.12.5: Semantic retrieval configuration (SOW v4.0.0)
- ADDED: EMBEDDING_MODEL, RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE,
  TOPIC_LINK_MIN_SCORE, MAX_RECENT_MESSAGES

CHANGES v1.7.0: SQLite message persistence (SOW v3.0.0)
- ADDED: DATABASE_PATH env var (default './data/messages.db'). The data/
  directory is created automatically on first run. Override via env var or
  .env if you prefer a different location.

CHANGES v1.6.0: Token-budget context management (SOW v2.23.0)
- ADDED: CONTEXT_BUDGET_PERCENT env var (default 80)
- FIXED: OPENAI_COMPATIBLE_CONTEXT_LENGTH default 128000 → 64000
- UPDATED: ANTHROPIC_MODEL default synced to claude-haiku-4-5-20251001

CHANGES v1.5.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: INITIAL_HISTORY_LOAD variable

CHANGES v1.4.0: Final BaseTen cleanup - removed all legacy references
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
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.1-flash-lite-preview')
GEMINI_CONTEXT_LENGTH = int(os.environ.get('GEMINI_CONTEXT_LENGTH', 1000000))
GEMINI_MAX_TOKENS = int(os.environ.get('GEMINI_MAX_TOKENS', 32768))

# Summarizer configuration
# SUMMARIZER_PROVIDER defaults to 'gemini' — 1M context handles full history
# in a single pass without recursive chunking. Set to another provider to
# override (shares that provider's singleton and model).
SUMMARIZER_PROVIDER = os.environ.get('SUMMARIZER_PROVIDER', 'gemini')
SUMMARIZER_MODEL = os.environ.get('SUMMARIZER_MODEL', 'gemini-3.1-flash-lite-preview')
# SUMMARIZER_BATCH_SIZE: messages per Gemini call. Keeps output JSON small
# enough to stay within Gemini's response token limit. Default 50 — larger
# batches cause too many ops in a single response, truncating the JSON.
SUMMARIZER_BATCH_SIZE = int(os.environ.get('SUMMARIZER_BATCH_SIZE', 50))

# Semantic retrieval configuration (SOW v4.0.0)
# EMBEDDING_MODEL: OpenAI embedding model. text-embedding-3-small is 1536
# dimensions, fast, and inexpensive. Uses OPENAI_API_KEY.
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
# RETRIEVAL_TOP_K: number of segments to retrieve per query (v6.1.0 tuned to 7).
RETRIEVAL_TOP_K = int(os.environ.get('RETRIEVAL_TOP_K', 7))
# RETRIEVAL_MIN_SCORE: minimum cosine similarity for cluster rollback path and
# incremental cluster assignment. Not used on the primary segment retrieval path.
RETRIEVAL_MIN_SCORE = float(os.environ.get('RETRIEVAL_MIN_SCORE', 0.25))
# RETRIEVAL_FLOOR: absolute minimum score for direct segment retrieval. Segments
# below this are never returned regardless of top-K. Set low — top-K and
# score-gap are the primary filters. (SOW v6.1.0)
RETRIEVAL_FLOOR = float(os.environ.get('RETRIEVAL_FLOOR', 0.20))
# RETRIEVAL_SCORE_GAP: minimum gap between adjacent scores to trigger cutoff
# after top-K selection. Set to 0 to disable score-gap detection. (SOW v6.1.0)
RETRIEVAL_SCORE_GAP = float(os.environ.get('RETRIEVAL_SCORE_GAP', 0.08))
# RRF_K: Reciprocal Rank Fusion constant for hybrid BM25+dense retrieval.
# Lower value = more weight on top-ranked segments. k=15 tuned for small result
# sets (top_k=7 candidates per ranker). (SOW v6.2.0)
RRF_K = int(os.environ.get('RRF_K', 15))
# EMBEDDING_CONTEXT_MIN_SCORE: minimum cosine similarity for a previous message
# to be included as context in the [Context: ...] prefix when building stored
# embeddings. Lower = more inclusive. Questions always pass. (SOW v5.12.0)
EMBEDDING_CONTEXT_MIN_SCORE = float(
    os.environ.get('EMBEDDING_CONTEXT_MIN_SCORE', 0.3))
# QUERY_TOPIC_SHIFT_THRESHOLD: at query time, cosine similarity below this
# value vs the previous message = topic shift → use raw embedding. Above =
# same topic → re-embed with conversational context. (SOW v5.12.0)
QUERY_TOPIC_SHIFT_THRESHOLD = float(
    os.environ.get('QUERY_TOPIC_SHIFT_THRESHOLD', 0.5))
# TOPIC_LINK_MIN_SCORE: legacy — topics table dropped in schema/007.sql.
# Retained for backward compatibility only; has no active callers.
TOPIC_LINK_MIN_SCORE = float(os.environ.get('TOPIC_LINK_MIN_SCORE', 0.3))
# MAX_RECENT_MESSAGES: hard cap on recent messages included in context window.
# Prevents recent history from overwhelming retrieved topic context.
MAX_RECENT_MESSAGES = int(os.environ.get('MAX_RECENT_MESSAGES', 5))
# RETRIEVAL_MSG_FALLBACK: max messages returned by direct embedding fallback
# when topic retrieval returns empty (SOW v4.1.0).
RETRIEVAL_MSG_FALLBACK = int(os.environ.get('RETRIEVAL_MSG_FALLBACK', 15))

# HDBSCAN clustering configuration (v5.1.0)
# CLUSTER_MIN_CLUSTER_SIZE: minimum messages per cluster. Lower = more clusters.
CLUSTER_MIN_CLUSTER_SIZE = int(os.environ.get('CLUSTER_MIN_CLUSTER_SIZE', '5'))
# CLUSTER_MIN_SAMPLES: noise sensitivity. Higher = more noise points.
CLUSTER_MIN_SAMPLES = int(os.environ.get('CLUSTER_MIN_SAMPLES', '3'))
# UMAP_N_NEIGHBORS: neighborhood size for UMAP. Lower = more local structure.
UMAP_N_NEIGHBORS = int(os.environ.get('UMAP_N_NEIGHBORS', '15'))
# UMAP_N_COMPONENTS: output dimensions for UMAP reduction.
UMAP_N_COMPONENTS = int(os.environ.get('UMAP_N_COMPONENTS', '5'))

# Segment pipeline configuration (v6.0.0)
# SEGMENT_BATCH_SIZE: messages per Gemini segmentation call.
SEGMENT_BATCH_SIZE = int(os.environ.get('SEGMENT_BATCH_SIZE', '500'))
# SEGMENT_OVERLAP: overlap window between batches to reduce boundary artifacts.
SEGMENT_OVERLAP = int(os.environ.get('SEGMENT_OVERLAP', '20'))
# SEGMENT_GAP_MINUTES: time gap threshold for fallback time-gap segmentation.
SEGMENT_GAP_MINUTES = int(os.environ.get('SEGMENT_GAP_MINUTES', '30'))

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
