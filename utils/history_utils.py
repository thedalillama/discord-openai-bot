"""
History management utility functions for the Discord bot.
"""
from collections import defaultdict
import asyncio
import datetime
from config import INITIAL_HISTORY_LOAD, CHANNEL_LOCK_TIMEOUT, DEFAULT_SYSTEM_PROMPT, DEBUG_MODE, HISTORY_LINE_PREFIX

# Dictionary to store conversation history for each channel
channel_history = defaultdict(list)

# Dictionary to track channels where history has been loaded, with timestamps
# Format: {channel_id: first_processed_timestamp}
loaded_history_channels = {}  # Changed from a set to a dictionary

# Dictionary to store locks for each channel
channel_locks = {}

# Dictionary to store custom system prompts for each channel
# Format: {channel_id: custom_prompt}
channel_system_prompts = {}

# Dictionary to store AI providers for each channel
# Format: {channel_id: provider_name}
channel_ai_providers = {}

def is_bot_command(message_text):
    """
    Check if a message is a bot command
    
    Args:
        message_text: The message text to check
        
    Returns:
        bool: True if the message is a command, False otherwise
    """
    # Special case: if it's a setprompt command, don't filter it out
    if message_text.startswith('!setprompt'):
        return False
        
    return (message_text.startswith('!') or 
            ': !' in message_text or 
            message_text.startswith('/'))

def is_history_output(message_text):
    """
    Check if a message appears to be output from a history command
    
    Args:
        message_text: The message text to check
        
    Returns:
        bool: True if the message looks like history output, False otherwise
    """
    # Special case: don't filter out system prompt update messages
    if "System prompt updated for" in message_text:
        if DEBUG_MODE:
            print(f"[DEBUG] Not filtering 'System prompt updated for' message")
        return False
        
    # Check for common patterns in history command outputs
    is_output = (
        "**Conversation History**" in message_text or  # History command header
        HISTORY_LINE_PREFIX in message_text or         # Our special prefix for history lines
        message_text.startswith("**1.") or             # Numbered history entries
        message_text.startswith("**2.") or
        (("Loaded " in message_text) and (" messages from channel history" in message_text)) or  # loadhistory response
        "Cleaned history: removed " in message_text or  # cleanhistory response
        "Auto-response is now " in message_text or     # autorespond responses
        "Auto-response is currently " in message_text or  # autostatus response
        "Current system prompt for" in message_text or  # getprompt response
        "System prompt for" in message_text and "reset to default" in message_text or  # resetprompt response
        "AI provider for" in message_text or           # setai responses
        "Current AI provider for" in message_text      # getai responses
    )
    
    return is_output

def get_system_prompt(channel_id):
    """
    Get the system prompt for a channel, falling back to default if none is set
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str: The system prompt to use for this channel
    """
    # Return channel-specific prompt if it exists, otherwise return default
    prompt = channel_system_prompts.get(channel_id, DEFAULT_SYSTEM_PROMPT)
    if DEBUG_MODE:
        print(f"[DEBUG] get_system_prompt for channel {channel_id}: {'custom prompt' if channel_id in channel_system_prompts else 'default prompt'}")
    return prompt

def get_system_prompt(channel_id):
    """
    Get the system prompt for a channel, falling back to default if none is set
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str: The system prompt to use for this channel
    """
    # Return channel-specific prompt if it exists, otherwise return default
    prompt = channel_system_prompts.get(channel_id, DEFAULT_SYSTEM_PROMPT)
    if DEBUG_MODE:
        print(f"[DEBUG] get_system_prompt for channel {channel_id}: {'custom prompt' if channel_id in channel_system_prompts else 'default prompt'}")
    return prompt

def set_system_prompt(channel_id, new_prompt):
    """
    Set a custom system prompt for a channel and record it in history
    
    Args:
        channel_id: The Discord channel ID
        new_prompt: The new system prompt to use
        
    Returns:
        bool: True if this is a change, False if same as before
    """
    if DEBUG_MODE:
        print(f"[DEBUG] set_system_prompt called for channel {channel_id}")
        print(f"[DEBUG] new prompt: {new_prompt[:50]}...")
    
    current_prompt = get_system_prompt(channel_id)
    if current_prompt == new_prompt:
        if DEBUG_MODE:
            print(f"[DEBUG] Prompt unchanged (same as current)")
        return False
        
    # Store the prompt in the dictionary
    channel_system_prompts[channel_id] = new_prompt
    
    if DEBUG_MODE:
        print(f"[DEBUG] Updated prompt in channel_system_prompts dictionary")
        print(f"[DEBUG] channel_system_prompts now has {len(channel_system_prompts)} entries")
    
    # Also add a special entry to the channel history to record this change
    # Use "system" role which is supported by the API
    if channel_id in channel_history:
        timestamp = datetime.datetime.now().isoformat()
        channel_history[channel_id].append({
            "role": "system",
            "content": f"SYSTEM_PROMPT_UPDATE: {new_prompt}",
            "timestamp": timestamp
        })
        if DEBUG_MODE:
            print(f"[DEBUG] Added system prompt update to channel history with timestamp {timestamp}")
            print(f"[DEBUG] Channel history now has {len(channel_history[channel_id])} entries")
    else:
        if DEBUG_MODE:
            print(f"[DEBUG] Channel {channel_id} not in channel_history, skipping history update")
    
    return True

