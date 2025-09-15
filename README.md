# README.md
# Version 2.8.0
# Discord AI Assistant Bot

A Discord bot that provides AI-powered responses using OpenAI, Anthropic, and BaseTen DeepSeek APIs, with advanced conversation management and per-channel customization.

## Features

- **Multi-AI Provider Support** - Switch between OpenAI GPT, Anthropic Claude, and BaseTen DeepSeek per channel
- **Direct AI Addressing** - Address specific AI providers directly without changing defaults (e.g., "openai, draw me a cat")
- **AI Image Generation** - Automatic image creation via OpenAI when contextually appropriate
- **Custom System Prompts** - Set unique AI personalities for each channel
- **Conversation History** - Maintains context across conversations with smart filtering
- **Auto-Response Mode** - Configurable automatic responses to messages
- **Flexible Interaction** - Both command-based and prefix-based AI interaction
- **Message Length Handling** - Automatically splits long responses to fit Discord's limits
- **Comprehensive Logging** - Structured logging for production deployment
- **Modular Architecture** - Clean, maintainable codebase with focused modules under 200 lines each

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

## Usage Examples

**Basic interaction:**
```
Bot, tell me about cats
```

**Direct AI provider addressing:**
```
openai, draw me a picture of a sunset
anthropic, write a poem about coding
deepseek, explain quantum physics
```

**Custom AI personality:**
```
!setprompt You are a helpful pirate assistant. Arrr!
Bot, what's the weather like?
```

**Provider switching with thinking control:**
```
!setai deepseek
!thinking on
What's the square root of 2?
[Shows detailed step-by-step reasoning]

!thinking off  
What's the square root of 3?
[Shows only final answer]
```

## Commands

### AI Provider Management
- `!setai <provider>` - Switch AI provider (openai/anthropic/deepseek)
- `!getai` - Show current AI provider
- `!resetai` - Reset to default provider

### DeepSeek Thinking Control
- `!thinking on` - Show DeepSeek's reasoning process (including `<think>` tags)
- `!thinking off` - Hide DeepSeek's reasoning process (default)
- `!thinking` - Check current thinking display setting
- `!thinkingstatus` - Alternative way to check current setting

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

## Direct AI Addressing

**Feature**: You can now directly address specific AI providers without changing the channel's default provider:

```
openai, create an image of a robot
anthropic, analyze this text for sentiment
deepseek, solve this math problem step by step
```

The bot will:
- Use the specified provider for that single response
- Keep the channel's default provider unchanged
- Clean the provider prefix from conversation history
- Work with both auto-response and direct bot addressing

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
- **Special Features**: Reasoning process display control with thinking commands

## Project Structure

```
discord-bot/
├── main.py                     # Entry point
├── bot.py                      # Core bot logic (185 lines, 42% reduction)
├── config.py                   # Configuration management
├── commands/                   # Command modules
│   ├── __init__.py
│   ├── history_commands.py     # History management commands
│   ├── prompt_commands.py      # System prompt commands
│   ├── ai_provider_commands.py # AI provider switching commands
│   ├── thinking_commands.py    # DeepSeek thinking display control
│   └── auto_respond_commands.py # Auto-response commands
├── ai_providers/               # AI provider implementations
│   ├── __init__.py
│   ├── base.py
│   ├── openai_provider.py      # OpenAI with image generation
│   ├── anthropic_provider.py   # Anthropic Claude
│   └── baseten_provider.py     # BaseTen DeepSeek R1
└── utils/                      # Utility modules (all under 200 lines)
    ├── ai_utils.py
    ├── logging_utils.py
    ├── message_utils.py        # Message formatting and splitting
    ├── provider_utils.py       # Provider override parsing
    ├── response_handler.py     # AI response handling
    └── history/                # Modular history management
        ├── __init__.py
        ├── storage.py          # Data storage and access
        ├── prompts.py          # System prompt management
        ├── message_processing.py # Message filtering and formatting
        ├── loading.py          # History loading coordination (150 lines)
        ├── discord_loader.py   # Discord API interactions (200 lines)
        ├── settings_parser.py  # Configuration parsing (120 lines)
        └── settings_manager.py # Settings validation & application (120 lines)
```

