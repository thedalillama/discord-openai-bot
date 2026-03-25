# commands/status_commands.py
# Version 2.1.0
"""
Bot status display command.

CHANGES v2.1.0: ℹ️ prefix tagging for noise filtering
- All output prefixed with ℹ️

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CREATED v1.0.0: Initial implementation

Usage:
  !status    - Show bot status for this channel (all users)
"""
from utils.history import get_system_prompt, get_ai_provider
from config import DEFAULT_SYSTEM_PROMPT, AI_PROVIDER
from utils.logging_utils import get_logger

logger = get_logger('commands.status')

_I = "ℹ️ "


def _get_thinking_status(channel_id):
    """Get thinking display status string."""
    try:
        from utils.history import get_thinking_enabled
        return "enabled" if get_thinking_enabled(channel_id) else "disabled"
    except Exception:
        return "unknown"


def get_provider_backend_info(provider_name, channel_id=None):
    """Get provider display name with backend info."""
    return provider_name


def register_status_commands(bot, auto_respond_channels):

    @bot.command(name='status')
    async def status_cmd(ctx):
        """Show bot status for this channel."""
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        try:
            lines = [f"**Bot Status for #{channel_name}**", ""]

            current_prompt = get_system_prompt(channel_id)
            if current_prompt == DEFAULT_SYSTEM_PROMPT:
                lines.append("**System Prompt:** Default")
            else:
                lines.append("**System Prompt:** Custom")
            lines.append(f"```{current_prompt}```")
            lines.append("")

            current_provider = get_ai_provider(channel_id)
            provider_display = current_provider or AI_PROVIDER
            backend = get_provider_backend_info(provider_display, channel_id)
            if current_provider is None:
                lines.append(f"**AI Provider:** {backend} (default)")
            else:
                lines.append(f"**AI Provider:** {backend}")

            auto_status = "enabled" if channel_id in auto_respond_channels else "disabled"
            lines.append(f"**Auto-Response:** {auto_status}")

            thinking_status = _get_thinking_status(channel_id)
            lines.append(f"**Thinking Display:** {thinking_status}")

            await ctx.send(f"{_I}" + "\n".join(lines))

        except Exception as e:
            logger.error(f"Error generating status: {e}")
            await ctx.send(f"{_I}Error retrieving status for #{channel_name}.")

    return {"status": status_cmd}
