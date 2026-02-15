# commands/prompt_commands.py
# Version 2.0.0
"""
System prompt management command for the Discord bot.

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REPLACED: !setprompt, !getprompt, !resetprompt with single unified !prompt command
- ADDED: No-arg path shows current prompt (all users, no permission check)
- ADDED: Value arg sets prompt (admin only, manual permission check)
- ADDED: 'reset' arg resets to default (admin only, with already-at-default check)
- FIXED: Reset path now checks if already at default before acting
- PRESERVED: Exact confirmation message strings required by realtime_settings_parser

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

def register_prompt_commands(bot):
    """Register system prompt management command with the bot"""

    @bot.command(name='prompt')
    async def prompt_cmd(ctx, *, arg=None):
        """
        Manage the system prompt for this channel.

        Usage:
          !prompt              - Show current system prompt (all users)
          !prompt <text>       - Set new system prompt (🔒 admin only)
          !prompt reset        - Reset to default prompt (🔒 admin only)

        Args:
            arg: None to show status, 'reset' to reset, or new prompt text to set
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        # --- No-arg: show current prompt (all users) ---
        if arg is None:
            prompt = get_system_prompt(channel_id)
            logger.debug(f"System prompt requested for #{channel_name} by {ctx.author.display_name}")
            await ctx.send(f"Current system prompt for #{channel_name}:\n\n**{prompt}**")
            return

        # --- Write operations: admin only ---
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to change this setting.")
            logger.warning(f"Unauthorized prompt change attempt by {ctx.author.display_name} in #{channel_name}")
            return

        # --- 'reset': restore default prompt ---
        if arg.strip().lower() == 'reset':
            logger.info(f"System prompt reset requested for #{channel_name} by {ctx.author.display_name}")

            # Check if already at default
            if channel_id not in channel_system_prompts:
                await ctx.send(f"System prompt for #{channel_name} is already the default.")
                logger.debug(f"System prompt already at default for #{channel_name}")
                return

            # Remove custom prompt and record reset in history
            remove_system_prompt(channel_id)
            await ctx.send(f"System prompt for #{channel_name} reset to default.")
            logger.info(f"System prompt reset to default for #{channel_name}")
            return

        # --- Value arg: set new prompt ---
        new_prompt = arg.strip()
        logger.info(f"System prompt update requested for #{channel_name} by {ctx.author.display_name}")
        logger.debug(f"New prompt: {new_prompt}")

        was_updated = set_system_prompt(channel_id, new_prompt)

        if was_updated:
            # CRITICAL: these exact substrings are required by realtime_settings_parser.py:
            # "System prompt updated for" and "New prompt:"
            response = f"System prompt updated for #{channel_name}.\nNew prompt: **{new_prompt}**"
            await ctx.send(response)
            logger.info(f"System prompt updated for #{channel_name}")
        else:
            await ctx.send("System prompt unchanged (same as current setting).")
            logger.debug(f"System prompt unchanged for #{channel_name}")

    return {"prompt": prompt_cmd}
