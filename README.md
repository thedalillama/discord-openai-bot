# README.md
# Version 2.22.0
# Discord AI Bot

A Discord bot that integrates with multiple AI providers (OpenAI, Anthropic,
DeepSeek) to provide intelligent responses and brainstorming support in
Discord channels.

## Quick Start

1. **Clone and install dependencies**:
   ```bash
   git clone <repository>
   cd discord-ai-bot
   pip install -r requirements.txt
   ```

2. **Configure environment** (create `.env` file):
   ```bash
   # Required
   DISCORD_TOKEN=your_discord_bot_token

   # Choose your AI provider
   AI_PROVIDER=deepseek
   OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
   OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
   OPENAI_COMPATIBLE_MODEL=deepseek-chat
   ```

3. **Run the bot**:
   ```bash
   python main.py
   ```

---

## AI Providers

### DeepSeek (Recommended — Cost-Effective)
```bash
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat        # Fast, cost-effective
# OPENAI_COMPATIBLE_MODEL=deepseek-reasoner  # Reasoning model with CoT display
```

**DeepSeek models:**
- `deepseek-chat` — General purpose, fast responses, lowest cost
- `deepseek-reasoner` — Chain-of-thought reasoning model; use with
  `!thinking on` to display full reasoning process in Discord

### OpenAI (GPT Models + Image Generation)
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
ENABLE_IMAGE_GENERATION=true
```

### Anthropic (Claude Models)
```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

### Other OpenAI-Compatible Providers
```bash
# OpenRouter
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1

# Local APIs (Ollama, LM Studio, etc.)
OPENAI_COMPATIBLE_BASE_URL=http://localhost:8000
```

### Provider Cost Comparison
| Provider | Model | Cost per 1M tokens |
|----------|-------|--------------------|
| DeepSeek | deepseek-chat | ~$0.27 input / $1.10 output |
| DeepSeek | deepseek-reasoner | ~$0.55 input / $2.19 output |
| Anthropic | claude-haiku-4-5 | ~$0.80 input / $4.00 output |
| OpenAI | gpt-4o-mini | ~$0.15 input / $0.60 output |

*Prices approximate — check provider docs for current rates.*

---

## Commands

🔒 = Administrator permission required

### `!prompt` — System Prompt
| Usage | Description | Permission |
|-------|-------------|------------|
| `!prompt` | Show current system prompt | All users |
| `!prompt <text>` | Set new system prompt | 🔒 Admin |
| `!prompt reset` | Reset to default prompt | 🔒 Admin |

### `!ai` — AI Provider
| Usage | Description | Permission |
|-------|-------------|------------|
| `!ai` | Show current provider and available options | All users |
| `!ai <provider>` | Set provider: `openai`, `anthropic`, `deepseek` | 🔒 Admin |
| `!ai reset` | Reset to default provider | 🔒 Admin |

### `!autorespond` — Auto-Response
| Usage | Description | Permission |
|-------|-------------|------------|
| `!autorespond` | Show current status and options | All users |
| `!autorespond on` | Enable auto-response to all messages | 🔒 Admin |
| `!autorespond off` | Disable auto-response | 🔒 Admin |

### `!thinking` — DeepSeek Reasoning Display
| Usage | Description | Permission |
|-------|-------------|------------|
| `!thinking` | Show current status and options | All users |
| `!thinking on` | Display full reasoning in Discord + log at INFO | 🔒 Admin |
| `!thinking off` | Answer only in Discord, reasoning logged at DEBUG | 🔒 Admin |

**Notes:**
- Only applies to `deepseek-reasoner` model which returns `reasoning_content`
- Reasoning content is always logged (INFO when on, DEBUG when off)
- Reasoning never stored in conversation history or sent to API
- Displayed as a separate message before the answer, prefixed with
  `[DEEPSEEK_REASONING]:`

### `!history` — History Management
| Usage | Description | Permission |
|-------|-------------|------------|
| `!history` | Display recent history (last 25 messages) | 🔒 Admin |
| `!history <count>` | Display N most recent messages | 🔒 Admin |
| `!history clean` | Remove commands/artifacts from history | 🔒 Admin |
| `!history reload` | Reload history from Discord | 🔒 Admin |

### `!status` — Channel Overview
| Usage | Description | Permission |
|-------|-------------|------------|
| `!status` | Show all current channel settings | All users |

### Direct Provider Addressing
Address a specific provider without changing channel defaults:
```
openai, draw a picture of a sunset
anthropic, explain quantum physics
deepseek, solve this math problem
```

---

## Configuration

See [README_ENV.md](README_ENV.md) for comprehensive environment variable
documentation.

---

## Architecture

### Provider Architecture
- **OpenAI Provider** — Responses API with optional image generation
- **Anthropic Provider** — Claude models via messages API
- **OpenAI-Compatible Provider** — Generic provider for DeepSeek, OpenRouter,
  local APIs, or any OpenAI-compatible endpoint

All providers use async executor wrappers to prevent Discord heartbeat
blocking during slow API calls. Provider instances are cached as singletons
for the lifetime of the bot.

### Settings Persistence
All channel settings (system prompt, AI provider, auto-respond, thinking
display) are automatically restored after bot restart by parsing Discord
message history. No external database required.

### History Management
- Per-channel conversation history with configurable `MAX_HISTORY` limit
- Noise filtering at three layers: runtime storage, load time, API payload
- Bot administrative messages never reach AI context
- Settings persistence messages kept in history for parser but filtered
  from API payload

### Contributing
1. Follow the 250-line limit for all new files
2. Create focused modules for new functionality
3. Follow the existing provider pattern for new AI integrations
4. Add commands to appropriate modules (or create new focused modules)
5. Include comprehensive logging with appropriate log levels
6. Update documentation and version numbers properly

---

## Development Status

**Current Version**: 2.22.0
**Branch**: development (stable, pending merge to main)
**State**: Production-ready

**Recent improvements:**
- Provider singleton caching — prevents httpx RuntimeError (v2.22.0)
- Async executor safety for all providers (v2.21.0)
- DeepSeek reasoning_content display with `!thinking` (v2.20.0)
- Three-layer history noise filtering (v2.19.0)
- Continuous context accumulation (v2.18.0)

---

## License

MIT
