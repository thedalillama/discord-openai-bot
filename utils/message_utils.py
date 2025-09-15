# utils/message_utils.py
# Version 1.0.0
"""
Message utility functions for Discord bot.
Handles message formatting, splitting, and Discord-specific message operations.
"""
from utils.logging_utils import get_logger

logger = get_logger('message_utils')

def split_message(text, max_length=2000):
    """
    Split a long message into chunks that fit Discord's character limit.
    
    Args:
        text (str): The text to split
        max_length (int): Maximum length per chunk (default: 2000 for Discord)
        
    Returns:
        list[str]: List of message chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    remaining_text = text
    
    logger.debug(f"Splitting message of {len(text)} characters into chunks of max {max_length}")
    
    while remaining_text:
        if len(remaining_text) <= max_length:
            chunks.append(remaining_text)
            break
        
        # Find the best place to split (prefer sentences, then words)
        split_pos = max_length
        
        # Try to split at sentence boundary
        sentence_pos = remaining_text.rfind('. ', 0, max_length)
        if sentence_pos > max_length * 0.5:  # Don't split too early
            split_pos = sentence_pos + 2
        else:
            # Try to split at word boundary
            word_pos = remaining_text.rfind(' ', 0, max_length)
            if word_pos > max_length * 0.5:  # Don't split too early
                split_pos = word_pos + 1
        
        chunks.append(remaining_text[:split_pos])
        remaining_text = remaining_text[split_pos:]
    
    logger.debug(f"Split into {len(chunks)} chunks")
    return chunks

def format_user_message_for_history(user_name, content, message_count):
    """
    Format a user message for storage in conversation history.
    Handles username cleaning for API compatibility.
    
    Args:
        user_name (str): Discord user's display name
        content (str): Message content
        message_count (int): Current message count for fallback naming
        
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

def create_history_content_for_bot_response(text_content, images_count=0):
    """
    Create content for bot response to store in history.
    Handles both text and image generation responses.
    
    Args:
        text_content (str): The text response from AI
        images_count (int): Number of images generated (default: 0)
        
    Returns:
        str: Content to store in conversation history
    """
    history_content = text_content
    if images_count > 0:
        history_content += f"\n[Generated {images_count} image(s)]"
    
    return history_content.strip() if history_content.strip() else "[Empty response]"
