# Discord AI Bot
# Version 2.11.0

A Discord bot that provides AI-powered conversations using multiple AI providers (OpenAI, Anthropic, DeepSeek) with comprehensive conversation history, system prompt management, and enhanced command interface.

## Key Features

- **Multi-Provider AI Support**: OpenAI GPT models, Anthropic Claude, and DeepSeek via OpenAI-compatible provider
- **Conversation History**: Maintains context across messages with configurable history limits
- **System Prompt Management**: Customizable AI behavior per channel
- **Auto-Response Mode**: Optional automatic responses to all messages
- **Direct Provider Addressing**: Address specific AI providers without changing defaults
- **Image Generation**: Integrated DALL-E image generation with OpenAI provider
- **Settings Persistence**: Automatic recovery of all settings from Discord message history
- **Enhanced Status Display**: Comprehensive status overview with provider backend identification
- **Thinking Display Control**: Toggle DeepSeek reasoning process visibility

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
The bot supports any OpenAI-compatible API:
```bash
# OpenRouter
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1

# Local APIs
OPENAI_COMPATIBLE_BASE_URL=http://localhost:8000

# Other providers following OpenAI API standard
```

## Core Commands

### System Prompt Management
- `!setprompt <prompt>` - Set custom system prompt for current channel
- `!resetprompt` - Reset to default system prompt
- `!getprompt` - Display current system prompt

### AI Provider Control
- `!setai <provider>` - Set AI provider for current channel (`openai`, `anthropic`, `deepseek`)
- `!getai` - Display current AI provider
- `!resetai` - Reset to default AI provider

### Auto-Response Control
- `!autorespond` - Show current auto-response status
- `!autorespond on` - Enable auto-response to all messages
- `!autorespond off` - Disable auto-response
- `!resetautorespond` - Reset to default auto-response setting

### History Management
- `!history` - Display recent conversation history
- `!clearhistory` - Clear conversation history for current channel

### Status and Information
- `!status` - Comprehensive overview of all channel settings
- `!thinking on/off` - Control DeepSeek reasoning process display

### Direct Provider Addressing
Address specific providers without changing channel defaults:
- `openai, draw a picture of a sunset`
- `anthropic, explain quantum physics`
- `deepseek, solve this math problem`

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

## Development

### Prerequisites
- Python 3.8+
- Discord bot token
- At least one AI provider API key

### Dependencies
```bash
pip install discord.py openai anthropic python-dotenv
```

### Development Guidelines
1. Follow the 250-line limit for all new files
2. Create focused modules for new functionality
3. Follow the existing provider pattern for new AI integrations
4. Add commands to appropriate modules (or create new focused modules)
5. Include comprehensive logging with appropriate log levels
6. Test message length handling for any new response types
7. Update documentation and version numbers properly

## License

MIT

## Development Status

**Current Version**: 2.11.0 - Multi-Provider Enhancement with OpenAI-Compatible Support
**Current State**: Production-ready with comprehensive settings persistence, enhanced command interface, stable async operation, and flexible provider architecture
**Architecture**: All files under 250 lines, modular design, comprehensive documentation
**Recent Features**: OpenAI-compatible provider support, provider backend identification, BaseTen migration completed, cost optimization
**Maintainability**: Excellent - clean separation of concerns and focused modules
