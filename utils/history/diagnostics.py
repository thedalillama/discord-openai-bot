# utils/history/diagnostics.py
# Version 1.0.0
"""
Diagnostic and analysis tools for Discord message history loading.

This module provides comprehensive diagnostic capabilities for troubleshooting
and analyzing the history loading system. Functions were extracted from
loading_utils.py in v1.0.0 to maintain the 250-line limit while preserving
all diagnostic functionality.

Key Responsibilities:
- Detailed channel diagnostics and analysis
- Potential issue identification in message histories
- Memory usage estimation and resource monitoring
- Content analysis and statistics generation
- Troubleshooting support for loading problems

These diagnostic tools are separated from core loading utilities to keep
the main workflow focused while providing deep analysis capabilities for
system administrators and developers.
"""
from utils.logging_utils import get_logger
from .storage import loaded_history_channels, channel_history
from .prompts import channel_system_prompts

logger = get_logger('history.diagnostics')

def get_channel_diagnostics(channel_id):
    """
    Get detailed diagnostic information about a specific channel's history.
    
    Provides comprehensive diagnostic information useful for troubleshooting
    loading issues or understanding the state of a channel's conversation history.
    
    Args:
        channel_id: Discord channel ID to diagnose
        
    Returns:
        dict: Detailed diagnostic information including:
            - channel_id: The channel ID analyzed
            - is_loaded: Whether history is loaded
            - load_timestamp: When history was loaded
            - message_count: Number of messages in history
            - has_custom_prompt: Whether channel has custom system prompt
            - message_roles: Count of messages by role (user/assistant/system)
            - content_statistics: Average length, max/min lengths, total characters
            - potential_issues: List of identified issues
    """
    diagnostics = {
        'channel_id': channel_id,
        'is_loaded': channel_id in loaded_history_channels,
        'load_timestamp': loaded_history_channels.get(channel_id),
        'message_count': len(channel_history.get(channel_id, [])),
        'has_custom_prompt': channel_id in channel_system_prompts,
        'message_roles': {},
        'content_statistics': {},
        'potential_issues': []
    }
    
    # Analyze message content if available
    if channel_id in channel_history:
        messages = channel_history[channel_id]
        
        # Count messages by role
        for msg in messages:
            role = msg.get('role', 'unknown')
            diagnostics['message_roles'][role] = diagnostics['message_roles'].get(role, 0) + 1
        
        # Analyze content statistics
        if messages:
            content_lengths = [len(msg.get('content', '')) for msg in messages]
            diagnostics['content_statistics'] = {
                'average_length': round(sum(content_lengths) / len(content_lengths), 1),
                'max_length': max(content_lengths),
                'min_length': min(content_lengths),
                'total_characters': sum(content_lengths)
            }
        
        # Check for potential issues
        diagnostics['potential_issues'] = identify_potential_issues(messages)
    
    logger.debug(f"Generated diagnostics for channel {channel_id}: {diagnostics['message_count']} messages, "
                f"{len(diagnostics['potential_issues'])} issues identified")
    
    return diagnostics

def identify_potential_issues(messages):
    """
    Identify potential issues in a channel's conversation history.
    
    Analyzes message structure and content to detect common problems that
    might affect AI processing or indicate loading issues.
    
    Args:
        messages: List of message dictionaries to analyze
        
    Returns:
        list: List of issue descriptions found in the messages
    """
    issues = []
    
    if not messages:
        issues.append("No messages found in history")
        return issues
    
    # Check for structural issues
    for i, msg in enumerate(messages[:10]):  # Check first 10 messages for performance
        if not isinstance(msg, dict):
            issues.append(f"Message {i} is not a dictionary")
            continue
            
        if 'role' not in msg:
            issues.append(f"Message {i} missing 'role' field")
        elif msg['role'] not in ['user', 'assistant', 'system']:
            issues.append(f"Message {i} has invalid role: {msg.get('role')}")
            
        if 'content' not in msg:
            issues.append(f"Message {i} missing 'content' field")
        elif not msg.get('content'):
            issues.append(f"Message {i} has empty content")
    
    # Check for conversation flow issues
    roles = [msg.get('role') for msg in messages if msg.get('role')]
    
    # Check for excessive consecutive messages from same role
    consecutive_count = 1
    current_role = None
    
    for role in roles:
        if role == current_role:
            consecutive_count += 1
            if consecutive_count > 5:
                issues.append(f"More than 5 consecutive {role} messages detected")
                break
        else:
            consecutive_count = 1
            current_role = role
    
    # Check for very long messages that might cause API issues
    long_messages = [i for i, msg in enumerate(messages) 
                    if len(msg.get('content', '')) > 8000]
    if long_messages:
        issues.append(f"Found {len(long_messages)} messages over 8000 characters")
    
    # Check for message format consistency
    user_messages = [msg for msg in messages if msg.get('role') == 'user']
    if user_messages:
        # Check if user messages have consistent format
        with_names = sum(1 for msg in user_messages[:5] if ':' in msg.get('content', ''))
        if 0 < with_names < len(user_messages[:5]):
            issues.append("Inconsistent username format in user messages")
    
    logger.debug(f"Identified {len(issues)} potential issues in {len(messages)} messages")
    return issues

def estimate_memory_usage(total_messages):
    """
    Provide rough estimate of memory usage for conversation histories.
    
    Calculates approximate memory consumption based on typical message sizes
    and provides estimates in different units for monitoring purposes.
    
    Args:
        total_messages: Total number of messages across all channels
        
    Returns:
        dict: Memory usage estimate with keys:
            - bytes: Estimated bytes used
            - kilobytes: Estimated KB used  
            - megabytes: Estimated MB used
            - note: Explanation of calculation method
    """
    # Rough estimates based on typical message sizes
    # Average message: ~200 characters content + ~100 bytes metadata = ~300 bytes
    bytes_per_message = 300
    estimated_bytes = total_messages * bytes_per_message
    
    return {
        'bytes': estimated_bytes,
        'kilobytes': round(estimated_bytes / 1024, 1),
        'megabytes': round(estimated_bytes / (1024 * 1024), 2),
        'note': 'Rough estimate based on average message size of 300 bytes'
    }

def analyze_channel_health(channel_id):
    """
    Perform comprehensive health analysis of a specific channel.
    
    Combines diagnostics, issue identification, and performance metrics
    to provide an overall health assessment of a channel's history.
    
    Args:
        channel_id: Discord channel ID to analyze
        
    Returns:
        dict: Health analysis with overall status and recommendations
    """
    diagnostics = get_channel_diagnostics(channel_id)
    
    health_status = "healthy"
    recommendations = []
    
    # Evaluate based on diagnostics
    if not diagnostics['is_loaded']:
        health_status = "warning"
        recommendations.append("Channel history not loaded")
    
    if diagnostics['message_count'] == 0:
        health_status = "warning" 
        recommendations.append("No messages found in history")
    
    if len(diagnostics['potential_issues']) > 0:
        health_status = "issues_detected"
        recommendations.extend(diagnostics['potential_issues'][:3])  # Top 3 issues
    
    # Check message distribution
    roles = diagnostics.get('message_roles', {})
    if roles.get('user', 0) == 0:
        health_status = "warning"
        recommendations.append("No user messages found")
    elif roles.get('assistant', 0) == 0:
        health_status = "warning"
        recommendations.append("No assistant messages found")
    
    return {
        'channel_id': channel_id,
        'health_status': health_status,
        'message_count': diagnostics['message_count'],
        'issues_found': len(diagnostics['potential_issues']),
        'recommendations': recommendations,
        'last_analyzed': diagnostics['load_timestamp']
    }
