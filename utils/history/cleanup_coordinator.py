# utils/history/cleanup_coordinator.py
# Version 2.1.0
"""
Final cleanup coordination for Discord message history loading.

CHANGES v2.1.0: Expand filtering to include assistant-side noise (SOW v2.14.0)
- ADDED: is_history_output import for assistant message filtering
- EXPANDED: _filter_conversation_history() now filters assistant messages matching is_history_output()
- EXPANDED: Also filters system messages that are not SYSTEM_PROMPT_UPDATE records
- FIXED: Stale !setprompt reference → !prompt for v2.13.0 consistency
- RESULT: Full cleanup matching !history clean logic, eliminating noise in AI context

CHANGES v2.0.0: Removed legacy system prompt support
- REMOVED: Legacy system prompt restoration for old SYSTEM_PROMPT_UPDATE format
- SIMPLIFIED: Focus only on message filtering and final validation
- ELIMINATED: Backward compatibility overhead (no longer needed)

This module coordinates final cleanup operations after message loading.
Handles message filtering and final validation of loaded conversation history.

Key Responsibilities:
- Filter out unwanted messages (commands, history outputs, etc.)
- Perform final validation and statistics reporting
- Clean up artifacts from the loading process
- Ensure conversation history is ready for AI usage

All system prompt handling is now done via realtime parsing during Discord loading.
"""
from utils.logging_utils import get_logger
from .storage import channel_history
from .message_processing import is_bot_command, is_history_output

logger = get_logger('history.cleanup_coordinator')

async def coordinate_final_cleanup(channel):
    """
    Coordinate final cleanup operations for a channel after history loading.
    
    Performs cleanup steps: filter unwanted messages and validate final results.
    System prompts are handled during realtime parsing, no legacy support needed.
    
    Args:
        channel: Discord channel object that was processed
        
    Returns:
        dict: Summary of cleanup operations with counts and status
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"Starting final cleanup coordination for channel #{channel_name}")
    
    result = {
        'messages_filtered': 0,
        'final_message_count': 0,
        'cleanup_status': 'started'
    }
    
    try:
        # Step 1: Filter unwanted messages from conversation history
        filter_result = await _filter_conversation_history(channel_id)
        result['messages_filtered'] = filter_result['removed_count']
        
        # Step 2: Final validation and statistics
        final_result = await _perform_final_validation(channel)
        result['final_message_count'] = final_result['message_count']
        
        result['cleanup_status'] = 'completed'
        
        logger.info(f"Final cleanup completed for channel #{channel_name}: "
                   f"{result['messages_filtered']} filtered, "
                   f"{result['final_message_count']} final messages")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during final cleanup for channel #{channel_name}: {e}")
        result['cleanup_status'] = f'error: {str(e)}'
        raise

async def _filter_conversation_history(channel_id):
    """
    Filter conversation history to remove unwanted messages.
    
    Removes bot commands, history outputs, and system artifacts not needed for
    AI context. This applies the same filtering logic as !history clean to ensure
    automatic reload and manual reload produce the same clean results.
    """
    logger.debug(f"Filtering conversation history for channel {channel_id}")
    
    if channel_id not in channel_history or not channel_history[channel_id]:
        logger.debug(f"No history to filter for channel {channel_id}")
        return {
            'original_count': 0,
            'filtered_count': 0,
            'removed_count': 0
        }
    
    before_count = len(channel_history[channel_id])
    
    # Apply full cleanup filter matching !history clean logic:
    # 1. Filter user-side bot commands (except !prompt which carries settings)
    # 2. Filter assistant-side history outputs (status messages, help, etc.)
    # 3. Filter system messages that are not SYSTEM_PROMPT_UPDATE records
    channel_history[channel_id] = [
        msg for msg in channel_history[channel_id]
        if (
            not (msg["role"] == "user" and is_bot_command(msg["content"])) and
            not (msg["role"] == "assistant" and is_history_output(msg["content"])) and
            not (msg["role"] == "system" and not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:"))
        )
    ]
    
    after_count = len(channel_history[channel_id])
    removed_count = before_count - after_count
    
    if removed_count > 0:
        logger.debug(f"Filtered {removed_count} noise messages from history")
    
    return {
        'original_count': before_count,
        'filtered_count': after_count,
        'removed_count': removed_count
    }

async def _perform_final_validation(channel):
    """
    Perform final validation and generate statistics for loaded history.
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"Performing final validation for channel #{channel_name}")
    
    # Get final message count
    final_message_count = len(channel_history.get(channel_id, []))
    
    # Basic validation checks
    validation_issues = []
    
    if final_message_count == 0:
        validation_issues.append("No messages in final history")
    
    if channel_id not in channel_history:
        validation_issues.append("Channel not found in channel_history")
    
    # Check for message format consistency
    if channel_id in channel_history:
        for i, msg in enumerate(channel_history[channel_id][:5]):  # Check first 5 messages
            if not isinstance(msg, dict):
                validation_issues.append(f"Message {i} is not a dictionary")
            elif 'role' not in msg:
                validation_issues.append(f"Message {i} missing 'role' field")
            elif 'content' not in msg:
                validation_issues.append(f"Message {i} missing 'content' field")
    
    # Log validation results
    if validation_issues:
        logger.warning(f"Final validation found issues for channel #{channel_name}: {validation_issues}")
    else:
        logger.debug(f"Final validation passed for channel #{channel_name}")
    
    # Generate simplified statistics
    statistics = _generate_history_statistics(channel_id)
    
    logger.info(f"Final validation complete for channel #{channel_name}: "
               f"{final_message_count} messages, {len(validation_issues)} issues")
    
    return {
        'message_count': final_message_count,
        'validation_issues': validation_issues,
        'statistics': statistics
    }

def _generate_history_statistics(channel_id):
    """
    Generate basic statistics for validation reporting.
    Simplified to provide essential information while reducing code complexity.
    """
    return {
        'total_messages': len(channel_history.get(channel_id, [])),
        'note': 'detailed statistics removed for code optimization'
    }
