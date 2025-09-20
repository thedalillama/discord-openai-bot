# utils/history/cleanup_coordinator.py
# Version 2.0.0
"""
Final cleanup coordination for Discord message history loading.

CHANGES v2.0.0: Removed legacy system prompt support
- REMOVED: Legacy system prompt restoration for old SYSTEM_PROMPT_UPDATE format
- SIMPLIFIED: Focus only on message filtering and final validation
- ELIMINATED: Backward compatibility overhead (no longer needed)

CHANGES v1.2.1: Minor formatting adjustment to meet 250-line limit
CHANGES v1.2.0: Simplified statistics generation for maintainability
- Reduced _generate_history_statistics from 85 lines to 5 lines
- Removed unused detailed statistics (user/assistant counts, average length)
- Maintained essential message count for validation
- Reduced file size from 280 to under 250 lines while preserving all functionality

This module coordinates final cleanup operations after message loading.
Handles message filtering and final validation of loaded conversation history.

Key Responsibilities:
- Filter out unwanted messages (commands, history outputs, etc.)
- Perform final validation and statistics reporting
- Clean up artifacts from the loading process
- Ensure conversation history is ready for AI usage

All system prompt handling is now done via realtime parsing during Discord loading.
No legacy format support is needed since realtime parsing handles all cases.
"""
from utils.logging_utils import get_logger
from .storage import filter_channel_history, channel_history
from .message_processing import is_bot_command

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
    Removes commands, history outputs and artifacts not needed for AI context.
    """
    logger.debug(f"Filtering conversation history for channel {channel_id}")
    
    # Filter out command messages that slipped through, except setprompt
    original_count, filtered_count, removed_count = filter_channel_history(
        channel_id, 
        lambda msg: not (
            msg["role"] == "user" and 
            is_bot_command(msg["content"]) and 
            not msg["content"].startswith('!setprompt')
        )
    )
    
    if removed_count > 0:
        logger.debug(f"Filtered {removed_count} command messages from history")
    
    return {
        'original_count': original_count,
        'filtered_count': filtered_count,
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
