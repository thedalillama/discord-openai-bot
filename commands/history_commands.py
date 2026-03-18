# commands/history_commands.py
# Version 2.1.0
"""
History management commands for the Discord bot.

CHANGES v2.1.0: ℹ️ prefix tagging for noise filtering
- All display/status output prefixed with ℹ️

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CREATED v1.0.0: Initial implementation

Usage:
  !history [count]   - Show recent conversation history
  !history clean     - Remove commands and artifacts from history
  !history reload    - Reload history from Discord
"""
from config import HISTORY_LINE_PREFIX
from utils.history import channel_history, loaded_history_channels
from utils.history.message_processing import (
    is_bot_command, is_history_output
)
from utils.logging_utils import get_logger

logger = get_logger('commands.history')

_I = "ℹ️ "


def register_history_commands(bot):

    @bot.command(name='history')
    async def history_cmd(ctx, *, arg=None):
        """Manage conversation history for this channel."""
        channel_id = ctx.channel.id

        if arg is None:
            await _show_history(ctx, channel_id, None)
            return

        arg = arg.strip().lower()
        if arg == 'clean':
            await _clean_history(ctx, channel_id)
            return
        elif arg == 'reload':
            await _reload_history(ctx, channel_id)
            return

        try:
            count = int(arg)
            await _show_history(ctx, channel_id, count)
        except ValueError:
            await ctx.send(f"{_I}Unknown history command: **{arg}**\n"
                           f"Usage: !history [count|clean|reload]")

    async def _show_history(ctx, channel_id, count):
        """Display recent conversation history."""
        if channel_id not in channel_history or not channel_history[channel_id]:
            await ctx.send(f"{_I}No conversation history available.")
            return

        filtered_history = []
        for msg in channel_history[channel_id]:
            if msg["role"] == "user" and (
                ("!history" in msg["content"].lower()) or
                ("!cleanhistory" in msg["content"].lower()) or
                ("!loadhistory" in msg["content"].lower())
            ):
                continue
            if msg["role"] == "assistant" and not msg["content"].strip():
                continue
            if msg["role"] == "assistant" and is_history_output(msg["content"]):
                continue
            if msg["role"] == "system" and not msg["content"].startswith(
                    "SYSTEM_PROMPT_UPDATE:"):
                continue
            filtered_history.append(msg)

        if not filtered_history:
            await ctx.send(f"{_I}No conversation history available.")
            return

        if count is None:
            count = min(len(filtered_history), 25)
        else:
            count = min(count, len(filtered_history), 50)

        total_messages = len(filtered_history)
        start_index = max(0, total_messages - count)
        history = filtered_history[start_index:total_messages]

        await ctx.send(
            f"{_I}**Conversation History** — Showing {len(history)} "
            f"of {total_messages} messages")

        history_text = ""
        for i, msg in enumerate(history):
            role = msg["role"]
            content = msg["content"]
            message_number = start_index + i + 1

            if role == "assistant":
                prefix = "Bot"
            elif role == "system":
                if content.startswith("SYSTEM_PROMPT_UPDATE:"):
                    prefix = "System"
                    content = content.replace(
                        "SYSTEM_PROMPT_UPDATE:", "Set prompt:").strip()
                else:
                    prefix = "System"
            else:
                prefix = "User"

            entry = (f"**{message_number}."
                     f"** {HISTORY_LINE_PREFIX}{prefix}: {content}\n\n")

            if len(history_text) + len(entry) > 1900:
                await ctx.send(f"{_I}{history_text}")
                history_text = entry
            else:
                history_text += entry

        if history_text:
            await ctx.send(f"{_I}{history_text}")

        await ctx.send(f"{_I}Usage: !history [count|clean|reload]")

    async def _clean_history(ctx, channel_id):
        """Remove commands and artifacts from history."""
        if channel_id not in channel_history or not channel_history[channel_id]:
            await ctx.send(f"{_I}No conversation history available.")
            return

        before_count = len(channel_history[channel_id])

        channel_history[channel_id] = [
            msg for msg in channel_history[channel_id]
            if (
                not (msg["role"] == "user" and
                     is_bot_command(msg["content"])) and
                not (msg["role"] == "assistant" and
                     is_history_output(msg["content"])) and
                not (msg["role"] == "system" and
                     not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"))
            )
        ]

        after_count = len(channel_history[channel_id])
        removed = before_count - after_count

        await ctx.send(
            f"{_I}Cleaned history: removed {removed} messages, "
            f"{after_count} remaining.")

    async def _reload_history(ctx, channel_id):
        """Reload history from Discord."""
        from utils.history import load_channel_history
        try:
            if channel_id in loaded_history_channels:
                del loaded_history_channels[channel_id]
            async with ctx.typing():
                await load_channel_history(ctx.channel, is_automatic=False)
            loaded_history_channels[channel_id] = True
            count = len(channel_history.get(channel_id, []))
            await ctx.send(f"{_I}History reloaded: {count} messages loaded.")
        except Exception as e:
            logger.error(f"Error reloading history: {e}")
            await ctx.send(f"{_I}Error reloading history: {str(e)[:1800]}")

    return {"history": history_cmd}
