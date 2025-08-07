"""
Auto-respond related commands for the Discord bot.
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
    async def toggle_channel_auto(ctx):
        """
        Toggle auto-response for the current channel.
        Usage: !autorespond
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.info(f"Auto-respond toggle requested for #{channel_name} by {ctx.author.display_name}")
        
        if channel_id in auto_respond_channels:
            auto_respond_channels.remove(channel_id)
            await ctx.send(f"Auto-response is now **disabled** in #{channel_name}")
            logger.info(f"Auto-response disabled for #{channel_name} ({channel_id})")
        else:
            auto_respond_channels.add(channel_id)
            await ctx.send(f"Auto-response is now **enabled** in #{channel_name}")
            logger.info(f"Auto-response enabled for #{channel_name} ({channel_id})")

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
