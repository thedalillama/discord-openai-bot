# README_ENV.md
# Version 2.22.0
# Environment Variables Configuration Guide

This document provides comprehensive documentation for all environment
variables used by the Discord AI Bot.

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token from Discord Developer Portal | `your_discord_bot_token` |

## API Keys

Set only the API keys for providers you plan to use:

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for GPT models and image generation | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models | `sk-ant-...` |
| `OPENAI_COMPATIBLE_API_KEY` | API key for OpenAI-compatible providers (DeepSeek, etc.) | `sk-...` |

## Core Bot Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `AI_PROVIDER` | Default AI provider for new channels | `openai` | `openai`, `anthropic`, `deepseek` |
| `AUTO_RESPOND` | Enable auto-response by default | `false` | `true`, `false` |
| `BOT_PREFIX` | Bot mention prefix for direct addressing | `Bot, ` | Any string |
| `DEFAULT_TEMPERATURE` | Creativity level for AI responses | `0.7` | `0.0` to `2.0` |

## Message and History Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `MAX_HISTORY` | Messages to keep in conversation context | `10` | Any positive integer |
| `INITIAL_HISTORY_LOAD` | Messages to load when starting in a channel | `50` | Any positive integer |
| `MAX_RESPONSE_TOKENS` | Maximum tokens per AI response | `800` | Any positive integer |
| `HISTORY_LINE_PREFIX` | Prefix for history display messages | `➤ ` | Any string |

## OpenAI Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o-mini` | Any valid OpenAI model |
| `OPENAI_CONTEXT_LENGTH` | Maximum context length for OpenAI | `128000` | Model-dependent |
| `OPENAI_MAX_TOKENS` | Maximum tokens per OpenAI response | `1500` | Model-dependent |
| `ENABLE_IMAGE_GENERATION` | Enable automatic image generation | `true` | `true`, `false` |

## Anthropic Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `ANTHROPIC_MODEL` | Claude model to use | `claude-haiku-4-5-20251001` | Any valid Claude model |
| `ANTHROPIC_CONTEXT_LENGTH` | Maximum context length for Claude | `200000` | Model-dependent |
| `ANTHROPIC_MAX_TOKENS` | Maximum tokens per Claude response | `2000` | Model-dependent |

## OpenAI-Compatible Provider Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `OPENAI_COMPATIBLE_BASE_URL` | API base URL | None | `https://api.deepseek.com`, `https://openrouter.ai/api/v1`, etc. |
| `OPENAI_COMPATIBLE_MODEL` | Model to use | `deepseek-chat` | Provider-dependent |
| `OPENAI_COMPATIBLE_CONTEXT_LENGTH` | Maximum context length | `128000` | Model-dependent |
| `OPENAI_COMPATIBLE_MAX_TOKENS` | Maximum tokens per response | `8000` | Model-dependent |

## Logging Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `LOG_LEVEL` | Logging verbosity level | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | Log output destination | `stdout` | `stdout` or file path |
| `LOG_FORMAT` | Log message format | Standard format | Custom format string |

## System Prompt Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_SYSTEM_PROMPT` | Default system prompt for AI responses | `"You are a helpful assistant in a Discord server. Respond in a friendly, concise manner. You have been listening to the conversation and can reference it in your replies."` |

---

## Example Configuration Files

### Basic Setup (.env)
```bash
# Required
DISCORD_TOKEN=your_discord_bot_token

# Choose your primary provider
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat

# Optional customization
AUTO_RESPOND=false
MAX_HISTORY=15
LOG_LEVEL=INFO
```

### Multi-Provider Setup (.env)
```bash
# Required
DISCORD_TOKEN=your_discord_bot_token

# All providers available
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com

# Configuration
AI_PROVIDER=deepseek
AUTO_RESPOND=false
MAX_HISTORY=20
MAX_RESPONSE_TOKENS=1200
LOG_LEVEL=DEBUG
LOG_FILE=/var/log/discord-bot.log
```

