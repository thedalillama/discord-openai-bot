# commands/history_commands.py
# Version 2.0.1
"""
History management command for the Discord bot.

CHANGES v2.0.1: Make manual reload run full clean pass (SOW v2.14.0)
- CHANGED: _reload_history() now calls _clean_history() after loading
- REMOVED: Partial filter (user-side bot commands only) that left noise
- RESULT: Manual !history reload produces same clean result as startup reload

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REPLACED: !history, !cleanhistory, !loadhistory with single unified !history command
- ADDED: !history clean subcommand (replaces !cleanhistory)
- ADDED: !history reload subcommand (replaces !loadhistory)
- ADDED: !history <count> subcommand for explicit count display
- ADDED: Usage hint appended to no-arg output for consistency with other commands
- ADDED: Invalid subcommand error response
- MAINTAINED: All existing logic from cleanhistory and loadhistory exactly

Usage:
  !history              - Display recent history (default 25) (admin only)
  !history <count>      - Display N most recent messages (admin only)
  !history clean        - Remove commands/artifacts from history (admin only)
  !history reload       - Reload history from Discord (admin only)
"""
from discord.ext import commands
from utils.history import (
    load_channel_history, is_bot_command, is_history_output,
    channel_history, loaded_history_channels,
    channel_system_prompts, set_system_prompt
)
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger

logger = get_logger('commands.history')

def register_history_commands(bot):
    """Register history management command with the bot"""

    @bot.command(name='history')
    @commands.has_permissions(administrator=True)
    async def history_cmd(ctx, arg=None):
        """
        Manage conversation history for this channel.

        Usage:
          !history              - Display recent history (default 25)
          !history <count>      - Display N most recent messages
          !history clean        - Remove commands/artifacts from history
          !history reload       - Reload history from Discord

        Args:
            arg: None for default display, count, 'clean', or 'reload'
        """
        channel_id = ctx.channel.id

        # --- Branch on arg ---
        if arg is None:
            await _show_history(ctx, channel_id, count=None)
            return

        arg_lower = arg.strip().lower()

        if arg_lower == 'clean':
            await _clean_history(ctx, channel_id)
            return

        if arg_lower == 'reload':
            await _reload_history(ctx, channel_id)
            return

        if arg.strip().isdigit():
            await _show_history(ctx, channel_id, count=int(arg.strip()))
            return

        # --- Unknown subcommand ---
        await ctx.send(f"Unknown history command: **{arg}**. Usage: !history [count|clean|reload]")
        logger.warning(f"Unknown history subcommand: {arg} in #{ctx.channel.name}")


    async def _show_history(ctx, channel_id, count):
        """Display recent conversation history"""
        logger.info(f"History display requested for #{ctx.channel.name} by {ctx.author.display_name} (count: {count})")

        if channel_id not in channel_history or not channel_history[channel_id]:
            logger.debug(f"No conversation history available for channel {channel_id}")
            return

        logger.debug(f"Total messages in history: {len(channel_history[channel_id])}")

        # Filter the history to remove unwanted messages
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
            if msg["role"] == "system" and not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"):
                continue
            filtered_history.append(msg)

        if not filtered_history:
            logger.debug(f"No conversation history available after filtering for channel {channel_id}")
            return

        # Determine count
        if count is None:
            count = min(len(filtered_history), 25)
        else:
            count = min(count, len(filtered_history), 50)

        total_messages = len(filtered_history)
        start_index = max(0, total_messages - count)
        history = filtered_history[start_index:total_messages]

        await ctx.send(f"**Conversation History** - Showing {len(history)} of {total_messages} messages")

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
                    content = content.replace("SYSTEM_PROMPT_UPDATE:", "Set prompt:").strip()
                else:
                    prefix = "System"
            else:
                prefix = "User"

            entry = f"**{message_number}.** {HISTORY_LINE_PREFIX}{prefix}: {content}\n\n"

            if len(history_text) + len(entry) > 1900:
                await ctx.send(history_text)
                history_text = entry
            else:
                history_text += entry

        if history_text:
            await ctx.send(history_text)

        # Usage hint for consistency with other commands
        await ctx.send("Usage: !history [count|clean|reload]")
        logger.info(f"Displayed {len(history)} history messages for #{ctx.channel.name}")


    async def _clean_history(ctx, channel_id):
        """Remove commands and artifacts from history"""
        logger.info(f"History cleanup requested for #{ctx.channel.name} by {ctx.author.display_name}")

        if channel_id not in channel_history or not channel_history[channel_id]:
            logger.debug(f"No conversation history available for channel {channel_id}")
            return

        before_count = len(channel_history[channel_id])

        channel_history[channel_id] = [
            msg for msg in channel_history[channel_id]
            if (
                not (msg["role"] == "user" and is_bot_command(msg["content"])) and
                not (msg["role"] == "assistant" and is_history_output(msg["content"])) and
                not (msg["role"] == "system" and not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"))
            )
        ]

        after_count = len(channel_history[channel_id])
        removed = before_count - after_count

        await ctx.send(f"Cleaned history: removed {removed} command and history output messages, {after_count} messages remaining.")
        logger.info(f"Cleaned {removed} messages from #{ctx.channel.name} history")


    async def _reload_history(ctx, channel_id):
        """Reload history from Discord"""
        logger.info(f"Manual history reload requested for #{ctx.channel.name} by {ctx.author.display_name}")

        # Remove from loaded channels to force a reload
        if channel_id in loaded_history_channels:
            del loaded_history_channels[channel_id]

        # Clear existing history
        channel_history[channel_id] = []

        # Save current system prompt before clearing
        current_prompt = None
        if channel_id in channel_system_prompts:
            current_prompt = channel_system_prompts[channel_id]
            logger.debug(f"Saved system prompt before reloading: {current_prompt[:50]}...")

        # Load history from Discord
        await load_channel_history(ctx.channel, is_automatic=False)

        # Set timestamp after loading
        import datetime
        loaded_history_channels[channel_id] = datetime.datetime.now()

        # Run full cleanup pass (same as automatic reload and !history clean)
        # This ensures manual reload produces the same clean result as startup
        await _clean_history(ctx, channel_id)

        # Restore custom prompt if it wasn't found in history
        if current_prompt and channel_id not in channel_system_prompts:
            logger.debug(f"Restoring saved system prompt after reload: {current_prompt[:50]}...")
            set_system_prompt(channel_id, current_prompt)

        message_count = len(channel_history[channel_id])
        await ctx.send(f"Loaded {message_count} messages from channel history.")
        logger.info(f"Successfully reloaded {message_count} messages for #{ctx.channel.name}")

    return {"history": history_cmd}
