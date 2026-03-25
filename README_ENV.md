# README_ENV.md
# Version 3.4.0
# Environment Variables Configuration Guide

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token from Developer Portal | `your_discord_bot_token` |

## API Keys (set only what you use)

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (GPT + image gen) | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude) | `sk-ant-...` |
| `OPENAI_COMPATIBLE_API_KEY` | DeepSeek or compatible provider | `sk-...` |
| `GEMINI_API_KEY` | Google Gemini API key (summarization) | `AIza...` |

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

Budget formula: `input_budget = (context_window × % / 100) − max_output_tokens`

The 20% default headroom absorbs tiktoken variance for Anthropic (~10-15%),
per-message formatting overhead, and provider-side hidden tokens.

## Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | Path to SQLite database file | `./data/messages.db` |

The `data/` directory is created automatically on first run. Stores all
messages in real-time for persistence across restarts and summarization.

## Summarizer Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SUMMARIZER_PROVIDER` | Provider for summarization | `gemini` |
| `SUMMARIZER_MODEL` | Model for summarization | `gemini-2.5-flash-lite` |
| `SUMMARIZER_BATCH_SIZE` | Messages per summarizer call | `50` |

The summarizer runs independently of conversation providers. Gemini is
recommended due to its 1M token context window, which allows sending full
channel history in a single pass without recursive chunking.

Set `SUMMARIZER_BATCH_SIZE=500` for single-pass cold starts (recommended).
The default of 50 is used for incremental batched updates.

The `SUMMARIZER_MODEL` is overridden in `.env` on the server to
`gemini-3.1-flash-lite-preview` for improved intelligence and speed.

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
this default. The channel summary is automatically appended to whichever
system prompt is active (M3 context injection).

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

# Optional
CONTEXT_BUDGET_PERCENT=80
DATABASE_PATH=./data/messages.db
LOG_LEVEL=INFO
```
