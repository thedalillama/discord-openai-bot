"""
Core bot module that sets up the Discord bot and defines main event handlers.
"""
import discord
from discord.ext import commands
from collections import defaultdict
import asyncio

# Import config and utilities
from config import (
    DEFAULT_AUTO_RESPOND, MAX_HISTORY, INITIAL_HISTORY_LOAD,
    MAX_RESPONSE_TOKENS, DEFAULT_SYSTEM_PROMPT, BOT_PREFIX
)
from utils.ai_utils import generate_ai_response
from utils.history import (
    load_channel_history, is_bot_command, 
    channel_history, loaded_history_channels, channel_locks,
    prepare_messages_for_api
)
from utils.logging_utils import get_logger

# Import command modules
from commands import register_commands

# Set to store channels with auto-response enabled
auto_respond_channels = set()

def create_bot():
    """Create and configure the Discord bot"""
    logger = get_logger('events')
    
    # Set up the Discord bot with intents
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True  # This is required for the bot to read message content
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    # Register event handlers
    @bot.event
    async def on_ready():
        logger.info(f'{bot.user} has connected to Discord!')
        logger.info(f'Default auto-respond mode: {DEFAULT_AUTO_RESPOND}')
        logger.info(f'Max history: {MAX_HISTORY} messages')
        logger.info(f'Initial history load: {INITIAL_HISTORY_LOAD} messages')
        logger.info(f'Max response tokens: {MAX_RESPONSE_TOKENS}')
        
        # Clear the loaded history channels set on startup
        if loaded_history_channels:
            logger.debug(f"Clearing loaded_history_channels dictionary. Had {len(loaded_history_channels)} entries.")
        loaded_history_channels.clear()
        
        # Apply default auto-respond setting to all channels the bot can see
        if DEFAULT_AUTO_RESPOND:
            logger.info("Applying default auto-respond setting (enabled) to available channels")
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    try:
                        # Check if the bot has permission to send messages in this channel
                        if channel.permissions_for(guild.me).send_messages:
                            auto_respond_channels.add(channel.id)
                            logger.info(f"  - Enabled auto-respond for #{channel.name} ({channel.id})")
                    except Exception as e:
                        logger.warning(f"  - Error enabling auto-respond for #{channel.name}: {e}")
        else:
            # Clear auto-respond channels if default is set to false
            auto_respond_channels.clear()
            logger.info("Default auto-respond setting is disabled")

    @bot.event
    async def on_message(message):
        # Ignore messages from the bot itself
        if message.author == bot.user:
            return
            
        # Completely ignore messages that start with a slash (commands for other bots)
        if message.content.startswith('/'):
            return  # Skip processing commands and exit immediately
            
        # Ignore messages with attachments (images, files, etc.)
        if message.attachments:
            await bot.process_commands(message)
            return
        
        # Get channel ID
        channel_id = message.channel.id
        
        # Log information about this message
        logger.debug(f"Received message in #{message.channel.name} ({channel_id})")
        logger.debug(f"Message content: {message.content[:50]}...")
        logger.debug(f"Is channel in loaded_history_channels? {channel_id in loaded_history_channels}")
        logger.debug(f"Current channel history length: {len(channel_history.get(channel_id, []))}")
        
        # IMPORTANT: Move the history loading check to happen before command filtering
        # Automatically load history for this channel if it's not loaded yet
        if channel_id not in loaded_history_channels:
            logger.debug(f"Channel #{message.channel.name} not in loaded_history_channels, loading history...")
            
            try:
                # Show typing indicator while loading history (visual feedback)
                async with message.channel.typing():
                    # load_channel_history handles its own locking
                    # Pass is_automatic=True to skip the newest message (current one)
                    await load_channel_history(message.channel, is_automatic=True)
            
                    # Log that history was loaded automatically
                    if len(channel_history[channel_id]) > 0:
                        logger.info(f"Auto-loaded {len(channel_history[channel_id])} messages for channel #{message.channel.name}")
                
                # Only mark the channel as loaded AFTER successfully loading history
                import datetime
                loaded_history_channels[channel_id] = datetime.datetime.now()
                
                logger.debug(f"Added channel #{message.channel.name} to loaded_history_channels")
                logger.debug(f"Current loaded_history_channels: {list(loaded_history_channels.keys())}")
            
            except Exception as e:
                logger.error(f"Failed to load history for channel #{message.channel.name}: {str(e)}")
                # Don't add to loaded_history_channels on failure
        else:
            logger.debug(f"Channel #{message.channel.name} already in loaded_history_channels, skipping history load")
        
        # Check if message starts with the bot prefix
        if message.content.lower().startswith(BOT_PREFIX.lower()):
            logger.debug(f"Detected prefix message: {message.content}")
    
            # Extract the question (remove prefix)
            question = message.content[len(BOT_PREFIX):].strip()
    
            # Add the user's message to history
            user_name = message.author.display_name
            clean_name = ''.join(c for c in user_name if c.isalnum() or c in '_-')
    
            if not clean_name or clean_name != user_name:
                channel_history[channel_id].append({
                    "role": "user",
                    "name": f"user_{len(channel_history[channel_id])}",
                    "content": f"{user_name}: {message.content}"
                })
            else:
                channel_history[channel_id].append({
                    "role": "user",
                    "name": clean_name,
                    "content": f"{user_name}: {message.content}"
                })
    
            # Generate and send response
            async with message.channel.typing():
                try:
                    # Use our function to prepare messages for API
                    messages = prepare_messages_for_api(channel_id)
            
                    # Generate a response - NOW PASSING CHANNEL_ID
                    bot_response = await generate_ai_response(messages, channel_id=channel_id)
            
                    # Send the response
                    await message.channel.send(bot_response)
            
                    # Add bot's response to the history
                    channel_history[channel_id].append({
                        "role": "assistant",
                        "content": bot_response
                    })
                except Exception as e:
                    error_msg = f"An error occurred: {str(e)}"
                    await message.channel.send(error_msg)
                    logger.error(f"Error processing prefix message: {e}")
    
            # Skip the auto-respond logic but still process other commands
            await bot.process_commands(message)
            return

        # Enhanced command filtering - skip ALL commands that start with !
        if message.content.startswith('!'):
            logger.debug(f"Detected command: {message.content}")
            logger.debug("Processing command and skipping history addition")
            
            await bot.process_commands(message)
            return  # Skip adding ANY commands to history
        
        # Add the message to the channel's history
        user_name = message.author.display_name
        
        # Store the message in history
        # Clean the username to match OpenAI's requirements (letters, numbers, underscores, hyphens only)
        clean_name = ''.join(c for c in user_name if c.isalnum() or c in '_-')
        
        # If the name is empty after cleaning or doesn't change, use a default
        if not clean_name or clean_name != user_name:
            # Add the message with the actual username in the content but a clean name parameter
            channel_history[channel_id].append({
                "role": "user", 
                "name": f"user_{len(channel_history[channel_id])}",
                "content": f"{user_name}: {message.content}"
            })
        else:
            # If the name is already clean, use it directly
            channel_history[channel_id].append({
                "role": "user", 
                "name": clean_name,
                "content": f"{user_name}: {message.content}"
            })
        
        logger.debug(f"Added message to history. New length: {len(channel_history[channel_id])}")
        
        # Trim history if it gets too long
        if len(channel_history[channel_id]) > MAX_HISTORY:
            old_length = len(channel_history[channel_id])
            channel_history[channel_id] = channel_history[channel_id][-MAX_HISTORY:]
            logger.debug(f"Trimmed history from {old_length} to {len(channel_history[channel_id])} messages")
        
        # Check if we should auto-respond using is_bot_command
        should_auto_respond = (
            channel_id in auto_respond_channels and
            not is_bot_command(message.content)  # Don't auto-respond to commands
        )

        if should_auto_respond:
            logger.debug(f"Auto-responding to message: {message.content[:50]}...")
            
            async with message.channel.typing():
                try:
                    # Use our new function to prepare messages for API
                    messages = prepare_messages_for_api(channel_id)
                    
                    logger.debug(f"Prepared {len(messages)} messages for API")
                    logger.debug(f"System prompt: {messages[0]['content'][:50]}...")
                    
                    # Generate a response using our abstracted function - NOW PASSING CHANNEL_ID
                    bot_response = await generate_ai_response(messages, channel_id=channel_id)
                    
                    # Send the generated response back to the user
                    await message.channel.send(bot_response)
                    
                    # Add bot's response to the history
                    channel_history[channel_id].append({
                        "role": "assistant",
                        "content": bot_response
                    })
                    
                    logger.debug(f"Added bot response to history. New length: {len(channel_history[channel_id])}")
                    
                except Exception as e:
                    error_msg = f"An error occurred: {str(e)}"
                    await message.channel.send(error_msg)
                    logger.error(f"Error in auto-response: {e}")
        
        # Process commands (this is needed for the bot to respond to commands)
        await bot.process_commands(message)
    
    # Register all the command cogs
    register_commands(bot, auto_respond_channels)
    
    return bot
