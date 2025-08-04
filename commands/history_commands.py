"""
History-related commands for the Discord bot.
"""
from discord.ext import commands
from utils.history_utils import (
    load_channel_history, is_bot_command, is_history_output,
    channel_history, loaded_history_channels,
    prepare_messages_for_api, channel_system_prompts, get_system_prompt, set_system_prompt
)
from config import DEBUG_MODE, HISTORY_LINE_PREFIX, DEFAULT_SYSTEM_PROMPT

def register_history_commands(bot):
    """Register history-related commands with the bot"""
    
    @bot.command(name='loadhistory')
    @commands.has_permissions(administrator=True)
    async def load_history_cmd(ctx):
        """
        Manually load message history for the current channel.
        Usage: !loadhistory
        """
        channel_id = ctx.channel.id
        
        # Remove from loaded channels dictionary to force a reload
        if channel_id in loaded_history_channels:
            del loaded_history_channels[channel_id]
        
        # Clear existing history for this channel
        channel_history[channel_id] = []
        
        # Store current system prompt if it exists before clearing
        current_prompt = None
        if channel_id in channel_system_prompts:
            current_prompt = channel_system_prompts[channel_id]
            if DEBUG_MODE:
                print(f"[DEBUG] Saved current system prompt before reloading: {current_prompt[:50]}...")
        
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
            if DEBUG_MODE:
                print(f"[DEBUG] Restoring saved system prompt after reload: {current_prompt[:50]}...")
            
            set_system_prompt(channel_id, current_prompt)
        
        await ctx.send(f"Loaded {len(channel_history[channel_id])} messages from channel history.")

    @bot.command(name='cleanhistory')
    @commands.has_permissions(administrator=True)
    async def clean_history(ctx):
        """
        Clean up the history by removing bot commands and history outputs.
        Usage: !cleanhistory
        """
        channel_id = ctx.channel.id
        
        if channel_id not in channel_history or not channel_history[channel_id]:
            # Just log to console instead of sending a message
            print(f"No conversation history available for channel {channel_id}")
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
        
        if channel_id not in channel_history or not channel_history[channel_id]:
            # Instead of sending a message, just log to console
            print(f"No conversation history available for channel {channel_id}")
            return
        
        # Debug: Only print debug info if DEBUG_MODE is enabled
        if DEBUG_MODE:
            print("\n----- HISTORY DEBUG -----")
            print(f"Total messages in history: {len(channel_history[channel_id])}")
            for i, msg in enumerate(channel_history[channel_id]):
                print(f"{i+1}. {msg['role']}: {msg['content'][:50]}...")
            print("----- END DEBUG -----\n")
        
        # Filter the history to remove:
        # 1. Any history command outputs before showing
        # 2. Empty bot messages or messages with no actual content
        # 3. System messages except custom prompts
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
            print(f"No conversation history available after filtering for channel {channel_id}")
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
        
        # Create a single formatted message for the history
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
        
        # Set the new prompt
        was_updated = set_system_prompt(channel_id, new_prompt)
        
        if was_updated:
            # Send response with NO special prefix to make it more likely to be kept in history
            response = f"System prompt updated for #{channel_name}.\nNew prompt: **{new_prompt}**"
            await ctx.send(response)
            
            # Add a special log message for debugging
            if DEBUG_MODE:
                print(f"[DEBUG] System prompt updated to: {new_prompt}")
        else:
            await ctx.send(f"System prompt unchanged (same as current setting).")

    @bot.command(name='getprompt')
    async def get_prompt_cmd(ctx):
        """
        Show the current system prompt for this channel.
        Usage: !getprompt
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        prompt = get_system_prompt(channel_id)
        
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
            
            if DEBUG_MODE:
                print(f"[DEBUG] Reset system prompt from: {current_prompt[:50]}...")
                print(f"[DEBUG] To default: {DEFAULT_SYSTEM_PROMPT[:50]}...")
            
            await ctx.send(f"System prompt for #{channel_name} reset to default.")
        else:
            await ctx.send(f"System prompt for #{channel_name} is already set to default.")

    @bot.command(name='setai')
    @commands.has_permissions(administrator=True)
    async def set_ai_cmd(ctx, provider_name):
        """
        Set the AI provider for the current channel.
        Usage: !setai [provider]
        Example: !setai anthropic
        
        Args:
            provider_name: The AI provider to use (openai, anthropic)
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        # Validate provider name
        valid_providers = ['openai', 'anthropic']
        provider_name = provider_name.lower()
        
        if provider_name not in valid_providers:
            await ctx.send(f"Invalid AI provider: **{provider_name}**. Valid options: {', '.join(valid_providers)}")
            return
        
        # Check if this is actually a change
        from utils.history_utils import get_ai_provider, set_ai_provider
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
            return
        
        # Set the new provider
        set_ai_provider(channel_id, provider_name)
        
        # Send confirmation
        await ctx.send(f"AI provider for #{channel_name} changed from **{current_provider}** to **{provider_name}**.")
        
        if DEBUG_MODE:
            print(f"[DEBUG] AI provider for channel #{channel_name} ({channel_id}) set to: {provider_name}")

    @bot.command(name='getai')
    async def get_ai_cmd(ctx):
        """
        Show the current AI provider for this channel.
        Usage: !getai
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        from utils.history_utils import get_ai_provider
        from config import AI_PROVIDER
        
        # Get channel-specific provider
        channel_provider = get_ai_provider(channel_id)
        
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
        
        from utils.history_utils import get_ai_provider, channel_ai_providers
        from config import AI_PROVIDER
        
        # Check if there's a channel-specific setting
        if channel_id not in channel_ai_providers:
            await ctx.send(f"AI provider for #{channel_name} is already using the default (**{AI_PROVIDER}**).")
            return
        
        # Get current setting before removing
        current_provider = get_ai_provider(channel_id)
        
        # Remove the channel-specific setting
        del channel_ai_providers[channel_id]
        
        await ctx.send(f"AI provider for #{channel_name} reset from **{current_provider}** to default (**{AI_PROVIDER}**).")
        
        if DEBUG_MODE:
            print(f"[DEBUG] AI provider for channel #{channel_name} ({channel_id}) reset to default: {AI_PROVIDER}")
            
    # Return the commands if needed for further registration
    return {
        "loadhistory": load_history_cmd,
        "cleanhistory": clean_history,
        "history": show_history,
        "setprompt": set_prompt_cmd,
        "getprompt": get_prompt_cmd,
        "resetprompt": reset_prompt_cmd,
        "setai": set_ai_cmd,
        "getai": get_ai_cmd,
        "resetai": reset_ai_cmd
    }
