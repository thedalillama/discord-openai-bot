# utils/response_handler.py
# Version 1.7.3
"""
AI response handling utilities for Discord bot.

CHANGES v1.7.3: Pass receipt_data to run_response_qc() so QC_FAIL details
  (pass 1/2 responses + per-claim reasons) are captured in the receipt.
CHANGES v1.7.2: Save receipt on QC_FAIL (qc_failed=True) for !explain visibility.
CHANGES v1.7.0: General QC pass — run_response_qc() on all responses with context.
CHANGES v1.5.0: Thread _msg_id through bot responses for Layer 2 dedup.
CHANGES v1.4.0: Dead code cleanup — removed send_text_response/send_image_response.
CHANGES v1.3.0: Citation footer support (SOW v5.9.0).
CHANGES v1.2.0: Receipt storage after response send (SOW v5.7.0).
CHANGES v1.1.x: Reasoning split, API error messages, noise filter, trim (SOW v2.19–2.23)
"""
import asyncio
import io
import os
import discord
from utils.ai_utils import generate_ai_response
from utils.message_utils import split_message, create_history_content_for_bot_response
from utils.history import channel_history
from utils.history.message_processing import is_history_output
from utils.logging_utils import get_logger
from config import MAX_HISTORY

logger = get_logger('response_handler')

# Must match API_ERROR_PREFIX in utils/history/message_processing.py exactly.
API_ERROR_PREFIX = "I'm sorry an API error occurred when attempting to respond: "

# Must match constants in ai_providers/openai_compatible_provider.py exactly.
REASONING_PREFIX = "[DEEPSEEK_REASONING]:"
REASONING_SEPARATOR = "\n[DEEPSEEK_ANSWER]:\n"

_I = "ℹ️ "
_QC_FAIL_MSG = _I + "I was unable to produce a verified response to that question. [QC_FAIL]"
_QC_ENABLED = os.environ.get("RESPONSE_QC_ENABLED", "true").lower() == "true"


async def _save_qc_fail_receipt(fail_msg, trigger_id, channel_id, receipt_data):
    if not receipt_data:
        return
    receipt_data["qc_failed"] = True
    try:
        from utils.receipt_store import save_receipt
        await asyncio.to_thread(save_receipt, fail_msg.id, trigger_id, channel_id, receipt_data)
    except Exception:
        pass


async def handle_ai_response_task(message, channel_id, messages,
                                   provider_override=None, receipt_data=None,
                                   citation_map=None):
    """Handle AI response: text/images, reasoning split, QC, citations, receipt storage."""
    from utils.citation_utils import apply_citations
    from utils.response_qc import _has_injected_context, run_response_qc
    _has_ctx = _QC_ENABLED and _has_injected_context(messages[0].get("content", "") if messages else "")
    try:
        bot_response = await generate_ai_response(
            messages,
            channel_id=channel_id,
            provider_override=provider_override
        )

        response_msg = None

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
                if _has_ctx:
                    _qc = await run_response_qc(answer, messages, channel_id, provider_override, receipt_data)
                    if _qc is None:
                        _qf = await message.channel.send(_QC_FAIL_MSG)
                        await _save_qc_fail_receipt(_qf, message.id, channel_id, receipt_data)
                        return
                    answer = _qc
                answer, cite_footer = apply_citations(answer, citation_map or {})
                answer_chunks = split_message(answer)
                for chunk in answer_chunks:
                    response_msg = await message.channel.send(chunk)
                if cite_footer:
                    await message.channel.send(_I + cite_footer)
                add_response_to_history(
                    channel_id, answer,
                    msg_id=getattr(response_msg, 'id', None))

        elif isinstance(bot_response, str):
            if _has_ctx:
                _qc = await run_response_qc(bot_response, messages, channel_id, provider_override, receipt_data)
                if _qc is None:
                    _qf = await message.channel.send(_QC_FAIL_MSG)
                    await _save_qc_fail_receipt(_qf, message.id, channel_id, receipt_data)
                    return
                bot_response = _qc
            bot_response, cite_footer = apply_citations(bot_response, citation_map or {})
            text_chunks = split_message(bot_response)
            for chunk in text_chunks:
                response_msg = await message.channel.send(chunk)
            if cite_footer:
                await message.channel.send(_I + cite_footer)
            add_response_to_history(
                channel_id, bot_response,
                msg_id=getattr(response_msg, 'id', None))

        elif isinstance(bot_response, dict):
            text_content = bot_response.get("text", "")
            images = bot_response.get("images", [])
            if _has_ctx:
                _qc = await run_response_qc(text_content, messages, channel_id, provider_override, receipt_data)
                if _qc is None:
                    _qf = await message.channel.send(_QC_FAIL_MSG)
                    await _save_qc_fail_receipt(_qf, message.id, channel_id, receipt_data)
                    return
                text_content = _qc
            text_content, cite_footer = apply_citations(text_content, citation_map or {})

            if text_content.strip():
                text_chunks = split_message(text_content)
                for chunk in text_chunks:
                    response_msg = await message.channel.send(chunk)
                if cite_footer:
                    await message.channel.send(_I + cite_footer)

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

            add_response_to_history(
                channel_id, text_content, len(images),
                msg_id=getattr(response_msg, 'id', None))

        if receipt_data and response_msg:
            try:
                from utils.receipt_store import save_receipt
                await asyncio.to_thread(
                    save_receipt, response_msg.id, message.id,
                    channel_id, receipt_data)
            except Exception as re:
                logger.warning(f"Receipt storage failed ch:{channel_id}: {re}")

    except Exception as e:
        error_msg = f"{API_ERROR_PREFIX}{str(e)}"
        await message.channel.send(error_msg)
        logger.error(f"Error processing AI response: {e}")


async def handle_ai_response(message, channel_id, messages, provider_override=None,
                             receipt_data=None, citation_map=None):
    """
    Handle AI response using a background task to avoid blocking Discord's heartbeat.

    Args:
        message: Discord message object that triggered the response
        channel_id: Discord channel ID where response should be sent
        messages: List of messages for AI context
        provider_override: Optional provider name to override channel default
        receipt_data: Optional context receipt dict to persist after send
        citation_map: Optional {int: {author, content, date}} for citation validation
    """
    async with message.channel.typing():
        task = asyncio.create_task(
            handle_ai_response_task(
                message, channel_id, messages, provider_override,
                receipt_data, citation_map)
        )
        try:
            await task
        except Exception as e:
            logger.error(f"Error in AI response task: {e}")
            await message.channel.send("Sorry, I encountered an error processing your request.")


def add_response_to_history(channel_id, text_content, images_count=0, msg_id=None):
    """
    Add AI response to channel conversation history.

    Filters noise messages via is_history_output() before storing.
    Trims to MAX_HISTORY after appending to prevent temporary overshoot.

    Args:
        channel_id: Discord channel ID
        text_content: Text content of the response
        images_count: Number of images generated (default: 0)
        msg_id: Discord message ID for Layer 2 deduplication (optional)

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

    entry = {"role": "assistant", "content": history_content}
    if msg_id is not None:
        entry["_msg_id"] = msg_id
    channel_history[channel_id].append(entry)

    # Trim to MAX_HISTORY to prevent temporary overshoot between
    # user append (in bot.py) and assistant append (here)
    if len(channel_history[channel_id]) > MAX_HISTORY:
        channel_history[channel_id] = channel_history[channel_id][-MAX_HISTORY:]
        logger.debug(f"Trimmed history to {MAX_HISTORY} after assistant append for channel {channel_id}")

    logger.debug(f"Added AI response to history for channel {channel_id}")
    return True
