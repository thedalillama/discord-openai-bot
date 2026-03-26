# commands/debug_commands.py
# Version 1.2.0
"""
Debug and maintenance commands for the Discord bot.

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
  !debug noise      - Preview deletable bot messages
  !debug cleanup    - Delete bot noise from Discord history
  !debug status     - Show summary internals (IDs, hashes, chains)
  !debug backfill   - Embed all messages + re-link topics
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
        """Embed all messages lacking embeddings, then re-link all topics."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}Admin only.")
            return
        channel_id = ctx.channel.id
        await ctx.send(f"{_I}Starting embedding backfill for #{ctx.channel.name}...")
        try:
            from utils.embedding_store import (
                get_messages_without_embeddings, embed_and_store_message,
                link_topic_to_messages)
            # Phase 1: embed missing messages
            pending = await asyncio.to_thread(
                get_messages_without_embeddings, channel_id, 2000)
            await ctx.send(f"{_I}Found {len(pending)} messages to embed...")
            embedded = failed = 0
            for msg_id, content in pending:
                try:
                    await asyncio.to_thread(embed_and_store_message, msg_id, content)
                    embedded += 1
                except Exception as e:
                    failed += 1
                    logger.warning(f"Backfill embed failed {msg_id}: {e}")
            await ctx.send(f"{_I}Embedded {embedded}/{len(pending)} ({failed} failed).")
            # Phase 2: re-link topics
            from utils.summary_store import get_channel_summary
            raw, _ = await asyncio.to_thread(get_channel_summary, channel_id)
            if not raw:
                await ctx.send(f"{_I}No summary — run `!summary create` first.")
                return
            topics = json.loads(raw).get("active_topics", [])
            relinked = 0
            for topic in topics:
                try:
                    await asyncio.to_thread(link_topic_to_messages, topic["id"], channel_id)
                    relinked += 1
                except Exception as e:
                    logger.warning(f"Re-link failed {topic['id']}: {e}")
            await ctx.send(f"{_I}Re-linked {relinked} topics. Backfill complete.")
        except Exception as e:
            await ctx.send(f"{_I}Backfill failed: {e}")
            logger.error(f"Backfill error for ch:{channel_id}: {e}")


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
