# commands/pipeline_commands.py
# Version 1.0.0
"""
!pipeline command group for background worker control (SOW v7.3.0 M3).

Admin-only commands for testing and rollout management.

  !pipeline stop    — stop worker after current cycle
  !pipeline start   — restart stopped worker
  !pipeline run     — force one cycle on current channel now
  !pipeline status  — show worker state + pipeline stats for channel

CREATED v1.0.0: Pipeline worker control commands (SOW v7.3.0 M3)
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('commands.pipeline')

_I = "ℹ️ "


def register_pipeline_commands(bot):

    @bot.group(name='pipeline', invoke_without_command=True)
    async def pipeline_cmd(ctx):
        await ctx.send(f"{_I}Usage: `!pipeline stop|start|run|status`")

    @pipeline_cmd.command(name='stop')
    async def pipeline_stop(ctx):
        """Stop the background worker after its current cycle (admin only)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        import utils.pipeline_worker as pw
        pw._worker_stopped = True
        await ctx.send(f"{_I}Pipeline worker stopping after current cycle.")

    @pipeline_cmd.command(name='start')
    async def pipeline_start(ctx):
        """Restart a stopped background worker (admin only)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        import utils.pipeline_worker as pw
        if not pw._worker_stopped and pw._worker_task and not pw._worker_task.done():
            await ctx.send(f"{_I}Worker is already running.")
            return
        pw.start_worker()
        await ctx.send(f"{_I}Pipeline worker started.")

    @pipeline_cmd.command(name='run')
    async def pipeline_run(ctx):
        """Force one pipeline cycle on this channel immediately (admin only)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        import utils.pipeline_worker as pw
        channel_id = ctx.channel.id
        if not pw.acquire_pipeline_lock(channel_id, "manual"):
            holder = pw.get_pipeline_lock_holder(channel_id)
            await ctx.send(f"{_I}Channel locked by `{holder}`. Try again shortly.")
            return
        await ctx.send(f"{_I}Running pipeline cycle for #{ctx.channel.name}...")
        try:
            from ai_providers import get_provider
            from config import SUMMARIZER_PROVIDER
            from utils.incremental_segmenter import incremental_segment
            provider = get_provider(SUMMARIZER_PROVIDER)
            created = await incremental_segment(channel_id, provider)
            await pw.embed_segments(channel_id)
            await pw.decompose_propositions(channel_id)
            await pw.index_fts(channel_id)
            await ctx.send(
                f"{_I}Cycle complete — {created} new segments created.")
        except Exception as e:
            logger.error(f"!pipeline run error ch:{channel_id}: {e}")
            await ctx.send(f"{_I}Error: {str(e)[:400]}")
        finally:
            pw.release_pipeline_lock(channel_id)

    @pipeline_cmd.command(name='status')
    async def pipeline_status(ctx):
        """Show worker state and pipeline stats for this channel (admin only)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        import utils.pipeline_worker as pw
        from utils.pipeline_state import get_pipeline_state, get_unsegmented_count
        channel_id = ctx.channel.id
        if pw._worker_stopped:
            worker_state = "stopped"
        elif pw._worker_task and not pw._worker_task.done():
            worker_state = "running"
        else:
            worker_state = "not started"
        lock_holder = pw.get_pipeline_lock_holder(channel_id)
        state = await asyncio.to_thread(get_pipeline_state, channel_id)
        unseg = await asyncio.to_thread(get_unsegmented_count, channel_id)
        last_run = state.get("last_pipeline_run") or "never"
        lines = [
            f"**Pipeline Status #{ctx.channel.name}**",
            f"Worker: {worker_state}",
            f"Lock: {lock_holder or 'free'}",
            f"Unsegmented messages: {unseg}",
            f"Last pipeline run: {last_run}",
        ]
        await ctx.send(f"{_I}" + "\n".join(lines))
