# utils/raw_events.py
# Version 1.0.2
"""
Discord event handlers for SQLite message persistence.

CREATED v1.0.0: SQLite message persistence (SOW v3.0.0)
- on_raw_message_create: Captures all messages to SQLite in real-time
- on_raw_message_edit: Updates stored content on message edits
- on_raw_message_delete: Soft-deletes messages (sets is_deleted flag)
- startup_backfill: Fetches missed messages after bot restart

CHANGES v1.0.1: Fix event registration
- FIXED: Changed @bot.event to bot.add_listener() for raw event handlers.

CHANGES v1.0.2: Fix message create not firing
- FIXED: on_raw_message_create never dispatched by commands.Bot when
  on_message is defined as @bot.event. Replaced with on_message listener
  for create events. Edit and delete remain as raw listeners since they
  have no equivalent cached event conflict.
- ADDED: Bot's own messages captured via separate on_message listener that
  does NOT skip bot messages (unlike bot.py's on_message which returns early).

These handlers are INDEPENDENT of the on_message response pipeline in
bot.py. The existing in-memory channel_history is untouched.
"""
import asyncio
from datetime import timezone

from utils.logging_utils import get_logger
from utils.models import StoredMessage
from utils.message_store import (
    insert_message, update_message_content, soft_delete_message,
    get_last_processed_id, update_last_processed_id,
    insert_messages_batch, init_database
)

logger = get_logger('raw_events')

# Limit concurrent channel fetches during backfill to avoid rate limits
_backfill_semaphore = asyncio.Semaphore(3)

# Maximum messages to fetch per channel during backfill
MAX_BACKFILL_PER_CHANNEL = 10000


def setup_raw_events(bot):
    """
    Register event handlers for SQLite persistence on the bot instance.

    Called from create_bot() after bot creation. Registers an on_message
    listener for capturing new messages, plus on_raw_message_edit and
    on_raw_message_delete for edits and deletes. Also initializes the
    SQLite database.

    The on_message listener is registered via bot.add_listener() which
    allows it to coexist with the @bot.event on_message in bot.py.
    bot.add_listener registers ADDITIONAL listeners; @bot.event sets
    the PRIMARY handler. Both fire for every message.

    Args:
        bot: The discord.py Bot instance
    """
    init_database()
    logger.info("SQLite message persistence initialized")

    async def persistence_on_message(message):
        """
        Capture every message (including bot's own) to SQLite.

        This is a SECOND on_message listener that runs alongside the
        primary on_message in bot.py. Unlike that handler, this one
        does NOT skip bot messages — bot responses are part of the
        conversation context needed for summarization.
        """
        # Skip DMs — only capture guild messages
        if message.guild is None:
            return

        msg = StoredMessage(
            id=message.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_name=(message.author.nick
                         if hasattr(message.author, 'nick') and message.author.nick
                         else message.author.display_name),
            content=message.content or "",
            created_at=message.created_at.replace(
                tzinfo=timezone.utc).isoformat()
            if message.created_at.tzinfo is None
            else message.created_at.isoformat(),
            message_type=message.type.value if hasattr(message.type, 'value') else 0,
            is_deleted=False
        )

        try:
            await asyncio.to_thread(insert_message, msg)
            await asyncio.to_thread(
                update_last_processed_id, msg.channel_id, msg.id
            )
        except Exception as e:
            logger.error(f"Failed to store message {msg.id}: {e}")

    async def on_raw_message_edit(payload):
        """Update stored content when a message is edited."""
        data = payload.data
        new_content = data.get("content")
        message_id = payload.message_id

        if new_content is None:
            return

        try:
            await asyncio.to_thread(update_message_content, message_id, new_content)
            logger.debug(f"Updated message {message_id} content")
        except Exception as e:
            logger.error(f"Failed to update message {message_id}: {e}")

    async def on_raw_message_delete(payload):
        """Soft-delete a message when it's deleted in Discord."""
        try:
            await asyncio.to_thread(soft_delete_message, payload.message_id)
            logger.debug(f"Soft-deleted message {payload.message_id}")
        except Exception as e:
            logger.error(f"Failed to soft-delete message {payload.message_id}: {e}")

    # Register on_message as additional listener (coexists with bot.py's handler)
    bot.add_listener(persistence_on_message, 'on_message')
    # Raw events for edit/delete (no conflict with cached handlers)
    bot.add_listener(on_raw_message_edit)
    bot.add_listener(on_raw_message_delete)
    logger.info("Message persistence listeners registered")


async def startup_backfill(bot):
    """
    Backfill missed messages after bot restart.

    For each visible text channel, fetches messages newer than the last
    stored message ID. On first run (no state), fetches up to
    MAX_BACKFILL_PER_CHANNEL recent messages.

    Args:
        bot: The discord.py Bot instance
    """
    logger.info("Starting message backfill...")
    tasks = []

    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                if channel.permissions_for(guild.me).read_messages:
                    tasks.append(_backfill_channel(channel))
            except Exception as e:
                logger.warning(f"Cannot check permissions for #{channel.name}: {e}")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = sum(r for r in results if isinstance(r, int))
        errors = sum(1 for r in results if isinstance(r, Exception))
        logger.info(f"Backfill complete: {total} messages across {len(tasks)} channels"
                     + (f" ({errors} errors)" if errors else ""))
    else:
        logger.info("No channels to backfill")


async def _backfill_channel(channel):
    """
    Backfill a single channel. Returns the number of messages stored.

    Uses the semaphore to limit concurrent Discord API fetches.
    """
    async with _backfill_semaphore:
        channel_id = channel.id
        last_id = await asyncio.to_thread(get_last_processed_id, channel_id)

        try:
            messages = []
            fetch_kwargs = {"limit": MAX_BACKFILL_PER_CHANNEL}
            if last_id:
                fetch_kwargs["after"] = discord_object_with_id(last_id)

            async for msg in channel.history(**fetch_kwargs, oldest_first=True):
                messages.append(StoredMessage(
                    id=msg.id,
                    channel_id=channel_id,
                    author_id=msg.author.id,
                    author_name=(msg.author.nick if hasattr(msg.author, 'nick')
                                 and msg.author.nick else msg.author.display_name),
                    content=msg.content or "",
                    created_at=msg.created_at.replace(
                        tzinfo=timezone.utc).isoformat()
                    if msg.created_at.tzinfo is None
                    else msg.created_at.isoformat(),
                    message_type=msg.type.value if hasattr(msg.type, 'value') else 0,
                    is_deleted=False
                ))

            if messages:
                await asyncio.to_thread(insert_messages_batch, messages)
                latest_id = messages[-1].id
                await asyncio.to_thread(
                    update_last_processed_id, channel_id, latest_id
                )
                if len(messages) >= MAX_BACKFILL_PER_CHANNEL:
                    logger.warning(
                        f"#{channel.name}: hit backfill cap ({MAX_BACKFILL_PER_CHANNEL}). "
                        "Some older messages may be missing."
                    )
                else:
                    logger.debug(f"#{channel.name}: backfilled {len(messages)} messages")

            return len(messages)

        except Exception as e:
            logger.error(f"Backfill failed for #{channel.name}: {e}")
            raise


def discord_object_with_id(snowflake_id):
    """Create a minimal object with an .id attribute for channel.history(after=...)."""
    import discord
    return discord.Object(id=snowflake_id)
