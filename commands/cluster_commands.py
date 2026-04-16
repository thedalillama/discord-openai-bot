# commands/cluster_commands.py
# Version 1.6.0
"""
Cluster/segment/proposition debug commands: backfill, reembed, segments, propositions.

CHANGES v1.6.0: Add !debug propositions — count + sample propositions (SOW v6.3.0)

CHANGES v1.5.0: Remove !debug clusters and !debug summarize_clusters (v6.3.0)
- REMOVED: debug_clusters — ran v5.x message-embedding clustering path
  (run_clustering() from cluster_store.py); has no effect on the v6.x segment
  retrieval path and creates a parallel cluster structure that retrieval ignores.
- REMOVED: debug_summarize_clusters — operated on clusters created by the now-
  removed debug_clusters command.
  Use !debug segments and !explain detail for v6.x diagnostics.

CHANGES v1.4.0: Add !debug segments — segment count, avg size, sample synthesis
previews (SOW v6.0.0).
CHANGES v1.3.0: Dead code cleanup (SOW v5.10.1)
CHANGES v1.2.0: Remove dead topic re-link from backfill (SOW v5.10.0)
CHANGES v1.1.0: Pre-batch raw embeddings in backfill (SOW v5.8.2)
CREATED v1.0.0: Extracted from debug_commands.py v1.7.0 (SOW v5.6.0).
All subcommands require administrator permissions.
Registered via register_cluster_commands(debug_cmd).
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('commands.cluster')

_I = "ℹ️ "


def register_cluster_commands(debug_cmd):
    """Add cluster subcommands to the existing !debug command group."""

    @debug_cmd.command(name='backfill')
    async def debug_backfill(ctx, *, flags=""):
        """Embed messages lacking embeddings using contextual text."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        await ctx.send(f"{_I}Starting embedding backfill for #{ctx.channel.name}...")
        try:
            import time
            from utils.embedding_store import (
                get_messages_without_embeddings, embed_texts_batch,
                store_message_embedding)
            from utils.embedding_context import build_contextual_text

            pending = await asyncio.to_thread(
                get_messages_without_embeddings, channel_id, 2000)
            await ctx.send(f"{_I}Found {len(pending)} messages to embed...")
            t0 = time.monotonic()
            embedded = failed = 0
            if pending:
                BATCH = 1000
                # Pre-batch all raw embeddings (1 API call) for similarity filter
                await ctx.send(f"{_I}Pre-computing raw embeddings...")
                raw_texts = [f"{author}: {content}" for _, content, author, _ in pending]
                raw_results = await asyncio.to_thread(embed_texts_batch, raw_texts, BATCH)
                raw_vec_map = {idx: vec for idx, vec in raw_results}
                raw_id_to_vec = {pending[i][0]: vec for i, vec in raw_vec_map.items()}
                await ctx.send(
                    f"{_I}Raw embeddings done ({len(raw_vec_map)}/{len(pending)}). "
                    f"Building contextual embeddings...")
                for batch_start in range(0, len(pending), BATCH):
                    batch = pending[batch_start:batch_start + BATCH]
                    ctx_texts = []
                    for i, (mid, content, author, reply_to_id) in enumerate(batch):
                        ctx_text = await asyncio.to_thread(
                            build_contextual_text, channel_id, mid, author, content,
                            reply_to_id=reply_to_id,
                            raw_vec=raw_vec_map.get(batch_start + i),
                            raw_vecs_cache=raw_id_to_vec)
                        ctx_texts.append(ctx_text)
                        done = batch_start + i + 1
                        if done % 100 == 0:
                            await ctx.send(f"{_I}Context: {done}/{len(pending)}...")
                    await ctx.send(
                        f"{_I}Embedding batch "
                        f"{batch_start + 1}–{batch_start + len(batch)}...")
                    results = await asyncio.to_thread(
                        embed_texts_batch, ctx_texts, BATCH)
                    result_map = {idx: vec for idx, vec in results}
                    for i, (mid, _, _, _) in enumerate(batch):
                        if i in result_map:
                            await asyncio.to_thread(
                                store_message_embedding, mid, result_map[i])
                            embedded += 1
                        else:
                            failed += 1
                    batch_end = min(batch_start + BATCH, len(pending))
                    logger.info(
                        f"Backfill batch {batch_start}–{batch_end - 1}: "
                        f"{len(results)} embedded, "
                        f"{len(batch) - len(results)} failed")
            elapsed = time.monotonic() - t0
            await ctx.send(
                f"{_I}Embedded {embedded}/{len(pending)} "
                f"({failed} failed) in {elapsed:.1f}s. Backfill complete.")
        except Exception as e:
            await ctx.send(f"{_I}Backfill failed: {e}")
            logger.error(f"Backfill error ch:{channel_id}: {e}")

    @debug_cmd.command(name='reembed')
    async def debug_reembed(ctx):
        """Delete all embeddings and re-embed every message with contextual text."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        await ctx.send(
            f"{_I}**Re-embed for #{ctx.channel.name}**\n"
            f"Deleting all existing embeddings and re-embedding with contextual "
            f"text. Run `!summary create` afterward to rebuild clusters.")
        try:
            from utils.embedding_store import delete_channel_embeddings
            deleted = await asyncio.to_thread(delete_channel_embeddings, channel_id)
            await ctx.send(f"{_I}Deleted {deleted} existing embeddings.")
            # Invoke backfill (reuse the registered command)
            await ctx.invoke(debug_backfill)
        except Exception as e:
            await ctx.send(f"{_I}Re-embed failed: {e}")
            logger.error(f"Reembed error ch:{channel_id}: {e}")

    @debug_cmd.command(name='segments')
    async def debug_segments(ctx):
        """Show segment count, avg size, and sample segments."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        try:
            import sqlite3
            from config import DATABASE_PATH
            from utils.segment_store import get_segment_count
            count = await asyncio.to_thread(get_segment_count, channel_id)
            if count == 0:
                await ctx.send(f"{_I}No segments. Run `!summary create` first.")
                return
            def _fetch():
                c = sqlite3.connect(DATABASE_PATH)
                try:
                    rows = c.execute(
                        "SELECT topic_label, synthesis, message_count, "
                        "first_message_at FROM segments WHERE channel_id=? "
                        "ORDER BY first_message_at ASC LIMIT 5",
                        (channel_id,)).fetchall()
                    avg = c.execute(
                        "SELECT AVG(message_count) FROM segments "
                        "WHERE channel_id=?", (channel_id,)).fetchone()[0]
                    return rows, avg
                finally:
                    c.close()
            samples, avg = await asyncio.to_thread(_fetch)
            lines = [f"**Segments #{ctx.channel.name}**: {count} total, "
                     f"avg {avg:.1f} msgs/segment", ""]
            for label, synth, n, first_at in samples:
                date = (first_at or "")[:10]
                preview = synth[:100] + "..." if len(synth) > 100 else synth
                lines.append(f"[{date}] **{label}** ({n})\n> {preview}")
            await _send_paginated(ctx, "\n".join(lines))
        except Exception as e:
            await ctx.send(f"{_I}Segments failed: {e}")
            logger.error(f"Segments error ch:{channel_id}: {e}")


    @debug_cmd.command(name='propositions')
    async def debug_propositions(ctx):
        """Show proposition count and sample propositions for this channel."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        try:
            from utils.proposition_store import (
                get_proposition_count, get_proposition_embeddings)
            total = await asyncio.to_thread(get_proposition_count, channel_id)
            if total == 0:
                await ctx.send(
                    f"{_I}No propositions for #{ctx.channel.name}. "
                    f"Run `!summary create` to generate them.")
                return
            rows = await asyncio.to_thread(get_proposition_embeddings, channel_id)
            embedded = len(rows)
            samples = rows[:5]
            lines = [
                f"**Propositions #{ctx.channel.name}**: "
                f"{total} total, {embedded} embedded", ""]
            for prop_id, seg_id, content, _ in samples:
                lines.append(f"• `{seg_id}`\n  {content}")
            await _send_paginated(ctx, "\n".join(lines))
        except Exception as e:
            await ctx.send(f"{_I}Propositions failed: {e}")
            logger.error(f"Propositions error ch:{channel_id}: {e}")


async def _send_paginated(ctx, text, limit=1900):
    """Send long text in ℹ️-prefixed chunks."""
    while text:
        chunk = text[:limit]
        if len(text) > limit:
            last_nl = chunk.rfind('\n')
            if last_nl > limit // 2:
                chunk = text[:last_nl]
        await ctx.send(f"{_I}{chunk}")
        text = text[len(chunk):].lstrip('\n')
