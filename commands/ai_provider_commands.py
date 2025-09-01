"""
AI provider related commands for the Discord bot.
"""
from discord.ext import commands
from utils.history import (
    get_ai_provider, set_ai_provider, channel_ai_providers
)
from utils.logging_utils import get_logger

# Get logger for command execution
logger = get_logger('commands.ai_provider')

def register_ai_provider_commands(bot):
    """Register AI provider related commands with the bot"""
    
    @bot.command(name='setai')
    @commands.has_permissions(administrator=True)
    async def set_ai_cmd(ctx, provider_name):
        """
        Set the AI provider for the current channel.
        Usage: !setai [provider]
        Example: !setai deepseek
        
        Args:
            provider_name: The AI provider to use (openai, anthropic, deepseek)
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.info(f"AI provider change requested for #{channel_name} by {ctx.author.display_name}")
        logger.debug(f"Requested provider: {provider_name}")
        
        # Validate provider name
        valid_providers = ['openai', 'anthropic', 'deepseek']
        provider_name = provider_name.lower()
        
        if provider_name not in valid_providers:
            await ctx.send(f"Invalid AI provider: **{provider_name}**. Valid options: {', '.join(valid_providers)}")
            logger.warning(f"Invalid AI provider requested: {provider_name}")
            return
        
        # Check if this is actually a change
        current_provider = get_ai_provider(channel_id)
        
        # If no current provider set, show what the default would be
        if current_provider is None:
            from config import AI_PROVIDER
            current_provider = AI_PROVIDER
            provider_source = "default"
        else:
            provider_source = "channel setting"
        
        if current_provider == provider_name:
            await ctx.send(f"AI provider for #{channel_name} is already set to **{provider_name}** (from {provider_source}).")
            logger.debug(f"AI provider unchanged: {provider_name}")
            return
        
        # Set the new provider
        set_ai_provider(channel_id, provider_name)
        
        # Send confirmation
        await ctx.send(f"AI provider for #{channel_name} changed from **{current_provider}** to **{provider_name}**.")
        logger.info(f"AI provider for #{channel_name} changed from {current_provider} to {provider_name}")

    @bot.command(name='getai')
    async def get_ai_cmd(ctx):
        """
        Show the current AI provider for this channel.
        Usage: !getai
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        from config import AI_PROVIDER
        
        # Get channel-specific provider
        channel_provider = get_ai_provider(channel_id)
        
        logger.debug(f"AI provider requested for #{channel_name} by {ctx.author.display_name}")
        
        if channel_provider is None:
            # Using default from config
            await ctx.send(f"AI provider for #{channel_name}: **{AI_PROVIDER}** (default setting)")
        else:
            # Using channel-specific setting
            await ctx.send(f"AI provider for #{channel_name}: **{channel_provider}** (channel setting)")

    @bot.command(name='resetai')
    @commands.has_permissions(administrator=True)
    async def reset_ai_cmd(ctx):
        """
        Reset the AI provider for this channel to use the default.
        Usage: !resetai
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        from config import AI_PROVIDER
        
        logger.info(f"AI provider reset requested for #{channel_name} by {ctx.author.display_name}")
        
        # Check if there's a channel-specific setting
        if channel_id not in channel_ai_providers:
            await ctx.send(f"AI provider for #{channel_name} is already using the default (**{AI_PROVIDER}**).")
            logger.debug(f"AI provider already using default for #{channel_name}")
            return
        
        # Get current setting before removing
        current_provider = get_ai_provider(channel_id)
        
        # Remove the channel-specific setting
        del channel_ai_providers[channel_id]
        
        await ctx.send(f"AI provider for #{channel_name} reset from **{current_provider}** to default (**{AI_PROVIDER}**).")
        logger.info(f"AI provider for #{channel_name} reset from {current_provider} to default")
    
    # Return the commands for reference if needed
    return {
        "setai": set_ai_cmd,
        "getai": get_ai_cmd,
        "resetai": reset_ai_cmd
    }
