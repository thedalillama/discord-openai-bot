# utils/raw_events.py
# Version 1.6.0
"""
Discord event handlers for SQLite message persistence.

CHANGES v1.6.0: Context-prepended embeddings on arrival (SOW v5.6.0)
- embed path uses build_contextual_text(); graceful fallback to raw text
CHANGES v1.5.0: _looks_like_diagnostic() guard — skip unprefixed bot diagnostics
CHANGES v1.4.0: Assign new messages to nearest cluster on arrival (SOW v5.4.0)
CHANGES v1.3.0: Embed message vectors on arrival (SOW v4.0.0)
CHANGES v1.0.x-v1.2.0: reply, thread, attachments, is_bot_author capture
CREATED v1.0.0: on_message → SQLite, on_raw_message_edit/delete, startup_backfill
"""
import asyncio
import json
import discord
from datetime import timezone

from utils.logging_utils import get_logger
from utils.models import StoredMessage
from utils.message_store import (
    insert_message, update_message_content_and_edit_time, soft_delete_message,
    get_last_processed_id, update_last_processed_id,
    insert_messages_batch, init_database
)

logger = get_logger('raw_events')

# Limit concurrent channel fetches during backfill to avoid rate limits
_backfill_semaphore = asyncio.Semaphore(3)

# Diagnostic output that must never be embedded even without ℹ️ prefix
_DIAGNOSTIC_PREFIXES = (
    'Cluster ', 'Parameters:', 'Processed:',
    '**Cluster Analysis', '**Cluster Summariz', '**Overview**',
)


def _looks_like_diagnostic(content):
    return any(content.startswith(p) for p in _DIAGNOSTIC_PREFIXES)

# Maximum messages to fetch per channel during backfill
MAX_BACKFILL_PER_CHANNEL = 10000


def _get_attachments_metadata(message):
    """Return JSON string of attachment info, or None if no attachments."""
    if not message.attachments:
        return None
    return json.dumps([
        {"filename": a.filename, "size": a.size, "content_type": a.content_type}
        for a in message.attachments
    ])


def setup_raw_events(bot):
    """Register persistence listeners: on_message, on_raw_message_edit/delete."""
    init_database()
    logger.info("SQLite message persistence initialized")

    async def persistence_on_message(message):
        """Capture every message (including bot's own) to SQLite."""
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
            is_deleted=False,
            reply_to_message_id=(message.reference.message_id
                                 if message.reference else None),
            thread_id=(message.channel.id
                       if isinstance(message.channel, discord.Thread) else None),
            attachments_metadata=_get_attachments_metadata(message),
            is_bot_author=message.author.bot,
        )

        try:
            await asyncio.to_thread(insert_message, msg)
            await asyncio.to_thread(
                update_last_processed_id, msg.channel_id, msg.id
            )
        except Exception as e:
            logger.error(f"Failed to store message {msg.id}: {e}")
            return

        # Embed message for semantic retrieval — skip noise, commands, and bot diagnostics
        content = msg.content
        if content and not content.startswith(('!', 'ℹ️', '⚙️')):
            if msg.is_bot_author and _looks_like_diagnostic(content):
                logger.debug(f"Skipping unprefixed bot diagnostic msg {msg.id}")
                return
            try:
                from utils.embedding_store import embed_and_store_message
                from utils.embedding_context import build_contextual_text
                ctx_text = await asyncio.to_thread(
                    build_contextual_text, msg.channel_id, msg.id,
                    msg.author_name, content, reply_to_id=msg.reply_to_message_id)
                await asyncio.to_thread(embed_and_store_message, msg.id, ctx_text)
            except Exception as e:
                logger.warning(f"Embedding failed for msg {msg.id}: {e}")
                return

            # Assign to nearest cluster centroid (best-effort, silent on failure)
            try:
                from utils.cluster_assign import assign_to_nearest_cluster
                await asyncio.to_thread(
                    assign_to_nearest_cluster, msg.channel_id, msg.id
                )
            except Exception as e:
                logger.debug(f"Cluster assignment skipped for msg {msg.id}: {e}")

    async def on_raw_message_edit(payload):
        """Update stored content and edited_at when a message is edited."""
        data = payload.data
        new_content = data.get("content")
        message_id = payload.message_id

        if new_content is None:
            return

        try:
            await asyncio.to_thread(
                update_message_content_and_edit_time, message_id, new_content
            )
            logger.debug(f"Updated message {message_id} content and edited_at")
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

    Captures reply_to_message_id, thread_id, attachments_metadata, and
    is_bot_author from historical messages (available via Discord API).
    edited_at and deleted_at are not available during backfill.
    """
    async with _backfill_semaphore:
        channel_id = channel.id
        last_id = await asyncio.to_thread(get_last_processed_id, channel_id)

        try:
            messages = []
            fetch_kwargs = {"limit": MAX_BACKFILL_PER_CHANNEL}
            if last_id:
                fetch_kwargs["after"] = discord.Object(id=last_id)

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
                    is_deleted=False,
                    reply_to_message_id=(msg.reference.message_id
                                         if msg.reference else None),
                    thread_id=(msg.channel.id
                               if isinstance(msg.channel, discord.Thread) else None),
                    attachments_metadata=json.dumps([
                        {"filename": a.filename, "size": a.size,
                         "content_type": a.content_type}
                        for a in msg.attachments
                    ]) if msg.attachments else None,
                    is_bot_author=msg.author.bot,
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
