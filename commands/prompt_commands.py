"""
System prompt related commands for the Discord bot.
"""
from discord.ext import commands
from utils.history import (
    channel_history, channel_system_prompts, get_system_prompt, set_system_prompt
)
from config import DEFAULT_SYSTEM_PROMPT
from utils.logging_utils import get_logger

# Get logger for command execution
logger = get_logger('commands.prompt')

def register_prompt_commands(bot):
    """Register system prompt related commands with the bot"""
    
    @bot.command(name='setprompt')
    @commands.has_permissions(administrator=True)
    async def set_prompt_cmd(ctx, *, new_prompt):
        """
        Set a custom system prompt for the current channel.
        Usage: !setprompt [new prompt text]
        Example: !setprompt You are a helpful bot that speaks like a pirate.
        
        Args:
            new_prompt: The new system prompt to use
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.info(f"System prompt update requested for #{channel_name} by {ctx.author.display_name}")
        logger.debug(f"New prompt: {new_prompt}")
        
        # Set the new prompt
        was_updated = set_system_prompt(channel_id, new_prompt)
        
        if was_updated:
            # Send response with NO special prefix to make it more likely to be kept in history
            response = f"System prompt updated for #{channel_name}.\nNew prompt: **{new_prompt}**"
            await ctx.send(response)
            logger.info(f"System prompt updated for #{channel_name}")
        else:
            await ctx.send(f"System prompt unchanged (same as current setting).")
            logger.debug(f"System prompt unchanged for #{channel_name}")

    @bot.command(name='getprompt')
    async def get_prompt_cmd(ctx):
        """
        Show the current system prompt for this channel.
        Usage: !getprompt
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        prompt = get_system_prompt(channel_id)
        
        logger.debug(f"System prompt requested for #{channel_name} by {ctx.author.display_name}")
        
        await ctx.send(f"Current system prompt for #{channel_name}:\n\n**{prompt}**")

    @bot.command(name='resetprompt')
    @commands.has_permissions(administrator=True)
    async def reset_prompt_cmd(ctx):
        """
        Reset the system prompt for this channel to the default.
        Usage: !resetprompt
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.info(f"System prompt reset requested for #{channel_name} by {ctx.author.display_name}")
        
        # Record the current prompt for logging
        current_prompt = get_system_prompt(channel_id)
        
        # Remove the custom prompt if it exists
        if channel_id in channel_system_prompts:
            # Before removing, add an update entry to record this change
            import datetime
            timestamp = datetime.datetime.now().isoformat()
            channel_history[channel_id].append({
                "role": "system",
                "content": f"SYSTEM_PROMPT_UPDATE: {DEFAULT_SYSTEM_PROMPT}",
                "timestamp": timestamp
            })
            
            # Now remove the custom prompt
            del channel_system_prompts[channel_id]
            
            logger.debug(f"Reset system prompt from: {current_prompt[:50]}...")
            logger.debug(f"To default: {DEFAULT_SYSTEM_PROMPT[:50]}...")
            
            await ctx.send(f"System prompt for #{channel_name} reset to default.")
        else:
            await ctx.send(f"System prompt for #{channel_name} is already set to default.")
    
    # Return the commands for reference if needed
    return {
        "setprompt": set_prompt_cmd,
        "getprompt": get_prompt_cmd,
        "resetprompt": reset_prompt_cmd
    }
