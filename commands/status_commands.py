# commands/status_commands.py
# Version 1.1.1
"""
Status command for displaying current bot configuration settings.

CHANGES v1.1.1: Fixed URL object string conversion bug
- FIXED: TypeError when checking URL object with 'in' operator
- ENHANCED: Proper string conversion of base_url before string operations
- MAINTAINED: All existing functionality

CHANGES v1.1.0: Added provider backend identification from URL
- ADDED: URL parsing to identify actual provider backend (DeepSeek, BaseTen, etc.)
- ENHANCED: AI provider display shows both model and backend provider
- MAINTAINED: All existing status functionality
- IMPROVED: Better transparency for OpenAI-compatible provider usage

This module provides a comprehensive status overview showing all current
bot settings for a channel including system prompt, AI provider, auto-response,
and thinking display settings.

Key Features:
- Single command to view all channel settings
- Available to all users (no admin requirement)
- Shows full system prompt text
- Displays current vs default settings clearly
- Shows actual provider backend for OpenAI-compatible providers
- Graceful handling of missing or default settings
"""
from discord.ext import commands
from urllib.parse import urlparse
from utils.logging_utils import get_logger
from utils.history import get_system_prompt, get_ai_provider
from config import AI_PROVIDER, DEFAULT_SYSTEM_PROMPT
from ai_providers import get_provider

# Get logger for status commands
logger = get_logger('commands.status')

def get_provider_company_from_url(base_url):
    """
    Extract company name from URL domain for provider identification.
    
    Args:
        base_url: The base URL of the API provider
        
    Returns:
        str: Capitalized company name (e.g., "Deepseek", "Baseten", "Custom")
    """
    if not base_url:
        return "Unknown"
    
    try:
        # Extract domain from URL
        domain = urlparse(base_url).netloc.lower()
        
        # Split by dots and get second-to-last part
        parts = domain.split('.')
        if len(parts) >= 2:
            company = parts[-2]
            # Capitalize first letter for display
            return company.capitalize()
        return "Custom"
    except Exception as e:
        logger.debug(f"Error parsing provider URL {base_url}: {e}")
        return "Unknown"

def get_provider_backend_info(provider_name, channel_id):
    """
    Get backend provider information for display in status.
    
    Args:
        provider_name: The provider name (openai, anthropic, deepseek, etc.)
        channel_id: Discord channel ID
        
    Returns:
        str: Provider display string with backend info if applicable
    """
    try:
        # Get the actual provider instance
        provider = get_provider(provider_name, channel_id)
        
        # For OpenAI-compatible providers, show the backend
        if hasattr(provider, 'client') and hasattr(provider.client, 'base_url'):
            base_url = provider.client.base_url
            base_url_str = str(base_url) if base_url else ""
            if base_url_str and 'openai.com' not in base_url_str:  # Not standard OpenAI
                company = get_provider_company_from_url(base_url_str)
                return f"{provider_name} ({company})"
        
        # For standard providers, just return the name
        return provider_name
        
    except Exception as e:
        logger.debug(f"Error getting provider backend info: {e}")
        return provider_name

def register_status_commands(bot, auto_respond_channels):
    """Register status command with the bot"""
    
    @bot.command(name='status')
    async def status_cmd(ctx):
        """
        Display current bot configuration settings for this channel.
        
        Shows:
        - System prompt (full text)
        - AI provider (current setting and backend provider)
        - Auto-response status
        - Thinking display status
        
        Usage: !status
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name
        
        logger.debug(f"Status command requested for #{channel_name} by {ctx.author.display_name}")
        
        try:
            # Build status message
            status_lines = [f"**Bot Status for #{channel_name}**", ""]
            
            # System Prompt Status
            current_prompt = get_system_prompt(channel_id)
            if current_prompt == DEFAULT_SYSTEM_PROMPT:
                status_lines.append(f"**System Prompt:** Default")
                status_lines.append(f"```{current_prompt}```")
            else:
                status_lines.append(f"**System Prompt:** Custom")
                status_lines.append(f"```{current_prompt}```")
            
            status_lines.append("")  # Empty line for spacing
            
            # AI Provider Status with Backend Info
            current_provider = get_ai_provider(channel_id)
            provider_display_name = current_provider or AI_PROVIDER
            
            # Get backend information
            provider_with_backend = get_provider_backend_info(provider_display_name, channel_id)
            
            if current_provider is None:
                status_lines.append(f"**AI Provider:** {provider_with_backend} (default)")
            else:
                if current_provider == AI_PROVIDER:
                    status_lines.append(f"**AI Provider:** {provider_with_backend} (matches default)")
                else:
                    status_lines.append(f"**AI Provider:** {provider_with_backend} (channel setting)")
                    status_lines.append(f"Default: {AI_PROVIDER}")
            
            # Auto-Response Status
            auto_respond_enabled = channel_id in auto_respond_channels
            auto_status = "enabled" if auto_respond_enabled else "disabled"
            status_lines.append(f"**Auto-Response:** {auto_status}")
            
            # Thinking Display Status
            thinking_status = _get_thinking_status(channel_id)
            status_lines.append(f"**Thinking Display:** {thinking_status}")
            
            # Combine all status lines
            status_message = "\n".join(status_lines)
            
            # Send the status message
            await ctx.send(status_message)
            
            logger.info(f"Status displayed for #{channel_name} - Prompt: {'custom' if current_prompt != DEFAULT_SYSTEM_PROMPT else 'default'}, Provider: {provider_with_backend}, Auto: {auto_status}, Thinking: {thinking_status}")
            
        except Exception as e:
            logger.error(f"Error generating status for #{channel_name}: {e}")
            await ctx.send(f"Error retrieving status for #{channel_name}. Please try again.")

def _get_thinking_status(channel_id):
    """
    Get the current thinking display status for a channel.
    
    Args:
        channel_id: Discord channel ID
        
    Returns:
        str: "enabled" or "disabled" based on thinking command settings
    """
    try:
        # Import here to avoid circular imports
        from commands.thinking_commands import get_thinking_enabled
        return "enabled" if get_thinking_enabled(channel_id) else "disabled"
    except ImportError:
        # If thinking commands not available, assume disabled
        logger.debug("Thinking commands module not available")
        return "disabled"
    except Exception as e:
        logger.debug(f"Error checking thinking status: {e}")
        return "unknown"
