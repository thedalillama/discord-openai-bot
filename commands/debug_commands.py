# commands/debug_commands.py
# Version 2.2.0
"""
Debug and maintenance commands.

CHANGES v2.2.0: !debug poison show/clean — soft-delete known-bad bot responses.
CHANGES v2.1.0: Segment/cluster status in !debug pipeline.
CREATED v1.0.0: noise, cleanup, status, pipeline, dedup commands.
"""
import asyncio
import json
from utils.logging_utils import get_logger

logger = get_logger('commands.debug')

_I = "ℹ️ "


def register_debug_commands(bot):
    """Register !debug command group. Returns the group for subcommand registration."""

    @bot.group(name='debug', invoke_without_command=True,
               help='Maintenance tools: noise cleanup, backfill, reembed, dedup (admin)')
    async def debug_cmd(ctx):
        await ctx.send(
            f"{_I}**Debug commands:**\n"
            f"`!debug noise` — scan for bot noise\n"
            f"`!debug cleanup` — delete bot noise\n"
            f"`!debug status` — summary internals\n"
            f"`!debug backfill` — embed missing messages\n"
            f"`!debug reembed` — re-embed all with context\n"
            f"`!debug segments` — segment count + sample syntheses\n"
            f"`!debug propositions` — proposition count + samples\n"
            f"`!debug pipeline` — pipeline state + unsummarized count\n"
            f"`!debug dedup` — scan for duplicate test messages\n"
            f"`!debug dedup confirm` — remove duplicates\n"
            f"`!debug poison` — show known-bad bot responses\n"
            f"`!debug poison clean` — soft-delete them (admin)")

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

        from utils.summary_display import send_paginated
        await send_paginated(ctx, lines)

    @debug_cmd.command(name='pipeline')
    async def debug_pipeline(ctx):
        """Show pipeline state for this channel (admin)."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        try:
            from utils.pipeline_state import (
                get_pipeline_state, get_unsegmented_count,
                get_session_bridge_messages)
            from utils.summary_store import get_channel_summary
            from utils.segment_store import get_segment_status_counts
            from utils.cluster_store import get_cluster_status_counts

            state = await asyncio.to_thread(get_pipeline_state, ctx.channel.id)
            unseg = await asyncio.to_thread(get_unsegmented_count, ctx.channel.id)
            bridge = await asyncio.to_thread(
                get_session_bridge_messages, ctx.channel.id)
            raw, _ = await asyncio.to_thread(get_channel_summary, ctx.channel.id)
            seg_counts = await asyncio.to_thread(
                get_segment_status_counts, ctx.channel.id)
            cl_counts = await asyncio.to_thread(
                get_cluster_status_counts, ctx.channel.id)
            summary_status = "current" if raw else "none"

            ptr = state["last_segmented_message_id"]
            last_run = state["last_pipeline_run"] or "never"
            if last_run != "never":
                last_run = last_run[:19].replace('T', ' ')

            seg_total = sum(seg_counts.values())
            seg_clustered = seg_counts.get('clustered', 0)
            cl_total = sum(cl_counts.values())
            cl_active = cl_counts.get('active', 0)
            cl_dirty = cl_counts.get('dirty', 0)
            cl_dropped = cl_counts.get('dropped', 0)

            await ctx.send(
                f"{_I}**Pipeline State #{ctx.channel.name}**\n"
                f"Last segmented message: {ptr}\n"
                f"Unsummarized messages: {unseg}\n"
                f"Last pipeline run: {last_run}\n"
                f"Summary status: {summary_status}\n"
                f"Session bridge: {len(bridge)} msgs\n"
                f"Segments: {seg_total} total ({seg_clustered} clustered)\n"
                f"Clusters: {cl_total} total ({cl_active} active, "
                f"{cl_dirty} dirty, {cl_dropped} dropped)")
        except Exception as e:
            await ctx.send(f"{_I}Error: {e}")

    @debug_cmd.command(name='poison')
    async def debug_poison(ctx, action='show'):
        """Show or soft-delete known-bad bot responses. Usage: !debug poison show|clean"""
        from utils.poison_filter import find_poison_candidates, soft_delete_messages
        if action == 'clean' and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        candidates = await asyncio.to_thread(find_poison_candidates, ctx.channel.id)
        if action == 'show':
            if not candidates:
                await ctx.send(f"{_I}No poison candidates in #{ctx.channel.name}.")
                return
            lines = [f"{_I}**{len(candidates)} poison candidates** in #{ctx.channel.name}:"]
            for mid, content, reason in candidates[:20]:
                lines.append(f"  `{mid}` [{reason}]: {content[:80].replace(chr(10),' ')}...")
            if len(candidates) > 20:
                lines.append(f"  ...and {len(candidates)-20} more")
            lines.append("\nRun `!debug poison clean` to soft-delete (admin).")
            await ctx.send("\n".join(lines))
        elif action == 'clean':
            count = await asyncio.to_thread(
                soft_delete_messages, ctx.channel.id, [c[0] for c in candidates])
            await ctx.send(f"{_I}Soft-deleted {count} poisoned messages in "
                           f"#{ctx.channel.name}. Restart to clear in-memory history.")

    return debug_cmd


async def _find_noise(channel, bot_user_id):
    """Scan channel for deletable bot noise messages."""
    to_delete, kept, commands_found, bot_responses, in_seq = [], 0, 0, 0, False
    async for msg in channel.history(limit=10000, oldest_first=True):
        bot = msg.author.id == bot_user_id
        if not bot and msg.content.startswith('!'):
            commands_found += 1; in_seq = True; continue
        if bot and in_seq:
            to_delete.append(msg); bot_responses += 1; continue
        if bot and msg.content.startswith(("ℹ️", "⚙️")):
            to_delete.append(msg); bot_responses += 1; in_seq = False; continue
        if not bot:
            in_seq = False
        kept += 1
    return to_delete, {"commands": commands_found, "bot_responses": bot_responses,
                       "total": len(to_delete), "kept": kept}
