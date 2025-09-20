# commands/auto_respond_commands.py
# Version 1.1.0
"""
Auto-respond related commands for the Discord bot.

CHANGES v1.1.0: Enhanced !autorespond command behavior
- CHANGED: !autorespond with no parameters now shows current status (instead of toggling)
- ADDED: !autorespond on/off for explicit control
- MAINTAINED: Same confirmation message format for settings recovery compatibility
- IMPROVED: More explicit and safer command behavior
"""
from discord.ext import commands
from config import DEFAULT_AUTO_RESPOND
from utils.logging_utils import get_logger

# Get logger for auto-respond commands
logger = get_logger('commands.auto_respond')

def register_auto_respond_commands(bot, auto_respond_channels):
    """Register auto-respond related commands with the bot"""
    
    @bot.command(name='autorespond')
    @commands.has_permissions(administrator=True)
    async def autorespond_cmd(ctx, setting=None):
        """
        Control auto-response for the current channel.
        
        Usage:
          !autorespond        - Show current auto-response status
          !autorespond on     - Enable auto-response
          !autorespond off    - Disable auto-response
        
        Args:
            setting: 'on', 'off', or None to check current setting
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        # If no setting provided, show current status
        if setting is None:
            current_status = "enabled" if channel_id in auto_respond_channels else "disabled"
            await ctx.send(f"Auto-response is currently **{current_status}** in #{channel_name}")
            logger.debug(f"Auto-response status requested for #{channel_name} by {ctx.author.display_name}: {current_status}")
            return
        
        # Parse the setting
        setting = setting.lower()
        if setting in ['on', 'enable', 'enabled', 'true', '1']:
            enabled = True
            action = "enabled"
        elif setting in ['off', 'disable', 'disabled', 'false', '0']:
            enabled = False
            action = "disabled"
        else:
            await ctx.send(f"Invalid setting: **{setting}**. Use `on` or `off`.")
            logger.warning(f"Invalid auto-respond setting requested: {setting}")
            return
        
        # Apply the setting
        current_enabled = channel_id in auto_respond_channels
        
        if enabled and not current_enabled:
            # Enable auto-response
            auto_respond_channels.add(channel_id)
            await ctx.send(f"Auto-response is now **enabled** in #{channel_name}")
            logger.info(f"Auto-response enabled for #{channel_name} by {ctx.author.display_name}")
            
        elif not enabled and current_enabled:
            # Disable auto-response
            auto_respond_channels.remove(channel_id)
            await ctx.send(f"Auto-response is now **disabled** in #{channel_name}")
            logger.info(f"Auto-response disabled for #{channel_name} by {ctx.author.display_name}")
            
        else:
            # No change needed
            await ctx.send(f"Auto-response is already **{action}** in #{channel_name}")
            logger.debug(f"Auto-response setting unchanged for #{channel_name}: {action}")

    @bot.command(name='autostatus')
    async def auto_status(ctx):
        """
        Show the current auto-response status for the channel.
        Usage: !autostatus
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        status = "enabled" if channel_id in auto_respond_channels else "disabled"
        
        logger.debug(f"Auto-status requested for #{channel_name} by {ctx.author.display_name}")
        
        await ctx.send(f"Auto-response is currently **{status}** in #{channel_name}")

    @bot.command(name='autosetup')
    @commands.has_permissions(administrator=True)
    async def auto_setup(ctx):
        """
        Apply the default auto-response setting to the current channel.
        Usage: !autosetup
        """
        # Apply the default setting to this channel based on environment variable
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.info(f"Auto-setup requested for #{channel_name} by {ctx.author.display_name}")
        logger.debug(f"Default auto-respond setting: {DEFAULT_AUTO_RESPOND}")
        
        if DEFAULT_AUTO_RESPOND:
            auto_respond_channels.add(channel_id)
            await ctx.send(f"Auto-response is now **enabled** in #{channel_name} (based on default setting)")
            logger.info(f"Applied default auto-respond setting (enabled) to #{channel_name}")
        else:
            if channel_id in auto_respond_channels:
                auto_respond_channels.remove(channel_id)
            await ctx.send(f"Auto-response is now **disabled** in #{channel_name} (based on default setting)")
            logger.info(f"Applied default auto-respond setting (disabled) to #{channel_name}")

    # Return the commands for reference if needed
    return {
        "autorespond": autorespond_cmd,
        "autostatus": auto_status,
        "autosetup": auto_setup
    }
