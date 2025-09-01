"""
History management commands for the Discord bot.
"""
from discord.ext import commands
from utils.history import (
    load_channel_history, is_bot_command, is_history_output,
    channel_history, loaded_history_channels,
    channel_system_prompts, set_system_prompt
)
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger

# Get logger for command execution
logger = get_logger('commands.history')

def register_history_commands(bot):
    """Register history management commands with the bot"""
    
    @bot.command(name='loadhistory')
    @commands.has_permissions(administrator=True)
    async def load_history_cmd(ctx):
        """
        Manually load message history for the current channel.
        Usage: !loadhistory
        """
        channel_id = ctx.channel.id
        
        logger.info(f"Manual history load requested for #{ctx.channel.name} by {ctx.author.display_name}")
        
        # Remove from loaded channels dictionary to force a reload
        if channel_id in loaded_history_channels:
            del loaded_history_channels[channel_id]
        
        # Clear existing history for this channel
        channel_history[channel_id] = []
        
        # Store current system prompt if it exists before clearing
        current_prompt = None
        if channel_id in channel_system_prompts:
            current_prompt = channel_system_prompts[channel_id]
            logger.debug(f"Saved current system prompt before reloading: {current_prompt[:50]}...")
        
        # Load the history (without timestamp filtering)
        await load_channel_history(ctx.channel, is_automatic=False)
        
        # Set the timestamp AFTER loading to mark the cutoff point
        import datetime
        loaded_history_channels[channel_id] = datetime.datetime.now()
        
        # Clean up the history to remove any bot commands
        channel_history[channel_id] = [
            msg for msg in channel_history[channel_id] 
            if not (msg["role"] == "user" and is_bot_command(msg["content"]))
        ]
        
        # If we had a custom prompt before reloading and didn't find one in history,
        # restore it to ensure continuity
        if current_prompt and channel_id not in channel_system_prompts:
            logger.debug(f"Restoring saved system prompt after reload: {current_prompt[:50]}...")
            set_system_prompt(channel_id, current_prompt)
        
        message_count = len(channel_history[channel_id])
        await ctx.send(f"Loaded {message_count} messages from channel history.")
        logger.info(f"Successfully loaded {message_count} messages for #{ctx.channel.name}")

    @bot.command(name='cleanhistory')
    @commands.has_permissions(administrator=True)
    async def clean_history(ctx):
        """
        Clean up the history by removing bot commands and history outputs.
        Usage: !cleanhistory
        """
        channel_id = ctx.channel.id
        
        logger.info(f"History cleanup requested for #{ctx.channel.name} by {ctx.author.display_name}")
        
        if channel_id not in channel_history or not channel_history[channel_id]:
            logger.debug(f"No conversation history available for channel {channel_id}")
            return
        
        before_count = len(channel_history[channel_id])
        
        # Filter out messages that are bot commands, history outputs, or system messages
        channel_history[channel_id] = [
            msg for msg in channel_history[channel_id] 
            if (
                not (msg["role"] == "user" and is_bot_command(msg["content"])) and
                not (msg["role"] == "assistant" and is_history_output(msg["content"])) and
                not (msg["role"] == "system" and not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"))
            )
        ]
        
        after_count = len(channel_history[channel_id])
        removed = before_count - after_count
        
        await ctx.send(f"Cleaned history: removed {removed} command and history output messages, {after_count} messages remaining.")
        logger.info(f"Cleaned {removed} messages from #{ctx.channel.name} history")

    @bot.command(name='history')
    @commands.has_permissions(administrator=True)
    async def show_history(ctx, count: int = None):
        """
        Display recent conversation history for the current channel.
        Usage: !history [count]
        Example: !history 10
        
        Args:
            count: Number of recent messages to show (default: all)
        """
        channel_id = ctx.channel.id
        
        logger.info(f"History display requested for #{ctx.channel.name} by {ctx.author.display_name} (count: {count})")
        
        if channel_id not in channel_history or not channel_history[channel_id]:
            logger.debug(f"No conversation history available for channel {channel_id}")
            return
        
        # Log total messages for debugging
        logger.debug(f"Total messages in history: {len(channel_history[channel_id])}")
        for i, msg in enumerate(channel_history[channel_id][:5]):  # Log first 5 for debugging
            logger.debug(f"{i+1}. {msg['role']}: {msg['content'][:50]}...")
        
        # Filter the history to remove unwanted messages
        filtered_history = []
        for msg in channel_history[channel_id]:
            # Skip command messages
            if msg["role"] == "user" and (
                ("!history" in msg["content"].lower()) or
                ("!cleanhistory" in msg["content"].lower()) or
                ("!loadhistory" in msg["content"].lower())
            ):
                continue
                
            # Skip empty bot messages or messages with just whitespace
            if msg["role"] == "assistant" and (not msg["content"].strip()):
                continue
            
            # Skip history output messages from the bot
            if msg["role"] == "assistant" and is_history_output(msg["content"]):
                continue
                
            # Skip system messages that aren't prompt updates
            if msg["role"] == "system" and not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"):
                continue
                
            # Include all other messages
            filtered_history.append(msg)
        
        # If filtered history is empty, just return without a message
        if not filtered_history:
            logger.debug(f"No conversation history available after filtering for channel {channel_id}")
            return
        
        # If count is not specified, show all messages (up to a reasonable limit)
        if count is None:
            count = min(len(filtered_history), 25)  # Reasonable default
        else:
            # Limit the count to avoid too long messages
            count = min(count, len(filtered_history), 50)
        
        # Get the slice of history to display
        total_messages = len(filtered_history)
        start_index = max(0, total_messages - count)
        history = filtered_history[start_index:total_messages]
        
        # Create a header message
        await ctx.send(f"**Conversation History** - Showing {len(history)} of {total_messages} messages")
        
        # Create formatted messages for the history
        history_text = ""
        for i, msg in enumerate(history):
            role = msg["role"]
            content = msg["content"]
            message_number = start_index + i + 1
            
            # Format based on role
            if role == "assistant":
                prefix = "Bot"
            elif role == "system":
                # For system messages, format differently
                if content.startswith("SYSTEM_PROMPT_UPDATE:"):
                    prefix = "System"
                    content = content.replace("SYSTEM_PROMPT_UPDATE:", "Set prompt:").strip()
                else:
                    prefix = "System"
            else:
                prefix = "User"
            
            # Add to the history text with a nice format - use our special prefix
            entry = f"**{message_number}.** {HISTORY_LINE_PREFIX}{prefix}: {content}\n\n"
            
            # If adding this entry would make the message too long, send what we have and start a new message
            if len(history_text) + len(entry) > 1900:  # Discord has a 2000 char limit, leave some buffer
                await ctx.send(history_text)
                history_text = entry
            else:
                history_text += entry
        
        # Send any remaining history text
        if history_text:
            await ctx.send(history_text)
        
        logger.info(f"Displayed {len(history)} history messages for #{ctx.channel.name}")
    
    # Return the commands for reference if needed
    return {
        "loadhistory": load_history_cmd,
        "cleanhistory": clean_history,
        "history": show_history
    }
