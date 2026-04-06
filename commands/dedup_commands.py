# commands/dedup_commands.py
# Version 1.0.0
"""
Duplicate message cleanup: identify and soft-delete repeated test messages.

CREATED v1.0.0: Test message deduplication (SOW v5.8.1)
- !debug dedup         — scan for messages appearing 3+ times, show report
- !debug dedup confirm — execute: soft-delete dupes, clean embeddings +
                         cluster_messages, mark clusters needs_resummarize=1

Soft-deletes only (is_deleted=1). Embeddings and cluster_messages are hard-
deleted (derived data). Oldest copy of each duplicate group is kept.
All output ℹ️ prefixed.
"""
import asyncio
import sqlite3
from collections import defaultdict
from config import DATABASE_PATH
from utils.logging_utils import get_logger

logger = get_logger('commands.dedup')

_I = "ℹ️ "


def _scan_duplicates(channel_id):
    """Return list of (content, count, keep_id, dupe_ids) for 3+ dupe groups.

    Excludes noise/command messages. Sorted by count descending.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, content FROM messages "
            "WHERE channel_id=? AND is_deleted=0 "
            "  AND content != '' AND content NOT LIKE '!%' "
            "  AND content NOT LIKE '\u2139\ufe0f%' "
            "  AND content NOT LIKE '\u2699\ufe0f%' "
            "ORDER BY id ASC",
            (channel_id,)
        ).fetchall()
    except Exception as e:
        logger.warning(f"_scan_duplicates failed ch:{channel_id}: {e}")
        return []
    finally:
        conn.close()

    groups = defaultdict(list)
    for msg_id, content in rows:
        groups[content].append(msg_id)

    result = []
    for content, ids in groups.items():
        if len(ids) >= 3:
            result.append((content, len(ids), ids[0], ids[1:]))
    return sorted(result, key=lambda x: -x[1])


def _execute_dedup(channel_id, dupes):
    """Soft-delete dupes and clean derived data. Returns (removed, emb, clusters).

    Raises on any DB error (caller handles).
    """
    all_dupe_ids = []
    for _, _, _, dupe_ids in dupes:
        all_dupe_ids.extend(dupe_ids)

    if not all_dupe_ids:
        return 0, 0, 0

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        ph = ','.join('?' * len(all_dupe_ids))

        # Find affected clusters before deletion
        cluster_rows = conn.execute(
            f"SELECT DISTINCT cluster_id FROM cluster_messages "
            f"WHERE message_id IN ({ph})",
            all_dupe_ids
        ).fetchall()

        # Soft-delete messages
        conn.execute(
            f"UPDATE messages SET is_deleted=1 WHERE id IN ({ph})",
            all_dupe_ids)
        msgs_removed = conn.execute("SELECT changes()").fetchone()[0]

        # Hard-delete derived data
        conn.execute(
            f"DELETE FROM message_embeddings WHERE message_id IN ({ph})",
            all_dupe_ids)
        emb_deleted = conn.execute("SELECT changes()").fetchone()[0]

        conn.execute(
            f"DELETE FROM cluster_messages WHERE message_id IN ({ph})",
            all_dupe_ids)

        # Mark affected clusters dirty
        for (cluster_id,) in cluster_rows:
            conn.execute(
                "UPDATE clusters SET needs_resummarize=1 WHERE id=?",
                (cluster_id,))
            logger.debug(f"Marked cluster {cluster_id} needs_resummarize")

        conn.commit()
        return msgs_removed, emb_deleted, len(cluster_rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def register_dedup_commands(debug_cmd):
    """Add !debug dedup [confirm] subcommand to the !debug group."""

    @debug_cmd.command(name='dedup')
    async def debug_dedup(ctx, action: str = None):
        """Identify and remove duplicate test messages.
        Usage: !debug dedup | !debug dedup confirm"""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return

        channel_id = ctx.channel.id
        await ctx.send(f"{_I}Scanning #{ctx.channel.name} for duplicates...")

        dupes = await asyncio.to_thread(_scan_duplicates, channel_id)

        if not dupes:
            await ctx.send(
                f"{_I}No duplicate messages (3+ identical) found in "
                f"#{ctx.channel.name}.")
            return

        total_to_remove = sum(cnt - 1 for _, cnt, _, _ in dupes)

        if action != 'confirm':
            lines = [f"**Duplicate Scan** (#{ctx.channel.name})", ""]
            lines.append(
                f"Messages appearing 3+ times (oldest copy kept):")
            for content, cnt, _, _ in dupes[:20]:
                preview = content[:60] + ("…" if len(content) > 60 else "")
                lines.append(f"  \"{preview}\" — {cnt} copies, {cnt-1} to remove")
            if len(dupes) > 20:
                lines.append(f"  ... and {len(dupes) - 20} more unique texts")
            lines += [
                "",
                f"Total: {total_to_remove} messages to remove "
                f"({len(dupes)} originals kept)",
                "Run `!debug dedup confirm` to proceed.",
            ]
            from utils.summary_display import send_paginated
            await send_paginated(ctx, lines)
            return

        # Execute dedup
        try:
            removed, emb, clusters = await asyncio.to_thread(
                _execute_dedup, channel_id, dupes)
            await ctx.send(
                f"{_I}**Dedup Complete** (#{ctx.channel.name})\n"
                f"Removed: {removed} duplicate messages "
                f"({len(dupes)} originals kept)\n"
                f"Embeddings deleted: {emb}\n"
                f"Clusters marked dirty: {clusters}\n\n"
                f"Run `!debug reembed` then `!summary create` to rebuild.")
            logger.info(
                f"Dedup ch:{channel_id}: {removed} removed, "
                f"{emb} embeddings, {clusters} clusters dirtied")
        except Exception as e:
            await ctx.send(f"{_I}Dedup failed: {e}")
            logger.error(f"Dedup error ch:{channel_id}: {e}")