def get_ai_provider(channel_id):
    """
    Get the AI provider for a channel, returning None if no channel-specific setting
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str or None: The provider name for this channel, or None to use default
    """
    provider = channel_ai_providers.get(channel_id, None)
    if DEBUG_MODE:
        print(f"[DEBUG] get_ai_provider for channel {channel_id}: {'custom provider: ' + provider if provider else 'using default'}")
    return provider

def set_ai_provider(channel_id, provider_name):
    """
    Set a custom AI provider for a channel
    
    Args:
        channel_id: The Discord channel ID
        provider_name: The provider name (e.g., 'openai', 'anthropic')
        
    Returns:
        bool: True if this is a change, False if same as before
    """
    if DEBUG_MODE:
        print(f"[DEBUG] set_ai_provider called for channel {channel_id}")
        print(f"[DEBUG] new provider: {provider_name}")
    
    current_provider = get_ai_provider(channel_id)
    if current_provider == provider_name:
        if DEBUG_MODE:
            print(f"[DEBUG] Provider unchanged (same as current)")
        return False
        
    # Store the provider in the dictionary
    channel_ai_providers[channel_id] = provider_name
    
    if DEBUG_MODE:
        print(f"[DEBUG] Updated provider in channel_ai_providers dictionary")
        print(f"[DEBUG] channel_ai_providers now has {len(channel_ai_providers)} entries")
    
    return True

def prepare_messages_for_api(channel_id):
    """
    Prepare messages for the API by:
    1. Adding the current system prompt as the first message
    2. Including all history except special system prompt update entries
    3. Filtering out history output messages
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        list: Messages ready to send to the API
    """
    # Start with the current system prompt
    messages = [
        {"role": "system", "content": get_system_prompt(channel_id)}
    ]
    
    if DEBUG_MODE:
        print(f"[DEBUG] prepare_messages_for_api for channel {channel_id}")
        print(f"[DEBUG] Starting with system prompt: {messages[0]['content'][:50]}...")
    
    # Add all messages except system prompt updates and history outputs
    if channel_id in channel_history:
        filtered_count = 0
        for msg in channel_history[channel_id]:
            # Skip special system prompt update entries
            if (msg["role"] == "system" and 
                msg["content"].startswith("SYSTEM_PROMPT_UPDATE:")):
                filtered_count += 1
                continue
            
            # Skip history output entries (messages from the bot that look like history output)
            if (msg["role"] == "assistant" and 
                is_history_output(msg["content"])):
                filtered_count += 1
                continue
            
            # Add all other messages
            messages.append(msg)
        
        if DEBUG_MODE:
            print(f"[DEBUG] Added {len(messages)-1} messages from history")
            print(f"[DEBUG] Filtered out {filtered_count} system prompt update and history output messages")
    else:
        if DEBUG_MODE:
            print(f"[DEBUG] No history found for channel {channel_id}")
    
    return messages

