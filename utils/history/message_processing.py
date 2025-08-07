"""
Message processing and filtering for Discord bot history.
"""
from config import HISTORY_LINE_PREFIX
from utils.logging_utils import get_logger
from .storage import channel_history
from .prompts import get_system_prompt

logger = get_logger('history.message_processing')

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
        logger.debug(f"Not filtering 'System prompt updated for' message")
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

def should_skip_message_from_history(message, is_bot_message=False):
    """
    Determine if a message should be skipped when loading history
    
    Args:
        message: Discord message object
        is_bot_message: Whether this is from the bot
        
    Returns:
        tuple: (should_skip, reason) - reason is for logging
    """
    content = message.content
    
    # Skip bot commands (except setprompt which we handle specially)
    if content.startswith('!') and not content.startswith('!setprompt'):
        return True, "bot command"
    
    # Skip bot messages that look like history command outputs
    if is_bot_message and is_history_output(content):
        return True, "history output"
    
    # Skip messages with attachments
    if message.attachments:
        return True, "has attachments"
    
    return False, None

def create_user_message(user_name, content, message_count):
    """
    Create a properly formatted user message for history
    
    Args:
        user_name: Display name of the user
        content: Message content
        message_count: Current message count for fallback naming
        
    Returns:
        dict: Formatted message for API
    """
    # Clean the username to match API requirements (letters, numbers, underscores, hyphens only)
    clean_name = ''.join(c for c in user_name if c.isalnum() or c in '_-')
    
    # If the name is empty after cleaning or doesn't change, use a default
    if not clean_name or clean_name != user_name:
        return {
            "role": "user", 
            "name": f"user_{message_count}",
            "content": f"{user_name}: {content}"
        }
    else:
        return {
            "role": "user", 
            "name": clean_name,
            "content": f"{user_name}: {content}"
        }

def create_assistant_message(content):
    """
    Create a properly formatted assistant message for history
    
    Args:
        content: Message content
        
    Returns:
        dict: Formatted message for API
    """
    return {
        "role": "assistant",
        "content": content
    }

def create_system_update_message(prompt_text, timestamp=None):
    """
    Create a system prompt update message
    
    Args:
        prompt_text: The new system prompt
        timestamp: Optional timestamp, uses current time if None
        
    Returns:
        dict: Formatted system update message
    """
    import datetime
    if timestamp is None:
        timestamp = datetime.datetime.now().isoformat()
    
    return {
        "role": "system",
        "content": f"SYSTEM_PROMPT_UPDATE: {prompt_text}",
        "timestamp": timestamp
    }

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
    
    logger.debug(f"prepare_messages_for_api for channel {channel_id}")
    logger.debug(f"Starting with system prompt: {messages[0]['content'][:50]}...")
    
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
        
        logger.debug(f"Added {len(messages)-1} messages from history")
        logger.debug(f"Filtered out {filtered_count} system prompt update and history output messages")
    else:
        logger.debug(f"No history found for channel {channel_id}")
    
    return messages

def extract_system_prompt_updates(messages):
    """
    Extract system prompt updates from message history
    
    Args:
        messages: List of message dicts
        
    Returns:
        list: List of system prompt update messages, sorted by timestamp if available
    """
    system_updates = [
        msg for msg in messages 
        if msg["role"] == "system" and msg["content"].startswith("SYSTEM_PROMPT_UPDATE:")
    ]
    
    # Sort by timestamp if available
    if system_updates and all("timestamp" in update for update in system_updates):
        system_updates.sort(key=lambda x: x.get("timestamp", ""))
        logger.debug(f"Sorted {len(system_updates)} system updates by timestamp")
    
    return system_updates
