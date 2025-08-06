"""
Discord Bot - Main Entry Point
This file sets up and runs the Discord bot.
"""
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
import os

from utils.logging_utils import setup_logging, get_logger
from bot import create_bot

if __name__ == "__main__":
    # Initialize logging first
    setup_logging()
    logger = get_logger('main')
    
    logger.info("Starting Discord bot...")
    logger.info(f"Log level: {os.environ.get('LOG_LEVEL', 'INFO')}")
    logger.info(f"Log output: {os.environ.get('LOG_FILE', 'stdout')}")
    
    try:
        # Create and run the bot
        bot = create_bot()
        bot.run(os.environ['DISCORD_TOKEN'])
    except KeyError as e:
        logger.error(f"Missing required environment variable: {e}")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