async def load_channel_history(channel, is_automatic=False):
    """
    Load recent message history from a channel with proper locking
    
    Args:
        channel: The Discord channel to load history from
        is_automatic: Whether this is an automatic load (triggered by new message)
        
    Returns:
        None
    """
    channel_id = channel.id
    
    if DEBUG_MODE:
        print(f"[DEBUG] load_channel_history called for channel #{channel.name} ({channel_id})")
        print(f"[DEBUG] Is channel in loaded_history_channels? {channel_id in loaded_history_channels}")
        if is_automatic:
            print(f"[DEBUG] This is an automatic history load (will skip newest message)")
    
    # Skip if we've already loaded history for this channel
    if channel_id in loaded_history_channels:
        if DEBUG_MODE:
            print(f"[DEBUG] Channel already in loaded_history_channels, returning early")
        return
    
    # Get or create a lock for this channel
    if channel_id not in channel_locks:
        channel_locks[channel_id] = asyncio.Lock()
        if DEBUG_MODE:
            print(f"[DEBUG] Created new lock for channel #{channel.name}")
    
    try:
        if DEBUG_MODE:
            print(f"[DEBUG] Attempting to acquire lock for channel #{channel.name}")
        
        # Wait up to CHANNEL_LOCK_TIMEOUT seconds to acquire the lock
        await asyncio.wait_for(channel_locks[channel_id].acquire(), timeout=CHANNEL_LOCK_TIMEOUT)
        
        if DEBUG_MODE:
            print(f"[DEBUG] Successfully acquired lock for channel #{channel.name}")
        
        # Double check if history was loaded while we were waiting for the lock
        if channel_id in loaded_history_channels:
            if DEBUG_MODE:
                print(f"[DEBUG] Channel was added to loaded_history_channels while waiting for lock, returning early")
            channel_locks[channel_id].release()
            return
        
        try:
            print(f"Loading message history for channel #{channel.name} ({channel_id})")
            messages = []
            
            # Fetch recent messages from the channel
            if DEBUG_MODE:
                print(f"[DEBUG] Fetching up to {INITIAL_HISTORY_LOAD} messages from Discord API")
            
            # Flag to skip the first message if automatic loading
            should_skip_first = is_automatic
            
            message_count = 0
            skipped_count = 0
            
            # Track if we've found a setprompt command and its response
            found_setprompt = False
            found_setprompt_response = False
            setprompt_content = ""
            
            async for message in channel.history(limit=INITIAL_HISTORY_LOAD):
                message_count += 1
                
                if DEBUG_MODE:
                    print(f"[DEBUG] Message {message_count}: {message.content[:80]}...")
                
                # Skip the first message if automatic loading
                if should_skip_first:
                    should_skip_first = False
                    skipped_count += 1
                    if DEBUG_MODE:
                        print(f"[DEBUG] Skipping newest message to avoid duplicate during automatic loading")
                    continue
                
                # Special handling for setprompt commands and their responses
                if message.content.startswith('!setprompt '):
                    found_setprompt = True
                    # Extract the prompt from the command
                    setprompt_content = message.content[len('!setprompt '):].strip()
                    if DEBUG_MODE:
                        print(f"[DEBUG] Found !setprompt command with content: {setprompt_content}")
                    # Continue to process more messages before deciding what to do
                
                # Check for system prompt update confirmation messages
                if message.author == channel.guild.me and "System prompt updated for" in message.content:
                    found_setprompt_response = True
                    if DEBUG_MODE:
                        print(f"[DEBUG] Found system prompt update confirmation")
                    # Continue to process more messages
                
                # Skip bot commands (except we already handled !setprompt)
                if message.content.startswith('!') and not message.content.startswith('!setprompt'):
                    skipped_count += 1
                    if DEBUG_MODE:
                        print(f"[DEBUG] Skipping bot command: {message.content[:30]}...")
                    continue
                    
                # Skip bot messages that look like history command outputs
                # (but we already made an exception for system prompt messages)
                if message.author == channel.guild.me and is_history_output(message.content):
                    skipped_count += 1
                    if DEBUG_MODE:
                        print(f"[DEBUG] Skipping history output: {message.content[:30]}...")
                    continue
                    
                # Skip messages with attachments
                if message.attachments:
                    skipped_count += 1
                    if DEBUG_MODE:
                        print(f"[DEBUG] Skipping message with attachments")
                    continue
                    
                # Add to our list (in reverse, since Discord returns newest first)
                messages.insert(0, message)
            
            if DEBUG_MODE:
                print(f"[DEBUG] Fetched {message_count} messages total")
                print(f"[DEBUG] Skipped {skipped_count} messages (commands, history outputs, attachments, and first message if automatic)")
                print(f"[DEBUG] Kept {len(messages)} messages for processing")
                
            # If we found a setprompt command but not its response, add the prompt directly
            if found_setprompt and setprompt_content and not found_setprompt_response:
                if DEBUG_MODE:
                    print(f"[DEBUG] Found setprompt command without response, setting prompt directly: {setprompt_content}")
                
                # Create system prompt update entry
                timestamp = datetime.datetime.now().isoformat()
                channel_history[channel_id].append({
                    "role": "system",
                    "content": f"SYSTEM_PROMPT_UPDATE: {setprompt_content}",
                    "timestamp": timestamp
                })
                
                # Set the prompt directly
                channel_system_prompts[channel_id] = setprompt_content
                
                if DEBUG_MODE:
                    print(f"[DEBUG] Added system prompt directly: {setprompt_content}")
            
            # Process messages and add to history
            for message in messages:
                # Skip setprompt commands since we already processed them above
                if message.content.startswith('!setprompt'):
                    if DEBUG_MODE:
                        print(f"[DEBUG] Skipping already processed setprompt command")
                    continue
                    
                # Process differently based on whether it's from our bot or a user
                if message.author == channel.guild.me:
                    # If this is a system prompt updated message, convert it to a system prompt update
                    if "System prompt updated for" in message.content and "New prompt:" in message.content:
                        try:
                            # Extract the prompt from the confirmation message
                            prompt_text = message.content.split("New prompt:", 1)[1].strip()
                            # Remove any formatting (like ** for bold)
                            prompt_text = prompt_text.replace("**", "").strip()
                            
                            if DEBUG_MODE:
                                print(f"[DEBUG] Extracted prompt from update message: {prompt_text}")
                            
                            # Record as system prompt update
                            timestamp = message.created_at.isoformat() if hasattr(message, 'created_at') else datetime.datetime.now().isoformat()
                            channel_history[channel_id].append({
                                "role": "system",
                                "content": f"SYSTEM_PROMPT_UPDATE: {prompt_text}",
                                "timestamp": timestamp
                            })
                            
                            if DEBUG_MODE:
                                print(f"[DEBUG] Added system prompt update to history: {prompt_text}")
                                
                            # Skip to next message
                            continue
                        except Exception as e:
                            if DEBUG_MODE:
                                print(f"[DEBUG] Error extracting prompt from update message: {e}")
                    
                    # Regular bot message
                    channel_history[channel_id].append({
                        "role": "assistant",
                        "content": message.content
                    })
                    
                    if DEBUG_MODE and len(channel_history[channel_id]) % 10 == 0:
                        print(f"[DEBUG] Added {len(channel_history[channel_id])} messages to history so far")
                else:
                    # Process user messages
                    user_name = message.author.display_name
                    clean_name = ''.join(c for c in user_name if c.isalnum() or c in '_-')
                    
                    # If the name is empty after cleaning or doesn't change, use a default
                    if not clean_name or clean_name != user_name:
                        # Add the message with the actual username in the content but a clean name parameter
                        channel_history[channel_id].append({
                            "role": "user", 
                            "name": f"user_{len(channel_history[channel_id])}",
                            "content": f"{user_name}: {message.content}"
                        })
                    else:
                        # If the name is already clean, use it directly
                        channel_history[channel_id].append({
                            "role": "user", 
                            "name": clean_name,
                            "content": f"{user_name}: {message.content}"
                        })
                    
                    if DEBUG_MODE and len(channel_history[channel_id]) % 10 == 0:
                        print(f"[DEBUG] Added {len(channel_history[channel_id])} messages to history so far")
            
            # Perform a final cleanup to make sure no command messages slipped through
            original_length = len(channel_history[channel_id])
            channel_history[channel_id] = [
                msg for msg in channel_history[channel_id] 
                if not (msg["role"] == "user" and is_bot_command(msg["content"]) and not msg["content"].startswith('!setprompt'))
            ]
            final_length = len(channel_history[channel_id])
            
            if DEBUG_MODE:
                print(f"[DEBUG] Final cleanup: removed {original_length - final_length} command messages")
            
            # Look for system prompt update entries
            system_updates = [msg for msg in channel_history[channel_id] 
                             if msg["role"] == "system" and msg["content"].startswith("SYSTEM_PROMPT_UPDATE:")]
            
            if DEBUG_MODE:
                print(f"[DEBUG] Found {len(system_updates)} system prompt updates in history")
                for i, update in enumerate(system_updates):
                    print(f"[DEBUG]   Update {i+1}: {update['content'][:100]}...")
            
            if system_updates:
                # Sort by timestamp if available
                if all("timestamp" in update for update in system_updates):
                    system_updates.sort(key=lambda x: x.get("timestamp", ""))
                    if DEBUG_MODE:
                        print(f"[DEBUG] Sorted system updates by timestamp")
                
                # Get the most recent update
                latest_update = system_updates[-1]
                
                # Extract the prompt (remove the prefix)
                prompt_text = latest_update["content"].replace("SYSTEM_PROMPT_UPDATE:", "", 1).strip()
                
                # Restore the prompt
                channel_system_prompts[channel_id] = prompt_text
                if DEBUG_MODE:
                    print(f"[DEBUG] Restored custom system prompt: {prompt_text[:100]}...")
                print(f"Restored custom system prompt for channel #{channel.name}")
            
            print(f"Loaded {len(channel_history[channel_id])} messages for channel #{channel.name}")
        
        except Exception as e:
            print(f"Error loading channel history: {str(e)}")
            if DEBUG_MODE:
                import traceback
                print(f"[DEBUG] Detailed error traceback:")
                traceback.print_exc()
            # We don't add the channel to loaded_history_channels if loading fails
        
        finally:
            # Always release the lock, even if loading fails
            if DEBUG_MODE:
                print(f"[DEBUG] Releasing lock for channel #{channel.name}")
            channel_locks[channel_id].release()
    
    except asyncio.TimeoutError:
        print(f"Timeout waiting for lock on channel {channel_id}")
        if DEBUG_MODE:
            print(f"[DEBUG] Timeout after {CHANNEL_LOCK_TIMEOUT} seconds waiting for lock")
        # We might want to implement a retry mechanism here if needed
