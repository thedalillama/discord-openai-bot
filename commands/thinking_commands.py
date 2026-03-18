# commands/thinking_commands.py
# Version 2.2.0
"""
Thinking display management command for the Discord bot.

CHANGES v2.2.0: ℹ️/⚙️ prefix tagging for noise filtering
- Settings changes prefixed with ⚙️ (persist for replay)
- Status/error output prefixed with ℹ️ (filter everywhere)

CHANGES v2.1.0: Remove <think> tag logic (SOW v2.20.0)
CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)

Usage:
  !thinking        - Show current thinking display status (all users)
  !thinking on     - Enable DeepSeek thinking display (admin only)
  !thinking off    - Disable DeepSeek thinking display (admin only)
"""
from utils.logging_utils import get_logger

logger = get_logger('commands.thinking')

_I = "ℹ️ "
_S = "⚙️ "

# Per-channel thinking display preference. Default False (off).
channel_thinking_enabled = {}


def get_thinking_enabled(channel_id):
    """Get the thinking display setting for a channel."""
    return channel_thinking_enabled.get(channel_id, False)


def set_thinking_enabled(channel_id, enabled):
    """Set the thinking display setting for a channel.
    Returns True if this is a change, False if same as before."""
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
        """Manage DeepSeek thinking display for this channel."""
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        if setting is None:
            current = get_thinking_enabled(channel_id)
            status = "enabled" if current else "disabled"
            logger.debug(
                f"Thinking status requested for #{channel_name} "
                f"by {ctx.author.display_name}: {status}"
            )
            await ctx.send(
                f"{_I}DeepSeek thinking display is currently "
                f"**{status}** in #{channel_name}\n"
                f"Options: on, off"
            )
            return

        if not ctx.author.guild_permissions.administrator:
            await ctx.send(
                f"{_I}You need administrator permissions to change this setting."
            )
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
            await ctx.send(f"{_I}Invalid setting: **{setting}**. Use `on` or `off`.")
            logger.warning(f"Invalid thinking setting: {setting} in #{channel_name}")
            return

        was_changed = set_thinking_enabled(channel_id, enabled)

        if was_changed:
            # CRITICAL: exact string required by realtime_settings_parser.py
            await ctx.send(
                f"{_S}DeepSeek thinking display **{action}** for #{channel_name}"
            )
            logger.info(
                f"Thinking display {action} for #{channel_name} "
                f"by {ctx.author.display_name}"
            )
        else:
            await ctx.send(
                f"{_I}DeepSeek thinking display is already "
                f"**{action}** in #{channel_name}"
            )
            logger.debug(
                f"Thinking display unchanged for #{channel_name}: {action}"
            )

    return {"thinking": thinking_cmd}
