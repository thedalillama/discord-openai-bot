# Discord AI Assistant Bot

A Discord bot that provides AI-powered responses using OpenAI and Anthropic APIs, with advanced conversation management and per-channel customization.

## Features

- **Multi-AI Provider Support** - Switch between OpenAI GPT and Anthropic Claude per channel
- **Custom System Prompts** - Set unique AI personalities for each channel
- **Conversation History** - Maintains context across conversations with smart filtering
- **Auto-Response Mode** - Configurable automatic responses to messages
- **Flexible Interaction** - Both command-based and prefix-based AI interaction
- **Comprehensive Logging** - Structured logging for production deployment
- **Modular Architecture** - Clean, maintainable codebase

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
- `!setai <provider>` - Switch AI provider (openai/anthropic)
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
!setai anthropic
Tell me a story
!setai openai  
Write a poem
```

## Configuration

| Variable | Description | Default | Valid Options |
|----------|-------------|---------|---------------|
| `DISCORD_TOKEN` | Discord bot token | Required | - |
| `OPENAI_API_KEY` | OpenAI API key | Required | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required | - |
| `AI_PROVIDER` | Default AI provider | `openai` | `openai`, `anthropic` |
| `ANTHROPIC_MODEL` | Claude model to use | `claude-3-5-sonnet-latest` | Any valid Claude model |
| `AUTO_RESPOND` | Default auto-response | `false` | `true`, `false` |
| `MAX_HISTORY` | Messages to remember | `10` | Any positive integer |
| `BOT_PREFIX` | Bot activation prefix | `Bot, ` | Any string |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | Log output destination | `stdout` | `stdout` or file path |

## Project Structure

```
discord-bot/
├── main.py                 # Entry point
├── bot.py                  # Core bot logic
├── config.py               # Configuration management
├── commands/               # Command modules
│   ├── __init__.py
│   ├── history_commands.py
│   └── auto_respond_commands.py
├── ai_providers/           # AI provider implementations
│   ├── __init__.py
│   ├── base.py
│   ├── openai_provider.py
│   └── anthropic_provider.py
└── utils/                  # Utility modules
    ├── ai_utils.py
    ├── logging_utils.py
    └── history/            # History management package
        ├── __init__.py
        ├── storage.py
        ├── prompts.py
        ├── message_processing.py
        └── loading.py
```

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

**Service logging includes:**
- `discord_bot.events` - Message and connection events
- `discord_bot.ai_providers` - AI provider operations
- `discord_bot.history.*` - Conversation management
- `discord_bot.commands.*` - Command execution

## License

MIT
