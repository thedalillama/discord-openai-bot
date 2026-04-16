# README_ENV.md
# Version 6.4.1
# Environment Variables Configuration Guide

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token from Developer Portal | `your_discord_bot_token` |

## API Keys (set only what you use)

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key — required for embeddings + classifier | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude conversation provider) | `sk-ant-...` |
| `OPENAI_COMPATIBLE_API_KEY` | DeepSeek or compatible provider | `sk-...` |
| `GEMINI_API_KEY` | Google Gemini API key (summarization) | `AIza...` |

Note: `OPENAI_API_KEY` is required even if OpenAI is not the conversation provider,
because it is used for message embeddings (`text-embedding-3-small`) and the
GPT-4o-mini classifier in the summarization pipeline.

## Core Bot Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_PROVIDER` | Default conversation AI provider | `openai` |
| `AUTO_RESPOND` | Auto-respond by default | `false` |
| `BOT_PREFIX` | Direct addressing prefix | `Bot, ` |
| `DEFAULT_TEMPERATURE` | AI creativity level (0.0-2.0) | `0.7` |
| `MAX_HISTORY` | Messages kept in memory per channel | `10` |
| `MAX_RESPONSE_TOKENS` | Max tokens per AI response | `800` |
| `HISTORY_LINE_PREFIX` | Prefix for !history display | `➤ ` |

## Token Budget Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTEXT_BUDGET_PERCENT` | % of context window for input | `80` |
| `MAX_RECENT_MESSAGES` | Hard cap on recent messages in context | `5` |

Budget formula: `input_budget = (context_window × % / 100) − max_output_tokens`

The 20% default headroom absorbs tiktoken variance for Anthropic (~10-15%),
per-message formatting overhead, and provider-side hidden tokens.

`MAX_RECENT_MESSAGES` prevents recent history from overwhelming semantically
retrieved topic context. Retrieved content is injected into the system prompt;
the trimmer drops oldest recent messages to fit within the remaining budget.

## Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | Path to SQLite database file | `./data/messages.db` |

The `data/` directory is created automatically on first run.

## Semantic Retrieval Configuration (v6.4.0+)

| Variable | Description | Default |
|----------|-------------|---------|
| `EMBEDDING_MODEL` | OpenAI embedding model | `text-embedding-3-small` |
| `RETRIEVAL_TOP_K` | Max segments returned per query (dense pool = top_k × 2) | `7` |
| `RETRIEVAL_FLOOR` | Absolute minimum score for segment retrieval; segments below this never returned | `0.20` |
| `RETRIEVAL_SCORE_GAP` | Triggers cutoff at largest inter-score gap after top-K; set to `0` to disable | `0.08` |
| `RRF_K` | Reciprocal Rank Fusion constant; lower = more weight on top-ranked segments | `15` |
| `RETRIEVAL_MIN_SCORE` | Min cosine similarity for cluster rollback path and incremental assignment | `0.25` |
| `QUERY_TOPIC_SHIFT_THRESHOLD` | At query time, cosine similarity below this vs previous message = topic shift → raw embedding; above = re-embed with context | `0.5` |
| `EMBEDDING_CONTEXT_MIN_SCORE` | Min cosine similarity for a previous message to be included in the `[Context: ...]` prefix for stored embeddings | `0.3` |
| `RETRIEVAL_MSG_FALLBACK` | Max messages returned by direct fallback search | `15` |
| `PROPOSITION_BATCH_SIZE` | Segment syntheses per GPT-4o-mini decomposition call | `10` |

Production `.env` sets `RETRIEVAL_MIN_SCORE=0.5` and `CONTEXT_BUDGET_PERCENT=80`.

**Budget note:** for providers with large `MAX_TOKENS` relative to context window (e.g. DeepSeek:
64k context − 8k max_tokens at 15% = only 1,600 token budget), keep `CONTEXT_BUDGET_PERCENT`
at 80 or retrieval will be starved and fall back to message similarity.

**Primary path (v6.4.0):** three-signal retrieval — proposition embeddings + dense segment
embeddings + BM25, fused via `RRF_K`. `PROPOSITION_BATCH_SIZE` controls GPT-4o-mini
decomposition call size. `RETRIEVAL_FLOOR` and `RETRIEVAL_SCORE_GAP` apply to dense
candidates only. `RETRIEVAL_MIN_SCORE` is only used on the cluster rollback path (pre-v6
channels with no segments) and for incremental cluster assignment.

After changing `EMBEDDING_MODEL` or migrating to a new server, run:
1. `!debug reembed` in Discord — wipes and re-embeds all messages with contextual text
2. `!summary create` — rebuilds clusters from the new embeddings

## Summarizer Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SUMMARIZER_PROVIDER` | Provider for summarization | `gemini` |
| `SUMMARIZER_MODEL` | Model for summarization | `gemini-2.5-flash-lite` |
| `SUMMARIZER_BATCH_SIZE` | Messages per summarizer call | `50` |