### Production Setup (.env)
```bash
# Core Configuration
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek

# API Keys (set only what you use)
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat
OPENAI_API_KEY=your_openai_key  # For image generation only

# Production Settings
AUTO_RESPOND=false
MAX_HISTORY=10
MAX_RESPONSE_TOKENS=800
LOG_LEVEL=INFO
LOG_FILE=stdout

# Cost Optimization
OPENAI_MAX_TOKENS=1000
ANTHROPIC_MAX_TOKENS=1500
OPENAI_COMPATIBLE_MAX_TOKENS=8000
```

### DeepSeek Reasoner Setup (.env)
```bash
# Use deepseek-reasoner for chain-of-thought reasoning display
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
OPENAI_COMPATIBLE_MAX_TOKENS=8000

# Then in Discord: !thinking on
# Bot will display full reasoning_content before each answer
```

---

## Provider-Specific Notes

### OpenAI
- Supports both text generation and image creation via DALL-E
- Uses Responses API with integrated image generation tools
- Set `ENABLE_IMAGE_GENERATION=false` to disable image generation and
  reduce costs

### Anthropic (Claude)
- Text-only responses with large context windows (200K tokens)
- Excellent for complex reasoning and long document analysis
- Recommended model: `claude-haiku-4-5-20251001` (fast, cost-effective)

### DeepSeek (via OpenAI-Compatible Provider)
- **Most cost-effective option** for text generation
- Use `OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com`
- Two models available:
  - `deepseek-chat` — General purpose, fast, lowest cost. Recommended
    for most Discord use cases.
  - `deepseek-reasoner` — Chain-of-thought reasoning model. Returns
    `reasoning_content` alongside the answer. Use `!thinking on` in
    Discord to display the full reasoning process as a separate message
    before the answer. Reasoning is always logged regardless of
    `!thinking` setting.
- Reasoning content is never stored in conversation history or sent
  to the API — only the final answer is kept in context

### Other OpenAI-Compatible Providers
- **OpenRouter**: `OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1`
- **LocalAI / Ollama / LM Studio**: Use your local endpoint URL
- Any provider following OpenAI chat completions API standard

---

## Environment Variable Priority

1. **Environment variables** (highest priority)
2. **`.env` file values**
3. **Default values in config.py** (lowest priority)

---

## Security Considerations

- **Never commit API keys** to version control
- **Use `.env` files** for local development
- **Use environment variables** in production deployment
- **Rotate API keys** regularly
- **Limit API key permissions** when possible

---

## Troubleshooting

### Common Issues

**Bot won't start:**
- Check that `DISCORD_TOKEN` is set correctly
- Verify at least one AI provider API key is configured

**No AI responses:**
- Verify the API key for your chosen `AI_PROVIDER` is valid
- Check the logs for authentication errors

**Images not generating:**
- Ensure `OPENAI_API_KEY` is set (required for image generation)
- Check that `ENABLE_IMAGE_GENERATION=true`

**High costs:**
- Switch to DeepSeek `deepseek-chat` for lowest cost
- Reduce `MAX_HISTORY` to limit context size
- Lower `OPENAI_COMPATIBLE_MAX_TOKENS` for shorter responses

**Reasoning not displaying:**
- Confirm `OPENAI_COMPATIBLE_MODEL=deepseek-reasoner` (not deepseek-chat)
- Run `!thinking on` in the Discord channel
- Check logs for `DeepSeek reasoning for channel` at INFO level

**DeepSeek/OpenAI-Compatible Issues:**
- Verify `OPENAI_COMPATIBLE_BASE_URL` is correct for your provider
- Check `OPENAI_COMPATIBLE_MODEL` matches provider's available models
- Ensure API key has sufficient credits/permissions

### Log Analysis

Enable debug logging to troubleshoot issues:
```bash
LOG_LEVEL=DEBUG
LOG_FILE=debug.log
```

Check the logs for:
- `Instantiating XProvider (first use)` — provider initialized (once per type)
- `Returning cached X provider instance` — singleton reuse confirmed
- `DeepSeek reasoning for channel` — reasoning_content received (INFO)
- `DeepSeek reasoning present, thinking display disabled` — thinking off (DEBUG)
- `API response finished with reason: stop` — successful API call
