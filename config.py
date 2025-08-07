"""
Configuration module for the Discord bot.
Loads and provides access to environment variables and other configuration.
"""
import os

# Bot configuration
DEFAULT_AUTO_RESPOND = os.environ.get('AUTO_RESPOND', 'false').lower() == 'true'
MAX_HISTORY = int(os.environ.get('MAX_HISTORY', 10))
INITIAL_HISTORY_LOAD = int(os.environ.get('INITIAL_HISTORY_LOAD', 50))
MAX_RESPONSE_TOKENS = int(os.environ.get('MAX_RESPONSE_TOKENS', 800))
BOT_PREFIX = os.environ.get('BOT_PREFIX', 'Bot, ')
CHANNEL_LOCK_TIMEOUT = 30  # Timeout for acquiring a channel lock (in seconds)

# Default AI provider
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai')

# OpenAI configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
AI_MODEL = os.environ.get('AI_MODEL', 'gpt-4o-mini')
DEFAULT_TEMPERATURE = float(os.environ.get('DEFAULT_TEMPERATURE', 0.7))

# Anthropic configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-3-haiku-20240307')

# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.environ.get('LOG_FILE', 'stdout')
LOG_FORMAT = os.environ.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')

# History display configuration
HISTORY_LINE_PREFIX = os.environ.get('HISTORY_LINE_PREFIX', '➤ ')  # Default prefix that's unlikely to appear in normal messages

# System prompts
DEFAULT_SYSTEM_PROMPT = os.environ.get('DEFAULT_SYSTEM_PROMPT', 
    "You are a helpful assistant in a Discord server. Respond in a friendly, concise manner. You have been listening to the conversation and can reference it in your replies.")
