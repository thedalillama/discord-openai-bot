# commands/thinking_commands.py
# Version 2.1.0
"""
Thinking display management command for the Discord bot.

CHANGES v2.1.0: Remove <think> tag logic (SOW v2.20.0)
- REMOVED: filter_thinking_tags() — dead code for DeepSeek official API
- REMOVED: import re — no longer needed
- RETAINED: get_thinking_enabled(), set_thinking_enabled() — still used by
  openai_compatible_provider.py and realtime_settings_parser.py
- NOTE: !thinking on/off now controls reasoning_content display in Discord
  and logging level for DeepSeek reasoner models

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REMOVED: @commands.has_permissions decorator — replaced with manual admin check
- REMOVED: !thinkingstatus command — no-arg !thinking now shows status (all users)
- PRESERVED: Exact confirmation message strings required by realtime_settings_parser

Usage:
  !thinking        - Show current thinking display status and options (all users)
  !thinking on     - Enable DeepSeek thinking display (admin only)
  !thinking off    - Disable DeepSeek thinking display (admin only)
"""
from utils.logging_utils import get_logger

logger = get_logger('commands.thinking')

# Per-channel thinking display preference. Default False (off).
channel_thinking_enabled = {}


def get_thinking_enabled(channel_id):
    """
    Get the thinking display setting for a channel.

    Args:
        channel_id: The Discord channel ID

    Returns:
        bool: True if thinking should be displayed, False otherwise
    """
    return channel_thinking_enabled.get(channel_id, False)


def set_thinking_enabled(channel_id, enabled):
    """
    Set the thinking display setting for a channel.

    Args:
        channel_id: The Discord channel ID
        enabled: Whether to display DeepSeek thinking

    Returns:
        bool: True if this is a change, False if same as before
    """
    current_setting = get_thinking_enabled(channel_id)
    if current_setting == enabled:
        return False

    if enabled:
        channel_thinking_enabled[channel_id] = True
    else:
        channel_thinking_enabled.pop(channel_id, None)

    return True


def register_thinking_commands(bot):
    """Register thinking display management command with the bot."""

    @bot.command(name='thinking')
    async def thinking_cmd(ctx, setting=None):
        """
        Manage DeepSeek thinking display for this channel.

        When enabled: full reasoning content shown in Discord before answer,
        logged at INFO. When disabled: answer only shown, reasoning logged
        at DEBUG only.

        Usage:
          !thinking        - Show current status and options (all users)
          !thinking on     - Enable thinking display (admin only)
          !thinking off    - Disable thinking display (admin only)
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        # No-arg: show current status (all users)
        if setting is None:
            current_setting = get_thinking_enabled(channel_id)
            status = "enabled" if current_setting else "disabled"
            logger.debug(
                f"Thinking status requested for #{channel_name} "
                f"by {ctx.author.display_name}: {status}"
            )
            await ctx.send(
                f"DeepSeek thinking display is currently **{status}** in #{channel_name}\n"
                f"Options: on, off"
            )
            return

        # Write operations: admin only
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to change this setting.")
            logger.warning(
                f"Unauthorized thinking change attempt by "
                f"{ctx.author.display_name} in #{channel_name}"
            )
            return

        setting = setting.strip().lower()
        if setting in ['on', 'enable', 'enabled', 'true', '1']:
            enabled = True
            action = "enabled"
        elif setting in ['off', 'disable', 'disabled', 'false', '0']:
            enabled = False
            action = "disabled"
        else:
            await ctx.send(f"Invalid setting: **{setting}**. Use `on` or `off`.")
            logger.warning(f"Invalid thinking setting: {setting} in #{channel_name}")
            return

        was_changed = set_thinking_enabled(channel_id, enabled)

        if was_changed:
            # CRITICAL: exact string required by realtime_settings_parser.py
            await ctx.send(f"DeepSeek thinking display **{action}** for #{channel_name}")
            logger.info(
                f"Thinking display {action} for #{channel_name} "
                f"by {ctx.author.display_name}"
            )
        else:
            await ctx.send(
                f"DeepSeek thinking display is already **{action}** in #{channel_name}"
            )
            logger.debug(f"Thinking display unchanged for #{channel_name}: {action}")

    return {"thinking": thinking_cmd}
