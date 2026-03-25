# commands/prompt_commands.py
# Version 2.1.0
"""
System prompt management command for the Discord bot.

CHANGES v2.1.0: ℹ️/⚙️ prefix tagging for noise filtering
- Settings changes prefixed with ⚙️ (persist for replay)
- Status/error output prefixed with ℹ️ (filter everywhere)

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CREATED v1.0.0: Initial implementation

Usage:
  !prompt              - Show current system prompt (all users)
  !prompt <text>       - Set new system prompt (admin only)
  !prompt reset        - Reset to default prompt (admin only)
"""
from utils.history import (
    channel_history, channel_system_prompts, get_system_prompt,
    set_system_prompt, remove_system_prompt
)
from config import DEFAULT_SYSTEM_PROMPT
from utils.logging_utils import get_logger

logger = get_logger('commands.prompt')

_I = "ℹ️ "
_S = "⚙️ "


def register_prompt_commands(bot):

    @bot.command(name='prompt')
    async def prompt_cmd(ctx, *, arg=None):
        """Manage the system prompt for this channel."""
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        if arg is None:
            prompt = get_system_prompt(channel_id)
            await ctx.send(f"{_I}Current system prompt for #{channel_name}:\n\n**{prompt}**")
            return

        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need administrator permissions to change this setting.")
            return

        if arg.strip().lower() == 'reset':
            if channel_id not in channel_system_prompts:
                await ctx.send(f"{_I}System prompt for #{channel_name} is already the default.")
                return
            remove_system_prompt(channel_id)
            await ctx.send(f"{_S}System prompt for #{channel_name} reset to default.")
            logger.info(f"System prompt reset for #{channel_name}")
            return

        new_prompt = arg.strip()
        was_updated = set_system_prompt(channel_id, new_prompt)

        if was_updated:
            await ctx.send(
                f"{_S}System prompt updated for #{channel_name}.\nNew prompt: **{new_prompt}**")
            logger.info(f"System prompt updated for #{channel_name}")
        else:
            await ctx.send(f"{_I}System prompt unchanged (same as current setting).")

    return {"prompt": prompt_cmd}
