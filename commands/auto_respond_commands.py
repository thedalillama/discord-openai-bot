# commands/auto_respond_commands.py
# Version 2.0.0
"""
Auto-response management command for the Discord bot.

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REMOVED: @commands.has_permissions decorator — replaced with manual admin check
- REMOVED: !autostatus command — no-arg !autorespond now shows status (all users)
- REMOVED: !autosetup command — redundant, rarely useful
- ADDED: No-arg path shows current status + options (all users)
- ADDED: Manual permission check for write operations only
- PRESERVED: Exact confirmation message strings required by realtime_settings_parser

Usage:
  !autorespond        - Show current auto-response status and options (all users)
  !autorespond on     - Enable auto-response (admin only)
  !autorespond off    - Disable auto-response (admin only)
"""
from config import DEFAULT_AUTO_RESPOND
from utils.logging_utils import get_logger

logger = get_logger('commands.auto_respond')

def register_auto_respond_commands(bot, auto_respond_channels):
    """Register auto-response management command with the bot"""

    @bot.command(name='autorespond')
    async def autorespond_cmd(ctx, setting=None):
        """
        Manage auto-response for this channel.

        Usage:
          !autorespond        - Show current status and options (all users)
          !autorespond on     - Enable auto-response (🔒 admin only)
          !autorespond off    - Disable auto-response (🔒 admin only)

        Args:
            setting: 'on', 'off', or None to show current status
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        # --- No-arg: show current status + options (all users) ---
        if setting is None:
            current_status = "enabled" if channel_id in auto_respond_channels else "disabled"
            logger.debug(f"Auto-response status requested for #{channel_name} by {ctx.author.display_name}: {current_status}")
            await ctx.send(
                f"Auto-response is currently **{current_status}** in #{channel_name}\n"
                f"Options: on, off"
            )
            return

        # --- Write operations: admin only ---
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to change this setting.")
            logger.warning(f"Unauthorized auto-respond change attempt by {ctx.author.display_name} in #{channel_name}")
            return

        # --- Parse setting ---
        setting = setting.strip().lower()
        if setting in ['on', 'enable', 'enabled', 'true', '1']:
            enabled = True
            action = "enabled"
        elif setting in ['off', 'disable', 'disabled', 'false', '0']:
            enabled = False
            action = "disabled"
        else:
            await ctx.send(f"Invalid setting: **{setting}**. Use `on` or `off`.")
            logger.warning(f"Invalid auto-respond setting requested: {setting} in #{channel_name}")
            return

        # --- Apply setting ---
        current_enabled = channel_id in auto_respond_channels

        if enabled and not current_enabled:
            auto_respond_channels.add(channel_id)
            # CRITICAL: "Auto-response is now" required by realtime_settings_parser.py
            await ctx.send(f"Auto-response is now **enabled** in #{channel_name}")
            logger.info(f"Auto-response enabled for #{channel_name} by {ctx.author.display_name}")

        elif not enabled and current_enabled:
            auto_respond_channels.remove(channel_id)
            # CRITICAL: "Auto-response is now" required by realtime_settings_parser.py
            await ctx.send(f"Auto-response is now **disabled** in #{channel_name}")
            logger.info(f"Auto-response disabled for #{channel_name} by {ctx.author.display_name}")

        else:
            await ctx.send(f"Auto-response is already **{action}** in #{channel_name}")
            logger.debug(f"Auto-response setting unchanged for #{channel_name}: {action}")

    return {"autorespond": autorespond_cmd}
