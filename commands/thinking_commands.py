"""
Thinking display commands for DeepSeek reasoning control.
"""
from discord.ext import commands
from utils.logging_utils import get_logger
import re

# Get logger for command execution
logger = get_logger('commands.thinking')

# Dictionary to store thinking display preference per channel
# Default to False (hide thinking) for cleaner output
channel_thinking_enabled = {}

def get_thinking_enabled(channel_id):
    """
    Get the thinking display setting for a channel
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        bool: True if thinking should be displayed, False otherwise
    """
    return channel_thinking_enabled.get(channel_id, False)

def set_thinking_enabled(channel_id, enabled):
    """
    Set the thinking display setting for a channel
    
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
        # Remove from dict when disabled (saves memory and defaults to False)
        channel_thinking_enabled.pop(channel_id, None)
    
    return True

def filter_thinking_tags(text, show_thinking=True):
    """
    Filter DeepSeek thinking tags from response text
    
    Args:
        text: The response text that may contain <think> tags
        show_thinking: Whether to keep or remove the thinking sections
        
    Returns:
        str: Filtered text
    """
    if show_thinking:
        return text
    
    # Pattern to match <think>...</think> including nested content and newlines
    # Use non-greedy matching with DOTALL to handle multiline thinking blocks
    think_pattern = r'<think>.*?</think>'
    
    # Remove thinking sections (case insensitive, multiline, dotall)
    filtered_text = re.sub(think_pattern, '', text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    
    # Clean up extra whitespace that might be left behind
    filtered_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', filtered_text)
    filtered_text = filtered_text.strip()
    
    # If the filtered text is empty or just whitespace, return a fallback message
    if not filtered_text.strip():
        return "[Response contained only thinking content - no final answer provided]"
    
    return filtered_text

def register_thinking_commands(bot):
    """Register thinking display commands with the bot"""
    
    @bot.command(name='thinking')
    @commands.has_permissions(administrator=True)
    async def thinking_toggle(ctx, setting=None):
        """
        Control DeepSeek thinking display for the current channel.
        Usage: !thinking [on|off]
        Examples: 
          !thinking on     - Show DeepSeek reasoning
          !thinking off    - Hide DeepSeek reasoning  
          !thinking        - Show current setting
        
        Args:
            setting: 'on', 'off', or None to check current setting
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        # If no setting provided, show current status
        if setting is None:
            current_setting = get_thinking_enabled(channel_id)
            status = "enabled" if current_setting else "disabled"
            await ctx.send(f"DeepSeek thinking display is currently **{status}** in #{channel_name}")
            logger.debug(f"Thinking status requested for #{channel_name} by {ctx.author.display_name}: {status}")
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
            logger.warning(f"Invalid thinking setting requested: {setting}")
            return
        
        # Set the new setting
        was_changed = set_thinking_enabled(channel_id, enabled)
        
        if was_changed:
            await ctx.send(f"DeepSeek thinking display **{action}** for #{channel_name}")
            logger.info(f"Thinking display {action} for #{channel_name} by {ctx.author.display_name}")
        else:
            await ctx.send(f"DeepSeek thinking display is already **{action}** in #{channel_name}")
            logger.debug(f"Thinking display setting unchanged for #{channel_name}: {action}")

    @bot.command(name='thinkingstatus')
    async def thinking_status(ctx):
        """
        Show the current DeepSeek thinking display status for this channel.
        Usage: !thinkingstatus
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        current_setting = get_thinking_enabled(channel_id)
        status = "enabled" if current_setting else "disabled"
        
        await ctx.send(f"DeepSeek thinking display is currently **{status}** in #{channel_name}")
        logger.debug(f"Thinking status requested for #{channel_name} by {ctx.author.display_name}: {status}")

    # Return the commands for reference if needed
    return {
        "thinking": thinking_toggle,
        "thinkingstatus": thinking_status
    }
