# Discord AI Assistant Bot

A Discord bot that provides AI-powered responses using OpenAI, Anthropic, and BaseTen DeepSeek APIs, with advanced conversation management and per-channel customization.

## Features

- **Multi-AI Provider Support** - Switch between OpenAI GPT, Anthropic Claude, and BaseTen DeepSeek per channel
- **AI Image Generation** - Automatic image creation via OpenAI when contextually appropriate
- **Custom System Prompts** - Set unique AI personalities for each channel
- **Conversation History** - Maintains context across conversations with smart filtering
- **Auto-Response Mode** - Configurable automatic responses to messages
- **Flexible Interaction** - Both command-based and prefix-based AI interaction
- **Message Length Handling** - Automatically splits long responses to fit Discord's limits
- **Comprehensive Logging** - Structured logging for production deployment
- **Modular Architecture** - Clean, maintainable codebase with focused command modules

## Quick Start

1. **Clone and install:**
   ```bash
   git clone <repository-url>
   cd discord-bot
   pip install -r requirements.txt
   ```

2. **Create `.env` file:**
   ```bash
   DISCORD_TOKEN=your_discord_token
   OPENAI_API_KEY=your_openai_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   BASETEN_DEEPSEEK_KEY=your_baseten_api_key
   AI_PROVIDER=openai
   LOG_LEVEL=INFO
   LOG_FILE=stdout
   ```

3. **Run the bot:**
   ```bash
   python main.py
   ```

## Commands

### AI Provider Management
- `!setai <provider>` - Switch AI provider (openai/anthropic/deepseek)
- `!getai` - Show current AI provider
- `!resetai` - Reset to default provider

### System Prompts
- `!setprompt <prompt>` - Set custom AI personality
- `!getprompt` - Show current system prompt
- `!resetprompt` - Reset to default prompt

### Auto-Response
- `!autorespond` - Toggle auto-response for channel
- `!autostatus` - Show auto-response status
- `!autosetup` - Apply default auto-response setting

### History Management
- `!history [count]` - Display conversation history
- `!cleanhistory` - Remove commands from history
- `!loadhistory` - Reload channel message history

## Usage Examples

**Direct interaction:**
```
Bot, tell me about cats
```

**Custom AI personality:**
```
!setprompt You are a helpful pirate assistant. Arrr!
Bot, what's the weather like?
```

**Provider switching:**
```
!setai deepseek
Tell me a story
!setai anthropic  
Write a poem
!setai openai
Generate an image of a sunset
```

## Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `DISCORD_TOKEN` | Discord bot token | Required | - |
| `OPENAI_API_KEY` | OpenAI API key | Required | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required | - |
| `BASETEN_DEEPSEEK_KEY` | BaseTen DeepSeek API key | Required | - |
| `AI_PROVIDER` | Default AI provider | `openai` | `openai`, `anthropic`, `deepseek` |
| `ANTHROPIC_MODEL` | Claude model to use | `claude-3-haiku-20240307` | Any valid Claude model |
| `AUTO_RESPOND` | Default auto-response | `false` | `true`, `false` |
| `MAX_HISTORY` | Messages to remember | `10` | Any positive integer |
| `BOT_PREFIX` | Bot activation prefix | `Bot, ` | Any string |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | Log output destination | `stdout` | `stdout` or file path |

## AI Providers

### OpenAI (GPT Models)
- **Capabilities**: Text generation and image creation
- **API**: Uses Responses API for integrated text/image generation
- **Models**: Configurable via `AI_MODEL` (default: `gpt-4o-mini`)
- **Special Features**: Automatic image generation when contextually appropriate

### Anthropic (Claude)
- **Capabilities**: Text generation only
- **API**: Uses Messages API with separate system prompts
- **Models**: Configurable via `ANTHROPIC_MODEL`
- **Context**: Large 200k context window

### BaseTen (DeepSeek R1)
- **Capabilities**: Text generation only
- **API**: OpenAI-compatible interface via BaseTen
- **Model**: `deepseek-ai/DeepSeek-R1`
- **Context**: 64k context window, 8k max response tokens

