# commands/thinking_commands.py
# Version 2.0.0
"""
Thinking display management command for the Discord bot.

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REMOVED: @commands.has_permissions decorator — replaced with manual admin check
- REMOVED: !thinkingstatus command — no-arg !thinking now shows status (all users)
- ADDED: No-arg path shows current status + options (all users)
- ADDED: Manual permission check for write operations only
- PRESERVED: Exact confirmation message strings required by realtime_settings_parser

Usage:
  !thinking        - Show current thinking display status and options (all users)
  !thinking on     - Enable DeepSeek thinking display (admin only)
  !thinking off    - Disable DeepSeek thinking display (admin only)
"""
from utils.logging_utils import get_logger
import re

logger = get_logger('commands.thinking')

# Dictionary to store thinking display preference per channel
# Default to False (hide thinking) for cleaner output
channel_thinking_enabled = {}


def get_thinking_enabled(channel_id):
    """
    Get the thinking display setting for a channel.

    Args:
        channel_id: The Discord channel ID

    Returns:
        bool: True if thinking should be displayed, False otherwise
    """
    return channel_thinking_enabled.get(channel_id, False)


def set_thinking_enabled(channel_id, enabled):
    """
    Set the thinking display setting for a channel.

    Args:
        channel_id: The Discord channel ID
        enabled: Whether to display DeepSeek thinking

    Returns:
        bool: True if this is a change, False if same as before
    """
    current_setting = get_thinking_enabled(channel_id)
    if current_setting == enabled:
        return False

    if enabled:
        channel_thinking_enabled[channel_id] = True
    else:
        # Remove from dict when disabled (saves memory, defaults to False)
        channel_thinking_enabled.pop(channel_id, None)

    return True


def filter_thinking_tags(text, show_thinking=True):
    """
    Filter DeepSeek thinking tags from response text.

    Args:
        text: The response text that may contain <think> tags
        show_thinking: Whether to keep or remove the thinking sections

    Returns:
        str: Filtered text
    """
    if show_thinking:
        return text

    # Pattern to match <think>...</think> including nested content and newlines
    think_pattern = r'<think>.*?</think>'

    # Remove thinking sections (case insensitive, multiline, dotall)
    filtered_text = re.sub(think_pattern, '', text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

    # Clean up extra whitespace left behind
    filtered_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', filtered_text)
    filtered_text = filtered_text.strip()

    if not filtered_text.strip():
        return "[Response contained only thinking content - no final answer provided]"

    return filtered_text


def register_thinking_commands(bot):
    """Register thinking display management command with the bot"""

    @bot.command(name='thinking')
    async def thinking_cmd(ctx, setting=None):
        """
        Manage DeepSeek thinking display for this channel.

        Usage:
          !thinking        - Show current status and options (all users)
          !thinking on     - Enable thinking display (🔒 admin only)
          !thinking off    - Disable thinking display (🔒 admin only)

        Args:
            setting: 'on', 'off', or None to show current status
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        # --- No-arg: show current status + options (all users) ---
        if setting is None:
            current_setting = get_thinking_enabled(channel_id)
            status = "enabled" if current_setting else "disabled"
            logger.debug(f"Thinking status requested for #{channel_name} by {ctx.author.display_name}: {status}")
            await ctx.send(
                f"DeepSeek thinking display is currently **{status}** in #{channel_name}\n"
                f"Options: on, off"
            )
            return

        # --- Write operations: admin only ---
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to change this setting.")
            logger.warning(f"Unauthorized thinking change attempt by {ctx.author.display_name} in #{channel_name}")
            return

        # --- Parse setting ---
        setting = setting.strip().lower()
        if setting in ['on', 'enable', 'enabled', 'true', '1']:
            enabled = True
            action = "enabled"
        elif setting in ['off', 'disable', 'disabled', 'false', '0']:
            enabled = False
            action = "disabled"
        else:
            await ctx.send(f"Invalid setting: **{setting}**. Use `on` or `off`.")
            logger.warning(f"Invalid thinking setting requested: {setting} in #{channel_name}")
            return

        # --- Apply setting ---
        was_changed = set_thinking_enabled(channel_id, enabled)

        if was_changed:
            # CRITICAL: "DeepSeek thinking display" required by realtime_settings_parser.py
            await ctx.send(f"DeepSeek thinking display **{action}** for #{channel_name}")
            logger.info(f"Thinking display {action} for #{channel_name} by {ctx.author.display_name}")
        else:
            await ctx.send(f"DeepSeek thinking display is already **{action}** in #{channel_name}")
            logger.debug(f"Thinking display setting unchanged for #{channel_name}: {action}")

    return {"thinking": thinking_cmd}
