# commands/debug_commands.py
# Version 1.6.0
"""
Debug and maintenance commands for the Discord bot.

CHANGES v1.6.0: Fix !debug clusters pagination missing ℹ️ prefix
- FIXED: debug_clusters ctx.send(page) was missing ℹ️ — unprefixed chunks
  were embedded by raw_events.py and contaminated cluster retrieval
- REFACTOR: both debug_clusters and debug_summarize_clusters now use
  send_paginated() from summary_display.py instead of inline chunk loops

CHANGES v1.5.0: Add !debug summarize_clusters command (SOW v5.2.0)
- ADDED: !debug summarize_clusters — runs per-cluster Gemini summarization,
  sends Discord progress every 5 clusters, paginates final cluster report

CHANGES v1.4.1: Paginate !debug clusters output
- MODIFIED: debug_clusters splits report into ≤1900-char pages before
  sending; prevents Discord 2000-character message limit errors

CHANGES v1.4.0: Add !debug clusters command (SOW v5.1.0)
- ADDED: !debug clusters — runs UMAP + HDBSCAN clustering on channel
  embeddings, stores results, displays diagnostic report

CHANGES v1.3.0: Batch embedding + archived topic re-link fix
- CHANGED: debug_backfill uses embed_texts_batch() — 1600 messages now takes
  ~2 API calls instead of 1600; per-batch progress logged; elapsed time reported
- FIXED: re-link phase now includes archived_topics (was active_topics only),
  matching the behaviour of summarizer_authoring.py

CHANGES v1.2.0: Backfill embeddings command (SOW v4.0.0)
- ADDED: !debug backfill — embed all messages in channel lacking embeddings,
  then re-link all topics. Reports progress and final counts.

CHANGES v1.1.0: Show classifier drops in !debug status
- ADDED: Classifier Drops section shows items filtered by GPT-5.4 nano

CREATED v1.0.0: Consolidates cleanup + summary diagnostics
- !debug noise    — scan for bot noise (preview, no delete)
- !debug cleanup  — delete bot noise from Discord
- !debug status   — internal summary state (IDs, hashes, statuses)

All subcommands require administrator permissions.

Usage:
  !debug noise               - Preview deletable bot messages
  !debug cleanup             - Delete bot noise from Discord history
  !debug status              - Show summary internals (IDs, hashes, chains)
  !debug backfill            - Embed all messages + re-link topics
  !debug clusters            - Run UMAP+HDBSCAN clustering, show report
  !debug summarize_clusters  - Run per-cluster LLM summarization
"""
import asyncio
import json
from utils.logging_utils import get_logger

logger = get_logger('commands.debug')

_I = "ℹ️ "


