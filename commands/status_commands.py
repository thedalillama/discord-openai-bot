# commands/status_commands.py
# Version 1.0.0
"""
Status command for displaying current bot configuration settings.

This module provides a comprehensive status overview showing all current
bot settings for a channel including system prompt, AI provider, auto-response,
and thinking display settings.

Key Features:
- Single command to view all channel settings
- Available to all users (no admin requirement)
- Shows full system prompt text
- Displays current vs default settings clearly
- Graceful handling of missing or default settings
"""
from discord.ext import commands
from utils.logging_utils import get_logger
from utils.history import get_system_prompt, get_ai_provider
from config import AI_PROVIDER, DEFAULT_SYSTEM_PROMPT

# Get logger for status commands
logger = get_logger('commands.status')

def register_status_commands(bot, auto_respond_channels):
    """Register status command with the bot"""
    
    @bot.command(name='status')
    async def status_cmd(ctx):
        """
        Display current bot configuration settings for this channel.
        
        Shows:
        - System prompt (full text)
        - AI provider (current setting and default)
        - Auto-response status
        - Thinking display status
        
        Usage: !status
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.debug(f"Status command requested for #{channel_name} by {ctx.author.display_name}")
        
        try:
            # Build status message
            status_lines = [f"**Bot Status for #{channel_name}**", ""]
            
            # System Prompt Status
            current_prompt = get_system_prompt(channel_id)
            if current_prompt == DEFAULT_SYSTEM_PROMPT:
                status_lines.append(f"**System Prompt:** Default")
                status_lines.append(f"```{current_prompt}```")
            else:
                status_lines.append(f"**System Prompt:** Custom")
                status_lines.append(f"```{current_prompt}```")
            
            status_lines.append("")  # Empty line for spacing
            
            # AI Provider Status
            current_provider = get_ai_provider(channel_id)
            if current_provider is None:
                status_lines.append(f"**AI Provider:** {AI_PROVIDER} (default)")
            else:
                if current_provider == AI_PROVIDER:
                    status_lines.append(f"**AI Provider:** {current_provider} (matches default)")
                else:
                    status_lines.append(f"**AI Provider:** {current_provider} (channel setting)")
                    status_lines.append(f"Default: {AI_PROVIDER}")
            
            # Auto-Response Status
            auto_respond_enabled = channel_id in auto_respond_channels
            auto_status = "enabled" if auto_respond_enabled else "disabled"
            status_lines.append(f"**Auto-Response:** {auto_status}")
            
            # Thinking Display Status
            thinking_status = _get_thinking_status(channel_id)
            status_lines.append(f"**Thinking Display:** {thinking_status}")
            
            # Combine all status lines
            status_message = "\n".join(status_lines)
            
            # Send the status message
            await ctx.send(status_message)
            
            logger.info(f"Status displayed for #{channel_name} - Prompt: {'custom' if current_prompt != DEFAULT_SYSTEM_PROMPT else 'default'}, Provider: {current_provider or AI_PROVIDER}, Auto: {auto_status}, Thinking: {thinking_status}")
            
        except Exception as e:
            logger.error(f"Error generating status for #{channel_name}: {e}")
            await ctx.send(f"Error retrieving status for #{channel_name}. Please try again.")

def _get_thinking_status(channel_id):
    """
    Get the current thinking display status for a channel.
    
    Args:
        channel_id: Discord channel ID
        
    Returns:
        str: "enabled" or "disabled"
    """
    try:
        # Import thinking commands module to check status
        from commands.thinking_commands import get_thinking_enabled
        thinking_enabled = get_thinking_enabled(channel_id)
        return "enabled" if thinking_enabled else "disabled"
        
    except ImportError:
        logger.warning("Could not import thinking commands module for status display")
        return "unavailable"
    except Exception as e:
        logger.error(f"Error getting thinking status: {e}")
        return "error"

    # Return the command for reference if needed
    return {
        "status": status_cmd
    }
