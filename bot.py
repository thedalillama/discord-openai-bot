# bot.py
# Version 3.2.0
"""
Core bot module that sets up the Discord bot and defines main event handlers.

CHANGES v3.2.0: Unpack citation_map from build_context_for_provider() (SOW v5.9.0)
- MODIFIED: Both call sites unpack 3-tuple (messages, receipt_data, citation_map)
  and pass citation_map to handle_ai_response()

CHANGES v3.1.0: Destructure (messages, receipt_data) from build_context_for_provider()
  (SOW v5.7.0)
- MODIFIED: Both call sites now unpack tuple return from build_context_for_provider()
  and pass receipt_data to handle_ai_response()

CHANGES v3.0.0: SQLite message persistence (SOW v3.0.0)
- ADDED: Import and call setup_raw_events() to register SQLite persistence handlers
- ADDED: Call startup_backfill() in on_ready() to catch missed messages on restart
- NOTE: The raw event handlers in raw_events.py are INDEPENDENT of the on_message
  pipeline below. The in-memory channel_history response path is unchanged.

CHANGES v2.10.0: Token-budget context management (SOW v2.23.0)
- MODIFIED: Direct addressing and auto-respond paths now resolve the provider
  first, then call build_context_for_provider() instead of
  prepare_messages_for_api() for API calls. This ensures every provider call
  fits within the provider's context window regardless of message content size.
- ADDED: Imports for build_context_for_provider and get_provider
- NOTE: prepare_messages_for_api() remains available for diagnostics/history
  commands but is no longer used on the API call path in this file.

CHANGES v2.9.0: Continuous context accumulation (SOW v2.18.0)
- FIXED: Regular messages now added to channel_history even when auto-respond
  is disabled. Bot always listens and accumulates context regardless of whether
  it is responding. When addressed directly after a silent period, the bot has
  full awareness of the intervening conversation.

CHANGES v2.8.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: INITIAL_HISTORY_LOAD import and on_ready() log line

CHANGES v2.7.0: Refactored AI response handling into separate module
CHANGES v2.6.0: Fixed missing import for parse_provider_override function
CHANGES v2.5.0: Refactored provider utilities into separate module
CHANGES v2.4.0: Refactored message utilities into separate module
"""
import discord
from discord.ext import commands
from collections import defaultdict
import datetime

from config import (
    DEFAULT_AUTO_RESPOND, MAX_HISTORY,
    MAX_RESPONSE_TOKENS, DEFAULT_SYSTEM_PROMPT, BOT_PREFIX
)
from utils.history import (
    load_channel_history, is_bot_command,
    channel_history, loaded_history_channels, channel_locks
)
from utils.logging_utils import get_logger
from utils.message_utils import format_user_message_for_history
from utils.provider_utils import parse_provider_override
from utils.response_handler import handle_ai_response
from utils.context_manager import build_context_for_provider
from ai_providers import get_provider
from utils.raw_events import setup_raw_events, startup_backfill

from commands import register_commands

auto_respond_channels = set()

