# commands/summary_commands.py
# Version 2.6.0
"""
!summary command group for channel summary management.

CHANGES v2.6.0: Add force flag to !summary create (SOW v7.3.0 M3)
- MODIFIED: summary_create() — accepts optional 'force' argument.
  !summary create force waits up to 30s for the pipeline lock before running.
  !summary create (no flag) fails immediately if worker holds the lock.
CHANGES v2.5.0: Remove !summary raw; fix !summary full description
CHANGES v2.4.0: !summary update — re-summarize dirty clusters only (SOW v5.4.0)
CHANGES v2.3.0: Cluster pipeline result display + clear clusters on !summary clear
CHANGES v2.2.0: ℹ️/⚙️ prefix tagging for noise filtering
CHANGES v2.1.0: Pagination + raw minutes + full view
CHANGES v2.0.0: Restructured as command group
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)

Usage:
  !summary               Overview, topics, decisions, actions, questions
  !summary full          All sections including key facts
  !summary create        Run summarization (admin only)
  !summary create force  Wait for pipeline lock, then run (admin only)
  !summary update        Re-summarize dirty clusters (admin only)
  !summary clear         Delete stored summary and clusters (admin only)
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
        """Show all summary sections including key facts."""
        summary = await _load_summary(ctx)
        if summary is None:
            return
        from utils.summary_display import format_summary, send_paginated
        await ctx.send(f"{_I}**Full Summary for #{ctx.channel.name}**")
        await send_paginated(ctx, format_summary(summary, full=True))

    @summary_cmd.command(name='create')
    async def summary_create(ctx, flag: str = None):
        """Run summarization for this channel (admin only). Add 'force' to wait for lock."""
        channel_name = ctx.channel.name
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions to run summarization.")
            return
        force = (flag == 'force')
        await ctx.send(
            f"{_I}Starting summarization for #{channel_name}. "
            f"This takes several minutes...")
        try:
            from utils.summarizer import summarize_channel

            async def _progress(msg):
                await ctx.send(f"{_I}{msg}")

            result = await summarize_channel(
                ctx.channel.id, progress_fn=_progress, force=force)
            if result.get("error"):
                await ctx.send(f"{_I}Summarization failed: {str(result['error'])[:1800]}")
                return
            msgs = result["messages_processed"]
            if msgs == 0:
                await ctx.send(f"{_I}No messages to summarize for #{channel_name}.")
                return
            overview_mark = "✅" if result.get("overview_generated") else "⚠️ failed"
            lines = [
                f"**Summary created for #{channel_name}**",
                f"Clusters: {result.get('cluster_count', '?')} "
                f"({result.get('noise_count', 0)} noise messages)",
                f"Messages processed: {msgs}",
                f"{overview_mark} Overview generated",
            ]
            await ctx.send(f"{_I}" + "\n".join(lines))
        except Exception as e:
            logger.error(f"Error in !summary create: {e}")
            await ctx.send(f"{_I}Error running summarization: {str(e)[:1800]}")

    @summary_cmd.command(name='update')
    async def summary_update(ctx):
        """Re-summarize clusters updated since last run (admin only)."""
        channel_name = ctx.channel.name
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions to run !summary update.")
            return
        await ctx.send(f"{_I}Running quick update for #{channel_name}...")
        try:
            from utils.summarizer import quick_update_channel

            async def _progress(msg):
                await ctx.send(f"{_I}{msg}")

            result = await quick_update_channel(
                ctx.channel.id, progress_fn=_progress)
            if result.get("error"):
                await ctx.send(
                    f"{_I}Update failed: {str(result['error'])[:1800]}")
                return
            updated = result["updated_count"]
            unassigned = result["unassigned_count"]
            if updated == 0:
                await ctx.send(
                    f"{_I}No updated clusters for #{channel_name}. "
                    f"({unassigned} unassigned messages not in any cluster)")
                return
            overview_mark = "✅" if result.get("overview_generated") else "⚠️ failed"
            lines = [
                f"**Quick update for #{channel_name}**",
                f"Clusters re-summarized: {updated}",
                f"{overview_mark} Overview regenerated",
            ]
            if unassigned > 0:
                lines.append(
                    f"⚠️ {unassigned} unassigned messages"
                    f" — run `!summary create` for full rebuild")
            await ctx.send(f"{_I}" + "\n".join(lines))
        except Exception as e:
            logger.error(f"Error in !summary update: {e}")
            await ctx.send(f"{_I}Error running quick update: {str(e)[:1800]}")

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
