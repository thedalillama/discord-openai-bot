# utils/response_handler.py
# Version 1.0.0
"""
AI response handling utilities for Discord bot.
Handles AI response processing, message splitting, image sending, and background task management.
"""
import asyncio
import io
import discord
from utils.ai_utils import generate_ai_response
from utils.message_utils import split_message, create_history_content_for_bot_response
from utils.history import channel_history
from utils.logging_utils import get_logger

logger = get_logger('response_handler')

async def handle_ai_response_task(message, channel_id, messages, provider_override=None):
    """
    Background task to handle AI response (both text and images)
    This runs in the background to avoid blocking Discord's heartbeat
    
    Args:
        message: Discord message object that triggered the response
        channel_id: Discord channel ID where response should be sent
        messages: List of messages for AI context
        provider_override: Optional provider name to override channel default
    """
    try:
        # Generate response using our abstracted function with optional provider override
        bot_response = await generate_ai_response(
            messages, 
            channel_id=channel_id,
            provider_override=provider_override
        )
        
        # Handle both old string format and new structured format
        if isinstance(bot_response, str):
            # Legacy format - just text
            text_chunks = split_message(bot_response)
            
            for chunk in text_chunks:
                await message.channel.send(chunk)
            
            # Add bot's response to the history
            channel_history[channel_id].append({
                "role": "assistant",
                "content": bot_response
            })
            
        elif isinstance(bot_response, dict):
            # New structured format
            text_content = bot_response.get("text", "")
            images = bot_response.get("images", [])
            
            # Send text response if available (split if necessary)
            if text_content.strip():
                text_chunks = split_message(text_content)
                
                for chunk in text_chunks:
                    await message.channel.send(chunk)
            
            # Send images if any were generated
            for i, image in enumerate(images):
                try:
                    # Create Discord file from image data
                    image_data = image["data"]
                    filename = f"generated_image_{i+1}.png"
                    
                    # Create a BytesIO object from the image data
                    image_buffer = io.BytesIO(image_data)
                    
                    # Create Discord file object
                    discord_file = discord.File(image_buffer, filename=filename)
                    
                    # Send the image
                    await message.channel.send(file=discord_file)
                    
                    logger.debug(f"Sent generated image: {filename}")
                    
                except Exception as e:
                    logger.error(f"Error sending generated image: {e}")
                    await message.channel.send("⚠️ I generated an image but couldn't send it.")
            
            # Add response to history (text only - don't store image data in history)
            history_content = create_history_content_for_bot_response(text_content, len(images))
            
            if history_content.strip():
                channel_history[channel_id].append({
                    "role": "assistant", 
                    "content": history_content
                })
                
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        await message.channel.send(error_msg)
        logger.error(f"Error processing AI response: {e}")

async def handle_ai_response(message, channel_id, messages, provider_override=None):
    """
    Helper function to handle AI response using background tasks
    This prevents blocking Discord's heartbeat during long API calls
    
    Args:
        message: Discord message object that triggered the response
        channel_id: Discord channel ID where response should be sent
        messages: List of messages for AI context
        provider_override: Optional provider name to override channel default
    """
    # Show typing indicator immediately
    async with message.channel.typing():
        # Create a background task for the AI response
        task = asyncio.create_task(handle_ai_response_task(message, channel_id, messages, provider_override))
        
        # Wait for the task to complete, but don't block the event loop
        try:
            await task
        except Exception as e:
            logger.error(f"Error in AI response task: {e}")
            await message.channel.send("Sorry, I encountered an error processing your request.")

async def send_text_response(channel, text_content):
    """
    Send text response to Discord channel with automatic message splitting
    
    Args:
        channel: Discord channel object
        text_content: Text content to send
        
    Returns:
        int: Number of message chunks sent
    """
    if not text_content or not text_content.strip():
        logger.debug("No text content to send")
        return 0
    
    text_chunks = split_message(text_content)
    
    for i, chunk in enumerate(text_chunks):
        await channel.send(chunk)
        logger.debug(f"Sent text chunk {i+1}/{len(text_chunks)}")
    
    return len(text_chunks)

async def send_image_response(channel, images):
    """
    Send image response(s) to Discord channel
    
    Args:
        channel: Discord channel object
        images: List of image dictionaries with 'data' and optional metadata
        
    Returns:
        int: Number of images successfully sent
    """
    sent_count = 0
    
    for i, image in enumerate(images):
        try:
            # Create Discord file from image data
            image_data = image["data"]
            filename = f"generated_image_{i+1}.png"
            
            # Create a BytesIO object from the image data
            image_buffer = io.BytesIO(image_data)
            
            # Create Discord file object
            discord_file = discord.File(image_buffer, filename=filename)
            
            # Send the image
            await channel.send(file=discord_file)
            
            logger.debug(f"Sent generated image: {filename}")
            sent_count += 1
            
        except Exception as e:
            logger.error(f"Error sending generated image {i+1}: {e}")
            await channel.send("⚠️ I generated an image but couldn't send it.")
    
    return sent_count

def add_response_to_history(channel_id, text_content, images_count=0):
    """
    Add AI response to channel conversation history
    
    Args:
        channel_id: Discord channel ID
        text_content: Text content of the response
        images_count: Number of images generated (default: 0)
        
    Returns:
        bool: True if response was added to history, False if content was empty
    """
    history_content = create_history_content_for_bot_response(text_content, images_count)
    
    if history_content.strip():
        channel_history[channel_id].append({
            "role": "assistant", 
            "content": history_content
        })
        logger.debug(f"Added AI response to history for channel {channel_id}")
        return True
    else:
        logger.debug(f"Skipped adding empty response to history for channel {channel_id}")
        return False
