# commands/summary_commands.py
# Version 2.3.0
"""
!summary command group for channel summary management.

CHANGES v2.3.0: Cluster pipeline result display + clear clusters on !summary clear
- MODIFIED: summary_create result handler displays cluster-v5 pipeline stats
  (cluster_count, noise_count, messages_processed) for new pipeline; retains
  v4.x display for backwards compatibility on rollback
- MODIFIED: summary_clear also calls clear_channel_clusters() to wipe cluster
  data alongside the channel summary

CHANGES v2.2.0: ℹ️/⚙️ prefix tagging for noise filtering
- ALL ctx.send() output prefixed with ℹ️ for automatic filtering

CHANGES v2.1.0: Pagination + raw minutes + full view
CHANGES v2.0.0: Restructured as command group
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)

Usage:
  !summary         Overview, topics, decisions, actions, questions
  !summary full    All sections including facts and archived topics
  !summary raw     Secretary's natural language minutes (cold start only)
  !summary create  Run summarization (admin only)
  !summary clear   Delete stored summary and clusters (admin only)
"""
import json
from utils.logging_utils import get_logger

logger = get_logger('commands.summary')

_I = "ℹ️ "


def register_summary_commands(bot):

    @bot.group(name='summary', invoke_without_command=True)
    async def summary_cmd(ctx):
        """Show the current channel summary."""
        summary = await _load_summary(ctx)
        if summary is None:
            return
        from utils.summary_display import format_summary, send_paginated
        await ctx.send(f"{_I}**Summary for #{ctx.channel.name}**")
        await send_paginated(ctx, format_summary(summary, full=False))

    @summary_cmd.command(name='full')
    async def summary_full(ctx):
        """Show all summary sections including facts and archived."""
        summary = await _load_summary(ctx)
        if summary is None:
            return
        from utils.summary_display import format_summary, send_paginated
        await ctx.send(f"{_I}**Full Summary for #{ctx.channel.name}**")
        await send_paginated(ctx, format_summary(summary, full=True))

    @summary_cmd.command(name='raw')
    async def summary_raw(ctx):
        """Show the Secretary's natural language minutes."""
        summary = await _load_summary(ctx)
        if summary is None:
            return
        from utils.summary_display import send_paginated
        minutes = summary.get("meta", {}).get("minutes_text", "")
        if not minutes:
            await ctx.send(
                f"{_I}No raw minutes for #{ctx.channel.name}. "
                f"Raw minutes stored on cold start only "
                f"(`!summary clear` then `!summary create`).")
            return
        await ctx.send(f"{_I}**Raw Minutes for #{ctx.channel.name}**")
        await send_paginated(ctx, minutes.split("\n"))

    @summary_cmd.command(name='create')
    async def summary_create(ctx):
        """Run summarization for this channel (admin only)."""
        channel_name = ctx.channel.name
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions to run summarization.")
            return
        async with ctx.typing():
            try:
                from utils.summarizer import summarize_channel
                result = await summarize_channel(ctx.channel.id)
                if result.get("error"):
                    await ctx.send(f"{_I}Summarization failed: {str(result['error'])[:1800]}")
                    return
                msgs = result["messages_processed"]
                if msgs == 0:
                    await ctx.send(f"{_I}No messages to summarize for #{channel_name}.")
                    return
                # cluster-v5 pipeline result
                if "cluster_count" in result:
                    overview_mark = "✅" if result.get("overview_generated") else "⚠️ failed"
                    lines = [
                        f"**Summary created for #{channel_name}**",
                        f"Pipeline: cluster-v5",
                        f"Clusters: {result['cluster_count']} "
                        f"({result['noise_count']} noise messages)",
                        f"Messages processed: {msgs}",
                        f"{overview_mark} Overview generated",
                    ]
                else:
                    # v4.x pipeline result (rollback path)
                    tokens = result.get("token_count", 0)
                    v = result.get("verification", {})
                    mm = v.get("mismatches", 0)
                    sf = v.get("source_checks_failed", 0)
                    lines = [f"**Summary updated for #{channel_name}**",
                             f"Messages processed: {msgs}",
                             f"Summary token count: {tokens}"]
                    if mm: lines.append(f"⚠️ Hash mismatches: {mm}")
                    if sf: lines.append(f"⚠️ Source verification failures: {sf}")
                    if not mm and not sf: lines.append("✅ Verification passed")
                await ctx.send(f"{_I}" + "\n".join(lines))
            except Exception as e:
                logger.error(f"Error in !summary create: {e}")
                await ctx.send(f"{_I}Error running summarization: {str(e)[:1800]}")

    @summary_cmd.command(name='clear')
    async def summary_clear(ctx):
        """Delete the stored summary and clusters (admin only)."""
        channel_name = ctx.channel.name
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions to clear the summary.")
            return
        try:
            import asyncio
            from utils.summary_store import delete_channel_summary
            from utils.cluster_store import clear_channel_clusters
            deleted = delete_channel_summary(ctx.channel.id)
            await asyncio.to_thread(clear_channel_clusters, ctx.channel.id)
            if deleted:
                await ctx.send(f"{_I}Summary and clusters cleared for #{channel_name}.")
            else:
                await ctx.send(f"{_I}No summary found for #{channel_name}. Clusters cleared.")
        except Exception as e:
            logger.error(f"Error in !summary clear: {e}")
            await ctx.send(f"{_I}Error: {str(e)[:1800]}")


async def _load_summary(ctx):
    """Load and parse summary for the channel."""
    try:
        from utils.summary_store import get_channel_summary
        summary_json, _ = get_channel_summary(ctx.channel.id)
        if not summary_json:
            await ctx.send(
                f"{_I}No summary available for #{ctx.channel.name}. "
                f"Run `!summary create` to generate one.")
            return None
        return json.loads(summary_json)
    except Exception as e:
        logger.error(f"Error loading summary: {e}")
        await ctx.send(f"{_I}Error retrieving summary: {str(e)[:1800]}")
        return None
