# README_ENV.md
# Version 2.23.0
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

## Core Bot Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `AI_PROVIDER` | Default AI provider | `openai` | `openai`, `anthropic`, `deepseek` |
| `AUTO_RESPOND` | Auto-respond by default | `false` | `true`, `false` |
| `BOT_PREFIX` | Direct addressing prefix | `Bot, ` | Any string |
| `DEFAULT_TEMPERATURE` | AI creativity level | `0.7` | `0.0` to `2.0` |
| `MAX_HISTORY` | Messages kept in memory per channel | `10` | Any positive integer |
| `MAX_RESPONSE_TOKENS` | Max tokens per AI response | `800` | Any positive integer |
| `HISTORY_LINE_PREFIX` | Prefix for !history display | `➤ ` | Any string |

## Token Budget Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `CONTEXT_BUDGET_PERCENT` | % of context window for input | `80` | `50` to `95` |

Budget formula: `input_budget = (context_window × % / 100) − max_output_tokens`

The 20% default headroom absorbs tiktoken variance for Anthropic (~10-15%),
per-message formatting overhead, and provider-side hidden tokens. With
`MAX_HISTORY=10`, the budget is a safety net. Increase MAX_HISTORY (e.g., 50)
to let the token budget be the primary context decision-maker.

## OpenAI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_MODEL` | Model to use | `gpt-4o-mini` |
| `OPENAI_CONTEXT_LENGTH` | Context window | `128000` |
| `OPENAI_MAX_TOKENS` | Max response tokens | `1500` |
| `ENABLE_IMAGE_GENERATION` | Enable DALL-E image gen | `true` |

## Anthropic Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_MODEL` | Claude model | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_CONTEXT_LENGTH` | Context window | `200000` |
| `ANTHROPIC_MAX_TOKENS` | Max response tokens | `2000` |

## OpenAI-Compatible Provider Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_COMPATIBLE_BASE_URL` | API base URL | None |
| `OPENAI_COMPATIBLE_MODEL` | Model to use | `deepseek-chat` |
| `OPENAI_COMPATIBLE_CONTEXT_LENGTH` | Context window | `64000` |
| `OPENAI_COMPATIBLE_MAX_TOKENS` | Max response tokens | `8000` |

**DeepSeek context note:** Default is 64K based on DeepSeek's pricing-details
page (verified 2025-02-26). Their models page claims 128K but the API enforces
64K. Override via env var if your provider confirms a higher limit.

## Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Verbosity | `INFO` (`DEBUG`, `WARNING`, `ERROR`) |
| `LOG_FILE` | Output destination | `stdout` (or file path) |
| `LOG_FORMAT` | Message format | Standard format string |

## System Prompt

| Variable | Default |
|----------|---------|
| `DEFAULT_SYSTEM_PROMPT` | `"You are a helpful assistant in a Discord server. Respond in a friendly, concise manner. You have been listening to the conversation and can reference it in your replies."` |

---

## Example Configurations

### Basic DeepSeek (.env)
```bash
DISCORD_TOKEN=your_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat
```

### Multi-Provider (.env)
```bash
DISCORD_TOKEN=your_token
AI_PROVIDER=deepseek
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
MAX_HISTORY=20
LOG_LEVEL=DEBUG
```

### DeepSeek Reasoner (.env)
```bash
DISCORD_TOKEN=your_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
# Then in Discord: !thinking on
```

---

## Provider-Specific Notes

**OpenAI** — Supports text + image generation via DALL-E Responses API. Set
`ENABLE_IMAGE_GENERATION=false` to disable and reduce costs.

**Anthropic** — Text-only, large context (200K). Recommended model:
`claude-haiku-4-5-20251001` (fast, cost-effective).

**DeepSeek** — Most cost-effective. Two models: `deepseek-chat` (general,
fastest) and `deepseek-reasoner` (CoT reasoning via `!thinking on`).
Reasoning is never stored in history.

**Other compatible providers** — OpenRouter (`https://openrouter.ai/api/v1`),
LocalAI, Ollama, LM Studio — any OpenAI chat completions API.

---

## Priority: env vars > .env file > config.py defaults

## Security
Never commit API keys. Use `.env` for dev, env vars in production. Rotate
keys regularly. Limit permissions when possible.

---

## Troubleshooting

**Bot won't start** — Check DISCORD_TOKEN and at least one API key.

**No AI responses** — Verify API key for chosen AI_PROVIDER; check logs.

**Images not generating** — Need OPENAI_API_KEY + ENABLE_IMAGE_GENERATION=true.

**High costs** — Use deepseek-chat, reduce MAX_HISTORY, lower MAX_TOKENS.

**Context window errors** — Verify OPENAI_COMPATIBLE_CONTEXT_LENGTH matches
your provider (DeepSeek=64K). Lower CONTEXT_BUDGET_PERCENT for more headroom.

**Reasoning not showing** — Need OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
and `!thinking on` in Discord.

### Key Log Messages (LOG_LEVEL=DEBUG)
- `Instantiating XProvider (first use)` — provider init (once per type)
- `Context budget for <provider>` — token budget calculation
- `Context built: N tokens, M/T messages` — context stats
- `Token budget trim: dropped N oldest` — budget enforcement (INFO)
- `Token usage [provider] ch:ID: N in + N out` — per-call usage (INFO)
- `Cumulative [provider] ch:ID: N in + N out (N calls)` — running total
- `DeepSeek reasoning for channel` — reasoning received (INFO)