The summarizer runs independently of conversation providers. Gemini is
recommended due to its 1M token context window, which allows sending full
channel history in a single pass without recursive chunking.

Controls both cold start batching and incremental batching. Cold start processes
the first `SUMMARIZER_BATCH_SIZE` messages, then continues through the incremental
loop for the remainder. Set to 500 to keep each Structurer response to a manageable
size while still processing large channels efficiently.

The server `.env` overrides `SUMMARIZER_MODEL` to `gemini-3.1-flash-lite-preview`.

## Provider-Specific Configuration

### OpenAI

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `OPENAI_CONTEXT_LENGTH` | Context window size | `128000` |
| `OPENAI_MAX_TOKENS` | Max response tokens | `1500` |
| `ENABLE_IMAGE_GENERATION` | Enable DALL-E image gen | `true` |

### Anthropic

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_MODEL` | Anthropic model name | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_CONTEXT_LENGTH` | Context window size | `200000` |
| `ANTHROPIC_MAX_TOKENS` | Max response tokens | `2000` |

### DeepSeek (OpenAI-Compatible)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_COMPATIBLE_BASE_URL` | API endpoint URL | *(required)* |
| `OPENAI_COMPATIBLE_MODEL` | Model name | `deepseek-chat` |
| `OPENAI_COMPATIBLE_CONTEXT_LENGTH` | Context window size | `64000` |
| `OPENAI_COMPATIBLE_MAX_TOKENS` | Max response tokens | `8000` |

Note: DeepSeek's API enforces 64K context despite documentation claiming
128K. Override via env var if your provider supports a higher limit.

### Gemini

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_MODEL` | Gemini model name | `gemini-2.5-flash-lite` |
| `GEMINI_CONTEXT_LENGTH` | Context window size | `1000000` |
| `GEMINI_MAX_TOKENS` | Max response tokens | `32768` |

Gemini is used for summarization only, not for conversation responses.

## Clustering Configuration (v5.1.0)

| Variable | Description | Default |
|----------|-------------|---------|
| `CLUSTER_MIN_CLUSTER_SIZE` | Minimum messages per cluster (lower = more clusters) | `5` |
| `CLUSTER_MIN_SAMPLES` | HDBSCAN noise sensitivity (higher = more noise) | `3` |
| `UMAP_N_NEIGHBORS` | UMAP neighborhood size (lower = more local structure) | `15` |
| `UMAP_N_COMPONENTS` | UMAP output dimensions | `5` |

These control the UMAP + HDBSCAN pipeline used by the segment clustering step in
`!summary create`. `UMAP_N_NEIGHBORS` is automatically capped to `n_items - 1`
for small channels/segment sets.

## Segment Pipeline Configuration (v6.0.0)

| Variable | Description | Default |
|----------|-------------|---------|
| `SEGMENT_BATCH_SIZE` | Messages per Gemini segmentation call | `500` |
| `SEGMENT_OVERLAP` | Overlap window between batches (reduces boundary artifacts) | `20` |
| `SEGMENT_GAP_MINUTES` | Time gap threshold for fallback time-gap segmentation | `30` |

`SEGMENT_BATCH_SIZE` controls how many messages are sent to Gemini per call during
`!summary create`. Larger batches give Gemini more context for segmentation but
increase response size. Gemini's 1M context handles 500 messages easily.

`SEGMENT_OVERLAP` causes adjacent batches to share the last N messages of the
previous batch. Segments identified in the overlap zone of non-first batches are
skipped (already captured). Reduces topic boundary artifacts at batch seams.

`SEGMENT_GAP_MINUTES` controls the time-gap fallback segmenter that fires when
Gemini segmentation fails for a batch. Messages separated by more than this many
minutes are split into different segments.

## Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FILE` | Log output destination | `stdout` |
| `LOG_FORMAT` | Python log format string | *(see config.py)* |

## System Prompt

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_SYSTEM_PROMPT` | Default system prompt for all channels | `You are a helpful assistant...` |

Per-channel system prompts can be set with `!prompt <text>` and override
this default. Always-on summary context and retrieved topic messages are
automatically appended to whichever system prompt is active.

## Debug Tools

When `LOG_LEVEL=DEBUG`, the full combined system prompt (base prompt +
citation instruction + context block) is written to `/tmp/last_system_prompt.txt`
after every bot response. Read it with:

```bash
cat /tmp/last_system_prompt.txt
```

This is the exact text sent to the AI provider API.

## Priority Order

Shell environment variables > `.env` file > `config.py` defaults.

## Example .env

```bash
# Required
DISCORD_TOKEN=your_discord_bot_token

# Conversation provider
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-your-deepseek-key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner

# Summarization
GEMINI_API_KEY=your-gemini-key
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500

# Embeddings + classifier (required)
OPENAI_API_KEY=your-openai-key

# Optional tuning
CONTEXT_BUDGET_PERCENT=80
MAX_RECENT_MESSAGES=5
DATABASE_PATH=./data/messages.db
LOG_LEVEL=INFO
```