## Project Structure

```
discord-bot/
├── main.py                     # Entry point
├── bot.py                      # Core bot logic with message handling
├── config.py                   # Configuration management
├── commands/                   # Command modules
│   ├── __init__.py
│   ├── history_commands.py     # History management commands
│   ├── prompt_commands.py      # System prompt commands
│   ├── ai_provider_commands.py # AI provider switching commands
│   └── auto_respond_commands.py # Auto-response commands
├── ai_providers/               # AI provider implementations
│   ├── __init__.py
│   ├── base.py
│   ├── openai_provider.py      # OpenAI with image generation
│   ├── anthropic_provider.py   # Anthropic Claude
│   └── baseten_provider.py     # BaseTen DeepSeek R1
└── utils/                      # Utility modules
    ├── ai_utils.py
    ├── logging_utils.py
    └── history/                # History management package
        ├── __init__.py
        ├── storage.py
        ├── prompts.py
        ├── message_processing.py
        └── loading.py
```

## Recent Updates

### Version 2.1.0 - Multi-Provider Enhancement
- **Added BaseTen DeepSeek R1 integration** for cost-effective text generation
- **Refactored command structure** into focused modules for better maintainability
- **Fixed Discord message length handling** - automatically splits responses over 2000 characters
- **Enhanced provider factory** with support for three AI providers
- **Improved error handling** for long responses and API failures

### Key Improvements
- **Message Splitting**: Long AI responses are now intelligently split at sentence/word boundaries
- **Modular Commands**: Commands organized into logical groups (history, prompts, AI providers, auto-respond)
- **DeepSeek Integration**: New cost-effective provider option with 64k context window
- **Better Error Recovery**: Graceful handling of API failures and length limits

## Deployment

**For production deployment:**

1. Set appropriate `LOG_LEVEL` for your environment:
   - `DEBUG` - Detailed logging for development and troubleshooting
   - `INFO` - General operational logging (recommended for production)
   - `WARNING` - Only warnings and errors
   - `ERROR` - Only error messages
2. Set `LOG_FILE=stdout` for service logging or specify a file path
3. Use process managers like systemd, Docker, or PM2
4. Monitor logs for structured output with module-specific logging
5. Configure appropriate AI model limits for your use case
6. Set up all required API keys for your chosen providers

**Service logging includes:**
- `discord_bot.events` - Message and connection events
- `discord_bot.ai_providers` - AI provider operations (openai, anthropic, deepseek)
- `discord_bot.history.*` - Conversation management
- `discord_bot.commands.*` - Command execution

**Environment variables for production:**
```bash
# Core Configuration
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek  # or openai, anthropic

# API Keys (set only the ones you plan to use)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key  
BASETEN_DEEPSEEK_KEY=your_baseten_key

# Optional Configuration
AUTO_RESPOND=false
MAX_HISTORY=20
LOG_LEVEL=INFO
BOT_PREFIX="Bot, "
```

## Cost Optimization

**Provider Cost Comparison (approximate):**
- **DeepSeek**: Most cost-effective for text-only tasks
- **OpenAI**: Moderate cost, includes image generation
- **Anthropic**: Higher cost, large context window

**Tips for cost management:**
- Use DeepSeek for general conversation and text tasks
- Reserve OpenAI for when image generation is needed
- Use Anthropic for tasks requiring large context understanding
- Monitor `MAX_HISTORY` to control context length and costs
- Consider shorter `MAX_RESPONSE_TOKENS` for budget-conscious deployments

## Contributing

The codebase follows a clean architecture with:
- **Provider abstraction** - Easy to add new AI providers
- **Modular commands** - Focused command modules for maintainability  
- **Comprehensive logging** - Module-specific logging throughout
- **Type hints and documentation** - Well-documented code structure

When adding new features:
1. Follow the existing provider pattern for new AI integrations
2. Add commands to appropriate modules (or create new focused modules)
3. Include comprehensive logging with appropriate log levels
4. Test message length handling for any new response types

## License

MIT
