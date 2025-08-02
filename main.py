"""
Discord Bot - Main Entry Point
This file sets up and runs the Discord bot.
"""
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
import os

from bot import create_bot

if __name__ == "__main__":
    # Create and run the bot
    bot = create_bot()
    bot.run(os.environ['DISCORD_TOKEN'])
