# README_ENV.md
# Version 2.10.1
# Environment Variables Configuration Guide

This document provides comprehensive documentation for all environment variables used by the Discord AI Bot.

## Required Variables

These variables **must** be set for the bot to function:

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token from Discord Developer Portal | `your_discord_bot_token` |

## API Keys

Set only the API keys for providers you plan to use:

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for GPT models and image generation | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models | `sk-ant-...` |
| `BASETEN_DEEPSEEK_KEY` | BaseTen API key for DeepSeek R1 model | `your_baseten_key` |

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
| `ANTHROPIC_MODEL` | Claude model to use | `claude-3-haiku-20240307` | Any valid Claude model |
| `ANTHROPIC_CONTEXT_LENGTH` | Maximum context length for Claude | `200000` | Model-dependent |
| `ANTHROPIC_MAX_TOKENS` | Maximum tokens per Claude response | `2000` | Model-dependent |

## DeepSeek Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `DEEPSEEK_MODEL` | DeepSeek model to use via BaseTen | `deepseek-ai/DeepSeek-R1` | BaseTen model path |
| `DEEPSEEK_CONTEXT_LENGTH` | Maximum context length for DeepSeek | `64000` | Model-dependent |
| `DEEPSEEK_MAX_TOKENS` | Maximum tokens per DeepSeek response | `4000` | Model-dependent |

## Logging Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | Log output destination | `stdout` | `stdout` or file path |
| `LOG_FORMAT` | Log message format | Complex format string | Any valid Python logging format |

## System Prompt Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_SYSTEM_PROMPT` | Default personality for the AI assistant | `"You are a helpful assistant in a Discord server. Respond in a friendly, concise manner. You have been listening to the conversation and can reference it in your replies."` |

## Example Configuration Files

### Basic Setup (.env)
```bash
# Required
DISCORD_TOKEN=your_discord_bot_token

# Choose your primary provider
AI_PROVIDER=deepseek
BASETEN_DEEPSEEK_KEY=your_baseten_key

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
BASETEN_DEEPSEEK_KEY=your_baseten_key

# Configuration
AI_PROVIDER=openai
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
BASETEN_DEEPSEEK_KEY=your_baseten_key
OPENAI_API_KEY=your_openai_key  # For image generation

# Production Settings
AUTO_RESPOND=false
MAX_HISTORY=10
MAX_RESPONSE_TOKENS=800
LOG_LEVEL=INFO
LOG_FILE=stdout

# Cost Optimization
OPENAI_MAX_TOKENS=1000
ANTHROPIC_MAX_TOKENS=1500
DEEPSEEK_MAX_TOKENS=3000
```

## Provider-Specific Notes

### OpenAI
- Supports both text generation and image creation
- Uses Responses API with integrated image generation tools
- Higher cost but includes DALL-E image generation

### Anthropic (Claude)
- Text-only responses with large context windows
- Excellent for complex reasoning and analysis
- Higher cost but superior context understanding

### DeepSeek (via BaseTen)
- Most cost-effective option for text generation
- Includes reasoning process display (`<think>` tags)
- Good balance of quality and cost

## Environment Variable Priority

1. **Environment variables** (highest priority)
2. **`.env` file values**
3. **Default values in config.py** (lowest priority)

## Security Considerations

- **Never commit API keys** to version control
- **Use `.env` files** for local development
- **Use environment variables** in production deployment
- **Rotate API keys** regularly
- **Limit API key permissions** when possible

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
- Reduce `MAX_HISTORY` to limit context size
- Lower `MAX_RESPONSE_TOKENS` for shorter responses
- Use DeepSeek for cost-effective text generation

### Log Analysis

Enable debug logging to troubleshoot configuration issues:
```bash
LOG_LEVEL=DEBUG
LOG_FILE=debug.log
```

Check the logs for:
- Configuration loading messages
- API authentication status
- Provider selection decisions
- Token usage information
