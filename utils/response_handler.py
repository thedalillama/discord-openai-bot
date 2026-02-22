# utils/response_handler.py
# Version 1.1.1
"""
AI response handling utilities for Discord bot.

CHANGES v1.1.1: User-friendly API error messages (SOW v2.19.0)
- MODIFIED: handle_ai_response_task() sends standard-prefix error message to
  Discord for user visibility but never stores it in channel_history
- ADDED: API_ERROR_PREFIX constant for consistent error message formatting
  and filtering coordination with message_processing.py

CHANGES v1.1.0: Filter noise from runtime history storage (SOW v2.19.0)
- ADDED: is_history_output import for runtime filtering
- MODIFIED: add_response_to_history() now checks is_history_output() before storing
- RESULT: Bot confirmation messages and error messages never enter channel_history
  at runtime; load-time cleanup filter is now a safety net rather than primary defense

Handles AI response processing, message splitting, image sending,
and background task management.
"""
import asyncio
import io
import discord
from utils.ai_utils import generate_ai_response
from utils.message_utils import split_message, create_history_content_for_bot_response
from utils.history import channel_history
from utils.history.message_processing import is_history_output
from utils.logging_utils import get_logger

logger = get_logger('response_handler')

# Standard prefix for API error messages sent to Discord.
# This prefix is also used by is_history_output() to filter these messages
# from channel_history at load time. Must match API_ERROR_PREFIX in
# utils/history/message_processing.py exactly.
API_ERROR_PREFIX = "I'm sorry an API error occurred when attempting to respond: "


async def handle_ai_response_task(message, channel_id, messages, provider_override=None):
    """
    Background task to handle AI response (both text and images).
    Runs in the background to avoid blocking Discord's heartbeat.

    Error messages are sent to Discord with a standard prefix for user visibility
    but are never stored in channel_history.

    Args:
        message: Discord message object that triggered the response
        channel_id: Discord channel ID where response should be sent
        messages: List of messages for AI context
        provider_override: Optional provider name to override channel default
    """
    try:
        bot_response = await generate_ai_response(
            messages,
            channel_id=channel_id,
            provider_override=provider_override
        )

        if isinstance(bot_response, str):
            # Legacy string format
            text_chunks = split_message(bot_response)
            for chunk in text_chunks:
                await message.channel.send(chunk)
            add_response_to_history(channel_id, bot_response)

        elif isinstance(bot_response, dict):
            # Structured format with optional images
            text_content = bot_response.get("text", "")
            images = bot_response.get("images", [])

            if text_content.strip():
                text_chunks = split_message(text_content)
                for chunk in text_chunks:
                    await message.channel.send(chunk)

            for i, image in enumerate(images):
                try:
                    image_buffer = io.BytesIO(image["data"])
                    discord_file = discord.File(image_buffer, filename=f"generated_image_{i+1}.png")
                    await message.channel.send(file=discord_file)
                    logger.debug(f"Sent generated image {i+1}")
                except Exception as e:
                    logger.error(f"Error sending generated image {i+1}: {e}")
                    await message.channel.send("⚠️ I generated an image but couldn't send it.")

            add_response_to_history(channel_id, text_content, len(images))

    except Exception as e:
        # Send user-friendly error message to Discord so users know something
        # went wrong, but do NOT store it in channel_history — it is noise
        # for the AI context and filtered by is_history_output() at load time.
        error_msg = f"{API_ERROR_PREFIX}{str(e)}"
        await message.channel.send(error_msg)
        logger.error(f"Error processing AI response: {e}")


async def handle_ai_response(message, channel_id, messages, provider_override=None):
    """
    Handle AI response using a background task to avoid blocking Discord's heartbeat.

    Args:
        message: Discord message object that triggered the response
        channel_id: Discord channel ID where response should be sent
        messages: List of messages for AI context
        provider_override: Optional provider name to override channel default
    """
    async with message.channel.typing():
        task = asyncio.create_task(
            handle_ai_response_task(message, channel_id, messages, provider_override)
        )
        try:
            await task
        except Exception as e:
            logger.error(f"Error in AI response task: {e}")
            await message.channel.send("Sorry, I encountered an error processing your request.")


async def send_text_response(channel, text_content):
    """
    Send text response to Discord channel with automatic message splitting.

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
    Send image response(s) to Discord channel.

    Args:
        channel: Discord channel object
        images: List of image dictionaries with 'data' and optional metadata

    Returns:
        int: Number of images successfully sent
    """
    sent_count = 0
    for i, image in enumerate(images):
        try:
            image_buffer = io.BytesIO(image["data"])
            discord_file = discord.File(image_buffer, filename=f"generated_image_{i+1}.png")
            await channel.send(file=discord_file)
            logger.debug(f"Sent generated image {i+1}")
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending generated image {i+1}: {e}")
            await channel.send("⚠️ I generated an image but couldn't send it.")

    return sent_count


def add_response_to_history(channel_id, text_content, images_count=0):
    """
    Add AI response to channel conversation history.

    Filters out noise messages (command confirmations, housekeeping, error messages)
    using is_history_output() before storing. This ensures bot-generated noise
    never enters channel_history at runtime.

    Args:
        channel_id: Discord channel ID
        text_content: Text content of the response
        images_count: Number of images generated (default: 0)

    Returns:
        bool: True if response was added to history, False if skipped
    """
    history_content = create_history_content_for_bot_response(text_content, images_count)

    if not history_content.strip():
        logger.debug(f"Skipped adding empty response to history for channel {channel_id}")
        return False

    if is_history_output(history_content):
        logger.debug(
            f"Skipped adding noise message to history for channel {channel_id}: "
            f"{history_content[:50]}..."
        )
        return False

    channel_history[channel_id].append({
        "role": "assistant",
        "content": history_content
    })
    logger.debug(f"Added AI response to history for channel {channel_id}")
    return True
