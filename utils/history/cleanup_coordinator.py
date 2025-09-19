# utils/history/cleanup_coordinator.py
# Version 1.0.0
"""
Final cleanup coordination for Discord message history loading.

This module coordinates the final cleanup operations that occur after message
loading and settings restoration. It handles message filtering, legacy system
prompt restoration, and final validation of the loaded conversation history.

Key Responsibilities:
- Filter out unwanted messages (commands, history outputs, etc.)
- Handle legacy system prompt restoration for backward compatibility
- Perform final validation and statistics reporting
- Clean up any artifacts from the loading process
- Ensure conversation history is in optimal state for AI usage

This module serves as the final step in the history loading workflow and
ensures that the loaded conversation history is clean, consistent, and
ready for use by AI providers and other bot systems.

Created in refactoring to maintain under 200-line limit while preserving
all cleanup and validation functionality from the original loading.py.
"""
from utils.logging_utils import get_logger
from .storage import filter_channel_history, channel_history
from .message_processing import is_bot_command, extract_system_prompt_updates
from .prompts import channel_system_prompts

logger = get_logger('history.cleanup_coordinator')

async def coordinate_final_cleanup(channel):
    """
    Coordinate all final cleanup operations for a channel after history loading.
    
    This function performs the final cleanup steps to ensure the loaded
    conversation history is clean, consistent, and ready for use:
    1. Filter out unwanted messages and commands
    2. Handle legacy system prompt restoration
    3. Perform final validation and reporting
    
    Args:
        channel: Discord channel object that was processed
        
    Returns:
        dict: Summary of cleanup operations performed:
            {
                'messages_filtered': int,
                'legacy_prompts_restored': int,
                'final_message_count': int,
                'cleanup_status': str
            }
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
    
    Removes command messages, history outputs, and other artifacts that
    shouldn't be included in the conversation context sent to AI providers.
    
    Args:
        channel_id: Discord channel ID to filter
        
    Returns:
        dict: Results of filtering operation
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
    
    This function handles the old SYSTEM_PROMPT_UPDATE format for channels
    that haven't been processed by the new real-time settings restoration system.
    It will be deprecated once all channels use the new system.
    
    Args:
        channel_id: Discord channel ID to process
        
    Returns:
        dict: Results of legacy prompt restoration
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
    Perform final validation and generate statistics for the loaded history.
    
    Args:
        channel: Discord channel object
        
    Returns:
        dict: Final validation results and statistics
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
    
    # Generate statistics
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
    Generate detailed statistics about the loaded conversation history.
    
    Args:
        channel_id: Discord channel ID to analyze
        
    Returns:
        dict: Detailed statistics about the conversation history
    """
    if channel_id not in channel_history:
        return {
            'total_messages': 0,
            'user_messages': 0,
            'assistant_messages': 0,
            'system_messages': 0
        }
    
    messages = channel_history[channel_id]
    
    statistics = {
        'total_messages': len(messages),
        'user_messages': 0,
        'assistant_messages': 0,
        'system_messages': 0,
        'average_message_length': 0,
        'has_custom_prompt': channel_id in channel_system_prompts
    }
    
    total_length = 0
    
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'user':
            statistics['user_messages'] += 1
        elif role == 'assistant':
            statistics['assistant_messages'] += 1
        elif role == 'system':
            statistics['system_messages'] += 1
        
        total_length += len(content)
    
    if statistics['total_messages'] > 0:
        statistics['average_message_length'] = round(total_length / statistics['total_messages'], 1)
    
    return statistics
