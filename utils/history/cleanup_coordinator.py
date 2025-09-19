# utils/history/cleanup_coordinator.py
# Version 1.2.1
"""
Final cleanup coordination for Discord message history loading.

CHANGES v1.2.1: Minor formatting adjustment to meet 250-line limit
CHANGES v1.2.0: Simplified statistics generation for maintainability
- Reduced _generate_history_statistics from 85 lines to 5 lines
- Removed unused detailed statistics (user/assistant counts, average length)
- Maintained essential message count for validation
- Reduced file size from 280 to under 250 lines while preserving all functionality

This module coordinates final cleanup operations after message loading and settings
restoration. Handles message filtering, legacy system prompt restoration, and final
validation of loaded conversation history.

Key Responsibilities:
- Filter out unwanted messages (commands, history outputs, etc.)
- Handle legacy system prompt restoration for backward compatibility
- Perform final validation and statistics reporting
- Clean up artifacts from the loading process
- Ensure conversation history is ready for AI usage

Created in refactoring to maintain under 250-line limit while preserving
all cleanup and validation functionality.
"""
from utils.logging_utils import get_logger
from .storage import filter_channel_history, channel_history
from .message_processing import is_bot_command, extract_system_prompt_updates
from .prompts import channel_system_prompts

logger = get_logger('history.cleanup_coordinator')

async def coordinate_final_cleanup(channel):
    """
    Coordinate final cleanup operations for a channel after history loading.
    
    Performs cleanup steps: filter unwanted messages, handle legacy prompts, 
    and validate final results.
    
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
        'legacy_prompts_restored': 0,
        'final_message_count': 0,
        'cleanup_status': 'started'
    }
    
    try:
        # Step 1: Filter unwanted messages from conversation history
        filter_result = await _filter_conversation_history(channel_id)
        result['messages_filtered'] = filter_result['removed_count']
        
        # Step 2: Handle legacy system prompt restoration for backward compatibility
        legacy_result = await _handle_legacy_system_prompts(channel_id)
        result['legacy_prompts_restored'] = legacy_result['prompts_restored']
        
        # Step 3: Final validation and statistics
        final_result = await _perform_final_validation(channel)
        result['final_message_count'] = final_result['message_count']
        
        result['cleanup_status'] = 'completed'
        
        logger.info(f"Final cleanup completed for channel #{channel_name}: "
                   f"{result['messages_filtered']} filtered, "
                   f"{result['legacy_prompts_restored']} legacy prompts, "
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

async def _handle_legacy_system_prompts(channel_id):
    """
    Handle legacy system prompt restoration for backward compatibility.
    Processes old SYSTEM_PROMPT_UPDATE format for channels not using new system.
    """
    logger.debug(f"Checking for legacy system prompt restoration for channel {channel_id}")
    
    prompts_restored = 0
    
    # Only restore legacy prompts if no modern prompt is already set
    if channel_id not in channel_system_prompts:
        try:
            # Look for legacy system prompt updates using the old method
            system_updates = extract_system_prompt_updates(channel_history[channel_id])
            
            logger.debug(f"Found {len(system_updates)} legacy system prompt updates")
            
            if system_updates:
                # Get the most recent update
                latest_update = system_updates[-1]
                
                # Extract the prompt (remove the prefix)
                prompt_text = latest_update["content"].replace("SYSTEM_PROMPT_UPDATE:", "", 1).strip()
                
                if prompt_text:
                    # Restore the prompt using legacy method
                    channel_system_prompts[channel_id] = prompt_text
                    prompts_restored = 1
                    logger.info(f"Restored legacy system prompt for channel {channel_id}: {prompt_text[:50]}...")
                else:
                    logger.debug(f"Legacy prompt text was empty after extraction")
            else:
                logger.debug(f"No legacy system prompt updates found for channel {channel_id}")
                
        except Exception as e:
            logger.error(f"Error during legacy system prompt restoration for channel {channel_id}: {e}")
    else:
        logger.debug(f"Channel {channel_id} already has modern system prompt, skipping legacy restoration")
    
    return {
        'prompts_restored': prompts_restored
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
