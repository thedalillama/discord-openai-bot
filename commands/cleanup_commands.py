# commands/cleanup_commands.py
# Version 1.0.0
"""
Temporary cleanup command to remove pre-prefix bot noise from Discord.

CREATED v1.0.0: One-time cleanup for pre-prefix bot output
- Scans channel history for !command messages
- Deletes the command AND all bot messages immediately following it
- Preserves actual conversation responses (bot replies to non-commands)
- Admin only, requires confirmation

Usage:
  !cleanup scan    - Preview what would be deleted (admin only)
  !cleanup run     - Delete the messages (admin only)
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('commands.cleanup')

_I = "ℹ️ "


def register_cleanup_commands(bot):

    @bot.group(name='cleanup', invoke_without_command=True)
    async def cleanup_cmd(ctx):
        """Preview or run cleanup of pre-prefix bot noise."""
        await ctx.send(
            f"{_I}Usage:\n"
            f"`!cleanup scan` — preview what would be deleted\n"
            f"`!cleanup run` — delete the messages"
        )

    @cleanup_cmd.command(name='scan')
    async def cleanup_scan(ctx):
        """Preview what would be deleted."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions.")
            return

        await ctx.send(f"{_I}Scanning #{ctx.channel.name}...")

        async with ctx.typing():
            to_delete, stats = await _find_deletable(ctx.channel, bot.user.id)

        await ctx.send(
            f"{_I}**Cleanup scan for #{ctx.channel.name}**\n"
            f"Commands found: {stats['commands']} (kept — already filtered)\n"
            f"Bot responses to delete: {stats['bot_responses']}\n"
            f"Total messages to delete: {stats['total']}\n"
            f"Messages to keep: {stats['kept']}\n\n"
            f"Run `!cleanup run` to delete these messages."
        )

    @cleanup_cmd.command(name='run')
    async def cleanup_run(ctx):
        """Delete pre-prefix bot noise messages."""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need admin permissions.")
            return

        await ctx.send(f"{_I}Scanning #{ctx.channel.name}...")

        async with ctx.typing():
            to_delete, stats = await _find_deletable(ctx.channel, bot.user.id)

        if not to_delete:
            await ctx.send(f"{_I}Nothing to clean up in #{ctx.channel.name}.")
            return

        await ctx.send(
            f"{_I}Deleting {stats['total']} messages "
            f"({stats['commands']} commands + "
            f"{stats['bot_responses']} bot responses)..."
        )

        deleted = 0
        errors = 0
        for msg in to_delete:
            try:
                await msg.delete()
                deleted += 1
                # Rate limit: Discord allows 5 deletes/sec
                if deleted % 5 == 0:
                    await asyncio.sleep(1.1)
            except Exception as e:
                errors += 1
                logger.error(f"Failed to delete message {msg.id}: {e}")

        await ctx.send(
            f"{_I}**Cleanup complete for #{ctx.channel.name}**\n"
            f"Deleted: {deleted}\n"
            f"Errors: {errors}\n\n"
            f"Rebuild the database: stop bot, delete "
            f"`data/messages.db*`, restart bot."
        )


async def _find_deletable(channel, bot_user_id):
    """Scan channel history and identify messages to delete.

    Pattern: find !commands, mark them + all immediately following
    bot messages for deletion. Stop when hitting a non-bot message.

    Also marks any bot message starting with ℹ️ or ⚙️ (prefixed output).

    Returns (list_of_messages, stats_dict).
    """
    messages = []
    async for msg in channel.history(limit=10000, oldest_first=True):
        messages.append(msg)

    to_delete = []
    kept = 0
    commands_found = 0
    bot_responses = 0
    in_command_sequence = False

    for msg in messages:
        is_bot = msg.author.id == bot_user_id

        # User message starting with ! — track sequence but DON'T delete
        # (bot lacks Manage Messages permission for user messages,
        # and !commands are already filtered from summarizer input)
        if not is_bot and msg.content.startswith('!'):
            commands_found += 1
            in_command_sequence = True
            continue

        # Bot message immediately after a command — delete it
        if is_bot and in_command_sequence:
            to_delete.append(msg)
            bot_responses += 1
            continue

        # Bot message with prefix tag — always delete
        if is_bot and (msg.content.startswith("ℹ️") or
                       msg.content.startswith("⚙️")):
            to_delete.append(msg)
            bot_responses += 1
            in_command_sequence = False
            continue

        # Non-bot message that's not a command — end the sequence
        if not is_bot:
            in_command_sequence = False
            kept += 1
            continue

        # Bot message NOT following a command — keep it
        # (this is an actual conversation response)
        if is_bot and not in_command_sequence:
            kept += 1
            continue

    stats = {
        "commands": commands_found,
        "bot_responses": bot_responses,
        "total": len(to_delete),
        "kept": kept,
    }
    logger.info(
        f"Cleanup scan: {stats['total']} to delete, "
        f"{stats['kept']} to keep"
    )
    return to_delete, stats
