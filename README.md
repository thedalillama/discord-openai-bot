# README.md
# Version 2.13.0
# Discord AI Bot

A Discord bot that integrates with multiple AI providers (OpenAI, Anthropic, DeepSeek) to provide intelligent responses and brainstorming support in Discord channels.

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

## AI Providers

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
ANTHROPIC_MODEL=claude-3-haiku-20240307
```

### DeepSeek (Cost-Effective Option)
```bash
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat
```

### Other OpenAI-Compatible Providers
```bash
# OpenRouter
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1

# Local APIs
OPENAI_COMPATIBLE_BASE_URL=http://localhost:8000
```

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

### `!thinking` — DeepSeek Thinking Display
| Usage | Description | Permission |
|-------|-------------|------------|
| `!thinking` | Show current status and options | All users |
| `!thinking on` | Show DeepSeek reasoning process | 🔒 Admin |
| `!thinking off` | Hide DeepSeek reasoning process | 🔒 Admin |

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

## Configuration

See [README_ENV.md](README_ENV.md) for comprehensive environment variable documentation.

### Essential Configuration
```bash
# Bot Requirements
DISCORD_TOKEN=your_discord_bot_token

# Primary AI Provider
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_api_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com

# Optional Settings
AUTO_RESPOND=false
MAX_HISTORY=10
MAX_RESPONSE_TOKENS=800
LOG_LEVEL=INFO
```

## Architecture

### File Structure
```
├── main.py                    # Entry point
├── bot.py                     # Core Discord events
├── config.py                  # Configuration management
├── commands/                  # Modular command system
│   ├── history_commands.py
│   ├── prompt_commands.py
│   ├── ai_provider_commands.py
│   ├── auto_respond_commands.py
│   ├── thinking_commands.py
│   └── status_commands.py
├── ai_providers/              # AI provider implementations
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   └── openai_compatible_provider.py
└── utils/                     # Utility modules
    ├── ai_utils.py
    ├── logging_utils.py
    ├── message_utils.py
    └── history/               # History management
```

### Design Principles
- **Modular Architecture**: All files under 250 lines for maintainability
- **Single Responsibility**: Each module serves one clear purpose
- **Comprehensive Documentation**: Detailed docstrings and inline comments
- **Async Safety**: Thread-safe operations prevent Discord event loop blocking
- **Settings Persistence**: Automatic recovery from Discord message history

## Provider Comparison

| Provider | Strengths | Cost | Image Generation |
|----------|-----------|------|------------------|
| **DeepSeek** | Most cost-effective, reasoning display | ~$2.24/1M tokens | No |
| **OpenAI** | Image generation, latest models | ~$15/1M tokens | Yes (DALL-E) |
| **Anthropic** | Large context, excellent reasoning | ~$18/1M tokens | No |

**Recommendation**: Use DeepSeek for cost-effective text generation, OpenAI when image generation is needed.

## Deployment

### Production Considerations
1. Set `LOG_FILE=stdout` for service logging or specify a file path
2. Use process managers like systemd, Docker, or PM2
3. Monitor logs for structured output with module-specific logging
4. Configure appropriate AI model limits for your use case

**Environment variables for production:**
```bash
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
AUTO_RESPOND=false
MAX_HISTORY=20
LOG_LEVEL=INFO
```

## Contributing

When adding new features:
1. Follow the 250-line limit for all new files
2. Create focused modules for new functionality
3. Follow the existing provider pattern for new AI integrations
4. Add commands to appropriate modules (or create new focused modules)
5. Include comprehensive logging with appropriate log levels
6. Update documentation and version numbers properly

## License

MIT

## Development Status

**Current Version**: 2.13.0 - Command Interface Redesign
**Current State**: Production-ready with unified command interface, comprehensive settings persistence, stable async operation, and flexible provider architecture
**Architecture**: All files under 250 lines, modular design, comprehensive documentation
**Recent Features**: Unified command interface (15 → 6 commands), consistent permission model, provider backend identification, cost optimization
**Maintainability**: Excellent - clean separation of concerns and focused modules