def register_debug_commands(bot):

    @bot.group(name='debug', invoke_without_command=True)
    async def debug_cmd(ctx):
        await ctx.send(
            f"{_I}**Debug commands:**\n"
            f"`!debug noise` — scan for bot noise\n"
            f"`!debug cleanup` — delete bot noise\n"
            f"`!debug status` — summary internals")

    @debug_cmd.command(name='noise')
    async def debug_noise(ctx):
        """Scan for deletable bot noise (preview only)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        await ctx.send(f"{_I}Scanning #{ctx.channel.name}...")
        async with ctx.typing():
            to_delete, stats = await _find_noise(ctx.channel, bot.user.id)
        await ctx.send(
            f"{_I}**Noise scan for #{ctx.channel.name}**\n"
            f"Commands found: {stats['commands']} (kept)\n"
            f"Bot responses to delete: {stats['bot_responses']}\n"
            f"Total to delete: {stats['total']}\n"
            f"Kept: {stats['kept']}\n\n"
            f"Run `!debug cleanup` to delete.")

    @debug_cmd.command(name='cleanup')
    async def debug_cleanup(ctx):
        """Delete bot noise from Discord history."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        await ctx.send(f"{_I}Scanning #{ctx.channel.name}...")
        async with ctx.typing():
            to_delete, stats = await _find_noise(ctx.channel, bot.user.id)
        if not to_delete:
            await ctx.send(f"{_I}Nothing to clean up.")
            return
        await ctx.send(f"{_I}Deleting {stats['total']} messages...")
        deleted = errors = 0
        for msg in to_delete:
            try:
                await msg.delete()
                deleted += 1
                if deleted % 5 == 0:
                    await asyncio.sleep(1.1)
            except Exception as e:
                errors += 1
                logger.error(f"Delete failed {msg.id}: {e}")
        await ctx.send(
            f"{_I}**Cleanup complete:** {deleted} deleted, "
            f"{errors} errors.\n"
            f"Rebuild DB: stop bot, `rm data/messages.db*`, restart.")

    @debug_cmd.command(name='status')
    async def debug_status(ctx):
        """Show internal summary state."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        try:
            from utils.summary_store import get_channel_summary
            raw, _ = get_channel_summary(ctx.channel.id)
            if not raw:
                await ctx.send(f"{_I}No summary for #{ctx.channel.name}.")
                return
            summary = json.loads(raw)
#            logger.info(f'Raw Summary: {summary}')
        except Exception as e:
            await ctx.send(f"{_I}Error loading summary: {e}")
            return

        meta = summary.get("meta", {})
        mr = meta.get("message_range", {})
        lines = [
            f"**Summary Debug for #{ctx.channel.name}**", "",
            f"Tokens: {summary.get('summary_token_count',0)} | "
            f"Messages: {mr.get('count',0)} | Model: {meta.get('model','?')}", ""]

        def _section(title, items, fmt):
            if items:
                lines.append(f"**{title}**")
                lines.extend(fmt(i) for i in items)
                lines.append("")

        _section("Decisions", summary.get("decisions", []), lambda d: (
            f"  {'✅' if d.get('status')=='active' else '❌'} `{d['id']}` "
            f"[{d.get('status')}] hash={d.get('text_hash','?')}"
            f"{' (supersedes '+d['supersedes_id']+')' if d.get('supersedes_id') else ''}"
            f"\n     → {d.get('decision','?')}"))
        _section("Action Items", summary.get("action_items", []), lambda a: (
            f"  {'📋' if a.get('status')=='open' else '✅'} `{a['id']}` "
            f"[{a.get('status')}] hash={a.get('text_hash','?')}"
            f"\n     → {a.get('task','?')} (owner: {a.get('owner','?')})"))
        _section("Key Facts", summary.get("key_facts", []), lambda f: (
            f"  {'📌' if f.get('status')=='active' else '🗄️'} `{f['id']}` "
            f"[{f.get('status')}] hash={f.get('text_hash','?')}"
            f"\n     → {f.get('fact','?')}"))
        _section("Open Questions", summary.get("open_questions", []), lambda q: (
            f"  {'❓' if q.get('status')=='open' else '✅'} `{q['id']}` "
            f"[{q.get('status')}]\n     → {q.get('question','?')}"))
        _section("Topics", summary.get("active_topics", []), lambda t: (
            f"  {'📂' if t.get('status')=='active' else '🗄️'} `{t['id']}` "
            f"[{t.get('status')}] {t.get('title','?')}"))

        parts = summary.get("participants", [])
        if parts:
            lines.append("**Participants:** " +
                         ", ".join(p.get("display_name", p["id"]) for p in parts))
            lines.append("")

        v = meta.get("verification", {})
        if v:
            lines.append(f"**Verification:** {v.get('hashes_verified',0)} verified, "
                         f"{v.get('mismatches',0)} mismatches")
            lines.append("")

        drops = meta.get("classifier_drops", [])
        if drops:
            lines.append(f"**Classifier Drops ({len(drops)})**")
            lines.extend(f"  🗑️ `{d.get('id','?')}` [{d.get('op','?')}] "
                         f"{d.get('text','?')[:60]}" for d in drops)
            lines.append("")

        # Send paginated
        from utils.summary_display import send_paginated
        await send_paginated(ctx, lines)

    @debug_cmd.command(name='backfill')
    async def debug_backfill(ctx):
        """Embed all messages lacking embeddings (batch), then re-link all topics."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        await ctx.send(f"{_I}Starting embedding backfill for #{ctx.channel.name}...")
        try:
            import time
            from utils.embedding_store import (
                get_messages_without_embeddings, embed_texts_batch,
                store_message_embedding, link_topic_to_messages)

            # Phase 1: batch embed missing messages
            pending = await asyncio.to_thread(
                get_messages_without_embeddings, channel_id, 2000)
            await ctx.send(f"{_I}Found {len(pending)} messages to embed...")
            t0 = time.monotonic()
            embedded = failed = 0
            if pending:
                ids = [mid for mid, _ in pending]
                texts = [content for _, content in pending]
                BATCH = 1000
                for batch_start in range(0, len(texts), BATCH):
                    batch_ids = ids[batch_start:batch_start + BATCH]
                    batch_texts = texts[batch_start:batch_start + BATCH]
                    results = await asyncio.to_thread(
                        embed_texts_batch, batch_texts, BATCH)
                    result_map = {idx: vec for idx, vec in results}
                    for i, mid in enumerate(batch_ids):
                        if i in result_map:
                            await asyncio.to_thread(
                                store_message_embedding, mid, result_map[i])
                            embedded += 1
                        else:
                            failed += 1
                    batch_end = min(batch_start + BATCH, len(texts))
                    logger.info(
                        f"Backfill batch {batch_start}–{batch_end - 1}: "
                        f"{len(results)} embedded, "
                        f"{len(batch_texts) - len(results)} failed")
            elapsed = time.monotonic() - t0
            await ctx.send(
                f"{_I}Embedded {embedded}/{len(pending)} "
                f"({failed} failed) in {elapsed:.1f}s.")

            # Phase 2: re-link all topics (active + archived)
            from utils.summary_store import get_channel_summary
            raw, _ = await asyncio.to_thread(get_channel_summary, channel_id)
            if not raw:
                await ctx.send(f"{_I}No summary — run `!summary create` first.")
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
            logger.error(f"Backfill error for ch:{channel_id}: {e}")

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

            clusters = await asyncio.to_thread(get_clusters_for_channel, channel_id)
            if not clusters:
                await ctx.send(
                    f"{_I}No clusters found for #{ctx.channel.name}. "
                    f"Run `!debug clusters` first.")
                return

            total = len(clusters)
            await ctx.send(
                f"{_I}**Cluster Summarization** (channel: #{ctx.channel.name})\n"
                f"Processing {total} clusters...")

            # Get the provider used for summarization
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
                    label = result.get("label", "?")
                    status = result.get("status", "?")
                    result_lines.append(
                        f"Cluster {i} ({cluster['message_count']} msgs): "
                        f"\"{label}\" — {status}")
                else:
                    failed += 1
                    result_lines.append(
                        f"Cluster {i} ({cluster['message_count']} msgs): FAILED")

                # Progress update every 5 clusters
                if (i + 1) % 5 == 0:
                    await ctx.send(
                        f"{_I}Progress: {i + 1}/{total} clusters processed...")

            result_lines.append("")
            result_lines.append(
                f"Processed: {processed} clusters, {failed} failures")

            from utils.summary_display import send_paginated
            await send_paginated(ctx, result_lines)

        except Exception as e:
            await ctx.send(f"{_I}Summarize clusters failed: {e}")
            logger.error(f"summarize_clusters error ch:{channel_id}: {e}")


async def _find_noise(channel, bot_user_id):
    """Scan channel for deletable bot noise messages."""
    messages = []
    async for msg in channel.history(limit=10000, oldest_first=True):
        messages.append(msg)
    to_delete = []
    kept = commands_found = bot_responses = 0
    in_command_sequence = False
    for msg in messages:
        is_bot = msg.author.id == bot_user_id
        if not is_bot and msg.content.startswith('!'):
            commands_found += 1
            in_command_sequence = True
            continue
        if is_bot and in_command_sequence:
            to_delete.append(msg)
            bot_responses += 1
            continue
        if is_bot and (msg.content.startswith("ℹ️") or
                       msg.content.startswith("⚙️")):
            to_delete.append(msg)
            bot_responses += 1
            in_command_sequence = False
            continue
        if not is_bot:
            in_command_sequence = False
            kept += 1
            continue
        if is_bot and not in_command_sequence:
            kept += 1
            continue
    stats = {
        "commands": commands_found, "bot_responses": bot_responses,
        "total": len(to_delete), "kept": kept,
    }
    return to_delete, stats
