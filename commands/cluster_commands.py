# commands/cluster_commands.py
# Version 1.1.0
"""
Cluster-related debug commands: backfill, reembed, clusters, summarize_clusters.

CHANGES v1.1.0: Pre-batch raw embeddings in backfill to eliminate per-message
  embed_text() calls (SOW v5.8.2)
- MODIFIED: debug_backfill() batch-embeds all raw texts in one API call before
  the context loop, builds raw_id_to_vec cache, passes raw_vec + raw_vecs_cache
  to build_contextual_text() — reduces API calls from N+1 to 2 for N messages
- ADDED: progress updates every 100 messages during context-building loop

CREATED v1.0.0: Extracted from debug_commands.py v1.7.0 (SOW v5.6.0)
- !debug backfill — contextual embedding backfill (v5.6.0: uses build_contextual_text)
- !debug reembed  — delete all embeddings + full re-embed with contextual text
- !debug clusters — run UMAP+HDBSCAN, show diagnostic report
- !debug summarize_clusters — run per-cluster LLM summarization

All subcommands require administrator permissions.
Registered via register_cluster_commands(debug_cmd) where debug_cmd is the
!debug group created in debug_commands.py.
"""
import asyncio
import json
from utils.logging_utils import get_logger

logger = get_logger('commands.cluster')

_I = "ℹ️ "


def register_cluster_commands(debug_cmd):
    """Add cluster subcommands to the existing !debug command group."""

    @debug_cmd.command(name='backfill')
    async def debug_backfill(ctx, *, flags=""):
        """Embed messages lacking embeddings using contextual text, then re-link topics."""
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
                f"({failed} failed) in {elapsed:.1f}s.")

            # Re-link all topics (active + archived)
            from utils.summary_store import get_channel_summary
            from utils.topic_store import link_topic_to_messages
            raw, _ = await asyncio.to_thread(get_channel_summary, channel_id)
            if not raw:
                await ctx.send(f"{_I}No summary — skipping topic re-link.")
                return
            data = json.loads(raw)
            all_topics = (data.get("active_topics", []) +
                          data.get("archived_topics", []))
            relinked = 0
            for topic in all_topics:
                try:
                    await asyncio.to_thread(
                        link_topic_to_messages, topic["id"], channel_id)
                    relinked += 1
                except Exception as e:
                    logger.warning(f"Re-link failed {topic['id']}: {e}")
            await ctx.send(f"{_I}Re-linked {relinked} topics. Backfill complete.")
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

    @debug_cmd.command(name='clusters')
    async def debug_clusters(ctx):
        """Run UMAP + HDBSCAN clustering and show diagnostic report."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        await ctx.send(f"{_I}Running cluster analysis for #{ctx.channel.name}...")
        try:
            from utils.cluster_store import (
                run_clustering, get_cluster_stats, format_cluster_report)
            from config import (
                CLUSTER_MIN_CLUSTER_SIZE, CLUSTER_MIN_SAMPLES,
                UMAP_N_NEIGHBORS, UMAP_N_COMPONENTS)
            stats = await asyncio.to_thread(run_clustering, channel_id)
            if stats is None:
                await ctx.send(
                    f"{_I}Not enough embeddings to cluster. "
                    f"Run `!debug backfill` first.")
                return
            rows = await asyncio.to_thread(get_cluster_stats, channel_id)
            params = {"mcs": CLUSTER_MIN_CLUSTER_SIZE, "ms": CLUSTER_MIN_SAMPLES,
                      "umap_n": UMAP_N_NEIGHBORS, "umap_d": UMAP_N_COMPONENTS}
            report = format_cluster_report(ctx.channel.name, stats, rows, params)
            from utils.summary_display import send_paginated
            await send_paginated(ctx, report.split("\n"))
        except Exception as e:
            await ctx.send(f"{_I}Cluster analysis failed: {e}")
            logger.error(f"Cluster error ch:{channel_id}: {e}")

    @debug_cmd.command(name='summarize_clusters')
    async def debug_summarize_clusters(ctx):
        """Run per-cluster LLM summarization and display results."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        try:
            from utils.cluster_store import get_clusters_for_channel
            from utils.cluster_summarizer import summarize_cluster
            clusters = await asyncio.to_thread(
                get_clusters_for_channel, channel_id)
            if not clusters:
                await ctx.send(
                    f"{_I}No clusters found for #{ctx.channel.name}. "
                    f"Run `!debug clusters` first.")
                return
            total = len(clusters)
            await ctx.send(
                f"{_I}**Cluster Summarization** (#{ctx.channel.name})\n"
                f"Processing {total} clusters...")
            from ai_providers import get_provider
            from config import SUMMARIZER_PROVIDER
            provider = get_provider(SUMMARIZER_PROVIDER)
            processed = failed = 0
            result_lines = []
            for i, cluster in enumerate(clusters):
                result = await summarize_cluster(
                    cluster["id"], channel_id, provider)
                if result:
                    processed += 1
                    result_lines.append(
                        f"Cluster {i} ({cluster['message_count']} msgs): "
                        f"\"{result.get('label','?')}\" — {result.get('status','?')}")
                else:
                    failed += 1
                    result_lines.append(
                        f"Cluster {i} ({cluster['message_count']} msgs): FAILED")
                if (i + 1) % 5 == 0:
                    await ctx.send(f"{_I}Progress: {i+1}/{total} clusters...")
            result_lines += ["", f"Processed: {processed} clusters, {failed} failures"]
            from utils.summary_display import send_paginated
            await send_paginated(ctx, result_lines)
        except Exception as e:
            await ctx.send(f"{_I}Summarize clusters failed: {e}")
            logger.error(f"summarize_clusters error ch:{channel_id}: {e}")