## Recent Updates

### Version 2.8.0 - Major Refactoring for Maintainability
- **Achieved 200-line file limit** - All files now under 200 lines for better maintainability
- **42% reduction in bot.py** - Core file reduced from 320 lines to 185 lines
- **Modular architecture** - Split large files into focused, single-purpose modules
- **Enhanced documentation** - Comprehensive docstrings and inline documentation
- **Configuration persistence foundation** - Infrastructure ready for settings persistence across restarts

#### Refactoring Details:
**bot.py (320→185 lines):**
- Extracted message utilities → `utils/message_utils.py`
- Extracted provider parsing → `utils/provider_utils.py`  
- Extracted response handling → `utils/response_handler.py`

**utils/history/loading.py (280→150 lines):**
- Extracted Discord API logic → `utils/history/discord_loader.py`
- Extracted settings parsing → `utils/history/settings_parser.py`
- Extracted settings management → `utils/history/settings_manager.py`

### Previous Updates
#### Version 2.3.0 - Direct AI Addressing
- **Added direct provider addressing** - Address specific AI providers without changing channel defaults
- **Fixed username duplication bug** - Resolved message formatting issues in API calls
- **Enhanced message parsing** - Clean provider prefix handling for natural conversation history
- **Improved provider consistency** - All providers now handle direct addressing uniformly

#### Version 2.2.0 - Enhanced AI Response Control
- **Added DeepSeek thinking control** with `!thinking on/off` commands to show/hide reasoning process
- **Removed artificial response truncation** - AI models now complete responses naturally
- **Enhanced message handling** - Message splitting manages Discord limits while preserving complete AI thoughts
- **Improved provider consistency** - All providers use natural stopping points instead of arbitrary token limits

#### Version 2.1.0 - Multi-Provider Enhancement
- **Added BaseTen DeepSeek R1 integration** for cost-effective text generation
- **Refactored command structure** into focused modules for better maintainability
- **Fixed Discord message length handling** - automatically splits responses over 2000 characters
- **Enhanced provider factory** with support for three AI providers
- **Improved error handling** for long responses and API failures

### Architecture Improvements
- **Modular Design**: Each file serves a single, well-defined purpose
- **Comprehensive Documentation**: Every module includes detailed docstrings and examples
- **Maintainable Codebase**: 200-line limit ensures files remain readable and manageable
- **Foundation for Future Features**: Clean architecture supports easy addition of new capabilities
- **Backward Compatibility**: All existing imports and APIs preserved during refactoring

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
- `discord_bot.history.*` - Conversation management (modular logging)
- `discord_bot.commands.*` - Command execution
- `discord_bot.message_utils` - Message processing and formatting
- `discord_bot.provider_utils` - Provider override handling
- `discord_bot.response_handler` - AI response processing

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
- Use direct addressing to access premium providers only when needed

## Contributing

The codebase follows a clean architecture with:
- **200-line file limit** - Ensures all files remain readable and maintainable
- **Modular design** - Each file serves a single, well-defined purpose
- **Provider abstraction** - Easy to add new AI providers
- **Focused command modules** - Commands organized by functionality
- **Comprehensive logging** - Module-specific logging throughout
- **Type hints and documentation** - Well-documented code structure

When adding new features:
1. Follow the 200-line limit for all new files
2. Create focused modules for new functionality
3. Follow the existing provider pattern for new AI integrations
4. Add commands to appropriate modules (or create new focused modules)
5. Include comprehensive logging with appropriate log levels
6. Test message length handling for any new response types
7. Update documentation and version numbers properly

## License

MIT

## Development Status

**Current State**: Production-ready with comprehensive refactoring completed
**Architecture**: All files under 200 lines, modular design, comprehensive documentation
**Next Priority**: Configuration Persistence feature (infrastructure ready)
**Maintainability**: Excellent - clean separation of concerns and focused modules
