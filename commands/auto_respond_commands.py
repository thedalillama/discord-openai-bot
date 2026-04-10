# commands/auto_respond_commands.py
# Version 2.2.0
"""
Auto-response management command for the Discord bot.

CHANGES v2.2.0: Dead code cleanup (SOW v5.10.1)
- REMOVED: DEFAULT_AUTO_RESPOND import (unused)

CHANGES v2.1.0: ℹ️/⚙️ prefix tagging for noise filtering
- Settings changes prefixed with ⚙️ (persist for replay)
- Status/error output prefixed with ℹ️ (filter everywhere)
- PRESERVED: Settings text after prefix unchanged for parser compat

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CREATED v1.0.0: Initial implementation

Usage:
  !autorespond        - Show current auto-response status (all users)
  !autorespond on     - Enable auto-response (admin only)
  !autorespond off    - Disable auto-response (admin only)
"""
from utils.logging_utils import get_logger

logger = get_logger('commands.auto_respond')

_I = "ℹ️ "
_S = "⚙️ "


def register_auto_respond_commands(bot, auto_respond_channels):

    @bot.command(name='autorespond')
    async def autorespond_cmd(ctx, setting=None):
        """Manage auto-response for this channel."""
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        if setting is None:
            current_status = "enabled" if channel_id in auto_respond_channels else "disabled"
            await ctx.send(
                f"{_I}Auto-response is currently **{current_status}** in #{channel_name}\n"
                f"Options: on, off")
            return

        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need administrator permissions to change this setting.")
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
            return

        current_enabled = channel_id in auto_respond_channels

        if enabled and not current_enabled:
            auto_respond_channels.add(channel_id)
            await ctx.send(f"{_S}Auto-response is now **enabled** in #{channel_name}")
            logger.info(f"Auto-response enabled for #{channel_name}")
        elif not enabled and current_enabled:
            auto_respond_channels.remove(channel_id)
            await ctx.send(f"{_S}Auto-response is now **disabled** in #{channel_name}")
            logger.info(f"Auto-response disabled for #{channel_name}")
        else:
            await ctx.send(f"{_I}Auto-response is already **{action}** in #{channel_name}")

    return {"autorespond": autorespond_cmd}
