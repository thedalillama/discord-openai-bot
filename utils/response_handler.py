# utils/response_handler.py
# Version 1.1.3
"""
AI response handling utilities for Discord bot.

CHANGES v1.1.3: Fix reasoning/answer split boundary (SOW v2.20.0 bugfix)
- CHANGED: Split on REASONING_SEPARATOR ([DEEPSEEK_ANSWER]:) instead of
  first \n\n — prevents reasoning paragraphs from being mistaken for the
  split point when reasoning_content contains blank lines

CHANGES v1.1.2: Handle [DEEPSEEK_REASONING]: prefix (SOW v2.20.0)
- MODIFIED: handle_ai_response_task() detects REASONING_PREFIX and splits
  response into two separate Discord messages — reasoning first, answer second
- ADDED: REASONING_PREFIX and REASONING_SEPARATOR constants

CHANGES v1.1.1: User-friendly API error messages (SOW v2.19.0)
- MODIFIED: Error messages sent to Discord with standard prefix, never stored
- ADDED: API_ERROR_PREFIX constant

CHANGES v1.1.0: Filter noise from runtime history storage (SOW v2.19.0)
- MODIFIED: add_response_to_history() checks is_history_output() before storing
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

# Must match API_ERROR_PREFIX in utils/history/message_processing.py exactly.
API_ERROR_PREFIX = "I'm sorry an API error occurred when attempting to respond: "

# Must match constants in ai_providers/openai_compatible_provider.py exactly.
REASONING_PREFIX = "[DEEPSEEK_REASONING]:"
REASONING_SEPARATOR = "\n[DEEPSEEK_ANSWER]:\n"


async def handle_ai_response_task(message, channel_id, messages, provider_override=None):
    """
    Background task to handle AI response (text and optional images).

    When response starts with REASONING_PREFIX, splits on REASONING_SEPARATOR
    into two Discord messages: reasoning first (not stored in history),
    answer second (stored normally).

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

        if isinstance(bot_response, str) and bot_response.startswith(REASONING_PREFIX):
            # Split on unambiguous separator — not \n\n which may appear in reasoning
            parts = bot_response.split(REASONING_SEPARATOR, 1)
            reasoning_block = parts[0]
            answer = parts[1] if len(parts) > 1 else ""

            # Send reasoning as separate message(s) — not stored in history
            if reasoning_block.strip():
                reasoning_chunks = split_message(reasoning_block)
                for chunk in reasoning_chunks:
                    await message.channel.send(chunk)

            # Send answer and store in history
            if answer.strip():
                answer_chunks = split_message(answer)
                for chunk in answer_chunks:
                    await message.channel.send(chunk)
                add_response_to_history(channel_id, answer)

        elif isinstance(bot_response, str):
            text_chunks = split_message(bot_response)
            for chunk in text_chunks:
                await message.channel.send(chunk)
            add_response_to_history(channel_id, bot_response)

        elif isinstance(bot_response, dict):
            text_content = bot_response.get("text", "")
            images = bot_response.get("images", [])

            if text_content.strip():
                text_chunks = split_message(text_content)
                for chunk in text_chunks:
                    await message.channel.send(chunk)

            for i, image in enumerate(images):
                try:
                    image_buffer = io.BytesIO(image["data"])
                    discord_file = discord.File(
                        image_buffer, filename=f"generated_image_{i+1}.png"
                    )
                    await message.channel.send(file=discord_file)
                    logger.debug(f"Sent generated image {i+1}")
                except Exception as e:
                    logger.error(f"Error sending generated image {i+1}: {e}")
                    await message.channel.send("⚠️ I generated an image but couldn't send it.")

            add_response_to_history(channel_id, text_content, len(images))

    except Exception as e:
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
    """Send text response to Discord channel with automatic message splitting."""
    if not text_content or not text_content.strip():
        logger.debug("No text content to send")
        return 0
    text_chunks = split_message(text_content)
    for i, chunk in enumerate(text_chunks):
        await channel.send(chunk)
        logger.debug(f"Sent text chunk {i+1}/{len(text_chunks)}")
    return len(text_chunks)


async def send_image_response(channel, images):
    """Send image response(s) to Discord channel."""
    sent_count = 0
    for i, image in enumerate(images):
        try:
            image_buffer = io.BytesIO(image["data"])
            discord_file = discord.File(
                image_buffer, filename=f"generated_image_{i+1}.png"
            )
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

    Filters noise messages via is_history_output() before storing.

    Args:
        channel_id: Discord channel ID
        text_content: Text content of the response
        images_count: Number of images generated (default: 0)

    Returns:
        bool: True if added, False if skipped
    """
    history_content = create_history_content_for_bot_response(text_content, images_count)

    if not history_content.strip():
        logger.debug(f"Skipped empty response for channel {channel_id}")
        return False

    if is_history_output(history_content):
        logger.debug(f"Skipped noise message for channel {channel_id}: {history_content[:50]}...")
        return False

    channel_history[channel_id].append({
        "role": "assistant",
        "content": history_content
    })
    logger.debug(f"Added AI response to history for channel {channel_id}")
    return True
