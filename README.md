# Discord AI Assistant Bot

A Discord bot that uses OpenAI's API to respond to messages and maintain conversation history.

## Features

- Auto-responds to messages in enabled channels
- Maintains conversation history for context
- Provides commands for interacting with the bot
- Automatically loads channel history when needed
- Configurable via environment variables
- Modular design for easy maintenance and extension
- Prevents duplicate messages in history
- Filters out bot commands and command outputs from history

## Setup

1. Clone the repository:
   ```
   git clone <repository-url>
   cd discord-bot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration:
   ```
   DISCORD_TOKEN=your_discord_token
   OPENAI_API_KEY=your_openai_api_key
   AUTO_RESPOND=false
   MAX_HISTORY=10
   INITIAL_HISTORY_LOAD=50
   MAX_RESPONSE_TOKENS=800
   AI_MODEL=gpt-4o-mini
   DEFAULT_TEMPERATURE=0.7
   ```

4. Run the bot:
   ```
   python main.py
   ```

## Commands

- `!ask <question>` - Ask a direct question to the bot
- `!autorespond` - Toggle auto-response for the current channel
- `!autostatus` - Show the current auto-response status
- `!autosetup` - Apply default auto-response setting to the channel
- `!history [count]` - Display recent conversation history
- `!loadhistory` - Manually load message history
- `!cleanhistory` - Remove bot commands from history

## Project Structure

```
discord-bot/
├── main.py                 # Entry point
├── bot.py                  # Core bot setup and event handlers
├── config.py               # Configuration and environment variables
├── commands/               # Command modules
│   ├── __init__.py
│   ├── history_commands.py     # History-related commands
│   └── auto_respond_commands.py # Auto-respond related commands
└── utils/                  # Utility functions
    ├── __init__.py
    ├── ai_utils.py         # AI response generation
    └── history_utils.py    # History management functions
```

## Recent Improvements

1. **Modular Code Structure**: Reorganized the code into logical modules for better maintainability.

2. **Automatic History Loading**: History is now loaded automatically when a channel becomes active.

3. **Timestamp-Based History**: Implemented a timestamp system to prevent duplicate messages when loading history.

4. **Command Output Filtering**: Added filters to prevent bot command outputs from being included in conversation history.

5. **Increased Token Limits**: Raised the default token limit to 800 to prevent truncated responses.

6. **Truncation Detection**: Added a message when responses are cut off due to token limits.

7. **Configurable AI Model**: Made the AI model configurable via environment variables.

## Environment Variables

| Variable              | Description                                    | Default Value |
|-----------------------|------------------------------------------------|---------------|
| DISCORD_TOKEN         | Discord bot token                              | Required      |
| OPENAI_API_KEY        | OpenAI API key                                | Required      |
| AUTO_RESPOND          | Default auto-response setting                  | false         |
| MAX_HISTORY           | Maximum messages to remember per channel       | 10            |
| INITIAL_HISTORY_LOAD  | Messages to load from history when empty       | 50            |
| MAX_RESPONSE_TOKENS   | Maximum tokens for AI responses                | 800           |
| AI_MODEL              | OpenAI model to use                           | gpt-4o-mini   |
| DEFAULT_TEMPERATURE   | Default creativity setting (0.0-1.0)           | 0.7           |

## Contributing

Feel free to submit issues or pull requests to improve the bot!

## License

MIT