def create_bot():
    """Create and configure the Discord bot"""
    logger = get_logger('events')

    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)

    # Initialize SQLite persistence and register raw event handlers
    setup_raw_events(bot)

    @bot.event
    async def on_ready():
        logger.info(f'{bot.user} has connected to Discord!')
        logger.info(f'Default auto-respond mode: {DEFAULT_AUTO_RESPOND}')
        logger.info(f'Max history: {MAX_HISTORY} messages')
        logger.info(f'Max response tokens: {MAX_RESPONSE_TOKENS}')

        if loaded_history_channels:
            logger.debug(f"Clearing loaded_history_channels dictionary. Had {len(loaded_history_channels)} entries.")
        loaded_history_channels.clear()

        if DEFAULT_AUTO_RESPOND:
            logger.info("Applying default auto-respond setting (enabled) to available channels")
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    try:
                        if channel.permissions_for(guild.me).send_messages:
                            auto_respond_channels.add(channel.id)
                            logger.info(f"  - Enabled auto-respond for #{channel.name} ({channel.id})")
                    except Exception as e:
                        logger.warning(f"  - Error enabling auto-respond for #{channel.name}: {e}")
        else:
            auto_respond_channels.clear()
            logger.info("Default auto-respond setting is disabled")

        # Backfill any messages missed while the bot was offline
        await startup_backfill(bot)

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        if message.content.startswith('/'):
            return

        if message.attachments:
            await bot.process_commands(message)
            return

        channel_id = message.channel.id

        logger.debug(f"Received message in #{message.channel.name} ({channel_id})")
        logger.debug(f"Message content: {message.content[:50]}...")
        logger.debug(f"Is channel in loaded_history_channels? {channel_id in loaded_history_channels}")
        logger.debug(f"Current channel history length: {len(channel_history.get(channel_id, []))}")

        provider_override, clean_message_content = parse_provider_override(message.content)

        # Load history on first message in channel
        if channel_id not in loaded_history_channels:
            logger.debug(f"Channel #{message.channel.name} not in loaded_history_channels, loading history...")
            try:
                async with message.channel.typing():
                    await load_channel_history(message.channel, is_automatic=True)
                    if len(channel_history[channel_id]) > 0:
                        logger.info(f"Auto-loaded {len(channel_history[channel_id])} messages for channel #{message.channel.name}")
                loaded_history_channels[channel_id] = datetime.datetime.now()
                logger.debug(f"Added channel #{message.channel.name} to loaded_history_channels")
            except Exception as e:
                logger.error(f"Failed to load history for channel #{message.channel.name}: {str(e)}")
        else:
            logger.debug(f"Channel #{message.channel.name} already in loaded_history_channels, skipping history load")

        is_prefix_message = message.content.lower().startswith(BOT_PREFIX.lower())
        is_provider_addressed = provider_override is not None

        # Handle direct addressing (bot prefix OR provider override)
        if is_prefix_message or is_provider_addressed:
            if is_prefix_message:
                logger.debug(f"Detected bot prefix message: {message.content}")
                content_for_history = message.content
            else:
                logger.debug(f"Detected provider override: {provider_override}")
                content_for_history = clean_message_content

            user_message = format_user_message_for_history(
                message.author.display_name,
                content_for_history,
                len(channel_history[channel_id])
            )
            channel_history[channel_id].append(user_message)

            # Trim to MAX_HISTORY
            if len(channel_history[channel_id]) > MAX_HISTORY:
                channel_history[channel_id] = channel_history[channel_id][-MAX_HISTORY:]

            # Resolve provider and build token-budget-aware context
            provider = get_provider(provider_name=provider_override, channel_id=channel_id)
            messages, receipt_data, citation_map = build_context_for_provider(channel_id, provider)
            await handle_ai_response(
                message, channel_id, messages, provider_override,
                receipt_data=receipt_data, citation_map=citation_map)
            await bot.process_commands(message)
            return

        # Skip commands — do not add to history
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        # All other messages: always add to history regardless of auto-respond state.
        # The bot always listens and accumulates context even when not responding,
        # so it has full awareness when addressed directly after a silent period.
        user_message = format_user_message_for_history(
            message.author.display_name,
            message.content,
            len(channel_history[channel_id])
        )
        channel_history[channel_id].append(user_message)

        # Trim to MAX_HISTORY
        if len(channel_history[channel_id]) > MAX_HISTORY:
            channel_history[channel_id] = channel_history[channel_id][-MAX_HISTORY:]

        logger.debug(f"Added message to history. New length: {len(channel_history[channel_id])}")

        # Respond only if auto-respond is enabled
        if channel_id in auto_respond_channels:
            logger.debug(f"Auto-responding to message in #{message.channel.name}")
            # Resolve provider and build token-budget-aware context
            provider = get_provider(channel_id=channel_id)
            messages, receipt_data, citation_map = build_context_for_provider(channel_id, provider)
            await handle_ai_response(message, channel_id, messages,
                                     receipt_data=receipt_data,
                                     citation_map=citation_map)

        await bot.process_commands(message)

    register_commands(bot, auto_respond_channels)
    return bot
