# README.md
# Version 2.10.1
# Discord AI Bot

A sophisticated Discord bot with multi-provider AI integration, conversation history management, and persistent configuration settings. Features seamless switching between OpenAI, Anthropic, and DeepSeek providers with automatic settings recovery and stable asynchronous operation.

## Features

### Multi-Provider AI Support
- **OpenAI Integration**: GPT models with image generation via DALL-E (async executor for stability)
- **Anthropic Integration**: Claude models with large context windows
- **DeepSeek Integration**: Cost-effective reasoning with thinking display control

### Advanced Configuration Management
- **Settings Persistence**: Automatic recovery of channel settings from Discord message history
- **Per-Channel Customization**: Individual system prompts and AI providers per channel
- **Auto-Response Control**: Configurable automatic responses with explicit on/off control
- **Thinking Display**: Toggle DeepSeek's reasoning process visibility

### Stability and Performance
- **Async Operation**: Non-blocking API calls prevent Discord heartbeat issues
- **Background Processing**: Long-running tasks don't interfere with bot responsiveness
- **Thread-Safe Execution**: Proper async handling for all AI provider interactions

### Direct AI Addressing
- Address specific providers without changing defaults: `openai, draw me a picture`
- Seamless provider switching for single responses
- Clean conversation history without provider prefixes

## Quick Start

1. **Clone and install:**
   ```bash
   git clone <repository-url>
   cd discord-bot
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
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

### Channel Status
- `!status` - Display all current channel settings (system prompt, AI provider, auto-response, thinking)

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

### Auto-Response (Enhanced)
- `!autorespond` - Show current auto-response status
- `!autorespond on` - Enable auto-response for channel
- `!autorespond off` - Disable auto-response for channel
- `!autostatus` - Show auto-response status (alternative)
- `!autosetup` - Apply default auto-response setting

### History Management
- `!history [count]` - Display conversation history
- `!cleanhistory` - Remove commands from history
- `!loadhistory` - Reload channel message history

## Settings Persistence

**Automatic Recovery**: The bot automatically recovers the most recent channel settings from Discord message history when restarting. This includes:

- **System Prompts**: Custom AI personalities persist across restarts
- **AI Provider Settings**: Channel-specific provider choices are maintained
- **Auto-Response Settings**: Auto-response enabled/disabled state is preserved
- **Thinking Display Settings**: DeepSeek thinking visibility preferences are restored

**How it Works**: The bot scans recent Discord messages for confirmation messages (like "System prompt updated for #channel") and extracts the most recent settings automatically during startup.

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

## Stability Features

### Async Operation
- **Non-blocking AI calls**: All AI provider requests use proper async handling
- **Thread-safe execution**: OpenAI API calls wrapped in `asyncio.run_in_executor()`
- **Heartbeat protection**: Prevents Discord gateway timeouts during long operations
- **Background processing**: Image generation and complex requests don't block bot responsiveness

### Error Handling
- **Graceful degradation**: Bot continues operating if individual requests fail
- **Comprehensive logging**: Detailed logs for debugging and monitoring
- **Automatic recovery**: Settings restoration handles parsing errors gracefully

## Configuration

For comprehensive environment variable documentation, see **[README_ENV.md](README_ENV.md)**.

**Quick Start Configuration:**
```bash
# Required
DISCORD_TOKEN=your_discord_bot_token

# Choose your AI provider
AI_PROVIDER=deepseek
BASETEN_DEEPSEEK_KEY=your_baseten_key

# Optional settings
AUTO_RESPOND=false
LOG_LEVEL=INFO
```

## Deployment

### Docker Deployment
```bash
docker build -t discord-bot .
docker run -d --env-file .env discord-bot
```

### Production Considerations
1. Set `LOG_FILE=stdout` for service logging or specify a file path
2. Use process managers like systemd, Docker, or PM2
3. Monitor logs for structured output with module-specific logging
4. Configure appropriate AI model limits for your use case
5. Set up all required API keys for your chosen providers

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
MAX_HISTORY=10
LOG_LEVEL=INFO
BOT_PREFIX="Bot, "
```

See **[README_ENV.md](README_ENV.md)** for complete environment variable documentation.

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
- **250-line file limit** - Ensures all files remain readable and maintainable
- **Modular design** - Each file serves a single, well-defined purpose
- **Provider abstraction** - Easy to add new AI providers
- **Focused command modules** - Commands organized by functionality
- **Comprehensive logging** - Module-specific logging throughout
- **Type hints and documentation** - Well-documented code structure

When adding new features:
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

**Current Version**: 2.10.1 - Stability and Performance Enhancement
**Current State**: Production-ready with comprehensive settings persistence, enhanced command interface, and stable async operation
**Architecture**: All files under 250 lines, modular design, comprehensive documentation
**Recent Features**: Settings recovery from Discord messages, enhanced autorespond command, comprehensive status display, async API stability
**Maintainability**: Excellent - clean separation of concerns and focused modules
