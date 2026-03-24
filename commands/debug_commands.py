# commands/debug_commands.py
# Version 1.1.0
"""
Debug and maintenance commands for the Discord bot.

CHANGES v1.1.0: Show classifier drops in !debug status
- ADDED: Classifier Drops section shows items filtered by GPT-5.4 nano

CREATED v1.0.0: Consolidates cleanup + summary diagnostics
- !debug noise    — scan for bot noise (preview, no delete)
- !debug cleanup  — delete bot noise from Discord
- !debug status   — internal summary state (IDs, hashes, statuses)

All subcommands require administrator permissions.

Usage:
  !debug noise     - Preview deletable bot messages
  !debug cleanup   - Delete bot noise from Discord history
  !debug status    - Show summary internals (IDs, hashes, chains)
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
        except Exception as e:
            await ctx.send(f"{_I}Error loading summary: {e}")
            return

        lines = [f"**Summary Debug for #{ctx.channel.name}**", ""]
        tc = summary.get("summary_token_count", 0)
        mr = summary.get("meta", {}).get("message_range", {})
        lines.append(f"Tokens: {tc} | Messages: {mr.get('count', 0)}")
        lines.append(f"Model: {summary.get('meta', {}).get('model', '?')}")
        lines.append("")

        # Decisions
        decisions = summary.get("decisions", [])
        if decisions:
            lines.append("**Decisions**")
            for d in decisions:
                icon = "✅" if d.get("status") == "active" else "❌"
                sup = ""
                if d.get("supersedes_id"):
                    sup = f" (supersedes {d['supersedes_id']})"
                lines.append(
                    f"  {icon} `{d['id']}` [{d.get('status')}] "
                    f"hash={d.get('text_hash', '?')}{sup}\n"
                    f"     → {d.get('decision', '?')}")
            lines.append("")

        # Action Items
        actions = summary.get("action_items", [])
        if actions:
            lines.append("**Action Items**")
            for a in actions:
                icon = "📋" if a.get("status") == "open" else "✅"
                lines.append(
                    f"  {icon} `{a['id']}` [{a.get('status')}] "
                    f"hash={a.get('text_hash', '?')}\n"
                    f"     → {a.get('task', '?')} "
                    f"(owner: {a.get('owner', '?')})")
            lines.append("")

        # Key Facts
        facts = summary.get("key_facts", [])
        if facts:
            lines.append("**Key Facts**")
            for f in facts:
                icon = "📌" if f.get("status") == "active" else "🗄️"
                lines.append(
                    f"  {icon} `{f['id']}` [{f.get('status')}] "
                    f"hash={f.get('text_hash', '?')}\n"
                    f"     → {f.get('fact', '?')}")
            lines.append("")

        # Open Questions
        questions = summary.get("open_questions", [])
        if questions:
            lines.append("**Open Questions**")
            for q in questions:
                icon = "❓" if q.get("status") == "open" else "✅"
                lines.append(
                    f"  {icon} `{q['id']}` [{q.get('status')}]\n"
                    f"     → {q.get('question', '?')}")
            lines.append("")

        # Active Topics
        topics = summary.get("active_topics", [])
        if topics:
            lines.append("**Topics**")
            for t in topics:
                icon = "📂" if t.get("status") == "active" else "🗄️"
                lines.append(
                    f"  {icon} `{t['id']}` [{t.get('status')}] "
                    f"{t.get('title', '?')}")
            lines.append("")

        # Participants
        parts = summary.get("participants", [])
        if parts:
            names = ", ".join(p.get("display_name", p["id"]) for p in parts)
            lines.append(f"**Participants:** {names}")
            lines.append("")

        # Verification
        v = summary.get("meta", {}).get("verification", {})
        if v:
            lines.append(
                f"**Verification:** {v.get('hashes_verified', 0)} verified, "
                f"{v.get('mismatches', 0)} mismatches, "
                f"{v.get('source_checks_passed', 0)} src pass, "
                f"{v.get('source_checks_failed', 0)} src fail")
            lines.append("")

        # Classifier drops
        drops = summary.get("meta", {}).get("classifier_drops", [])
        if drops:
            lines.append(f"**Classifier Drops ({len(drops)})**")
            for d in drops:
                lines.append(
                    f"  🗑️ `{d.get('id', '?')}` [{d.get('op', '?')}] "
                    f"{d.get('text', '?')[:60]}")
            lines.append("")

        # Send paginated
        from utils.summary_display import send_paginated
        await send_paginated(ctx, lines)


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
