# utils/logging_utils.py
# Version 1.1.0
"""
Logging utility functions for the Discord bot.

CHANGES v1.1.0: BotFilter suppresses third-party DEBUG noise
- ADDED: BotFilter on root handler — passes discord_bot.* at any level;
  all other loggers (httpcore, httpx, openai) only pass WARNING+.
  Root logger stays at DEBUG so bot logs are unaffected.

CREATED v1.0.0: setup_logging() and get_logger()
"""
import logging
import sys
import os
from config import LOG_LEVEL, LOG_FILE, LOG_FORMAT

def setup_logging():
    """
    Configure logging for the bot based on environment variables.
    
    Returns:
        logging.Logger: Configured logger for the bot
    """
    # Determine the handler based on LOG_FILE setting
    if LOG_FILE.lower() == 'stdout' or LOG_FILE == '':
        handler = logging.StreamHandler(sys.stdout)
    else:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        handler = logging.FileHandler(LOG_FILE)
    
    # Configure the handler
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
    # Filter: pass discord_bot.* at any level; everything else only at WARNING+.
    # This suppresses httpcore/httpx/openai DEBUG noise without muting our logs.
    class BotFilter(logging.Filter):
        def filter(self, record):
            return (record.name.startswith('discord_bot')
                    or record.levelno >= logging.WARNING)

    handler.addFilter(BotFilter())

    # Root logger accepts everything — the filter does the real gatekeeping.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    # Bot-specific logger at configured level
    bot_logger = logging.getLogger('discord_bot')
    bot_logger.setLevel(getattr(logging, LOG_LEVEL))
    
    return bot_logger

def get_logger(name):
    """
    Get a logger with the specified name under the discord_bot hierarchy.
    
    Args:
        name (str): Name for the logger (e.g., 'events', 'commands', 'ai')
    
    Returns:
        logging.Logger: Logger instance
    """
    return logging.getLogger(f'discord_bot.{name}')
