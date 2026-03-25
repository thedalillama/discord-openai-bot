# commands/ai_provider_commands.py
# Version 2.1.0
"""
AI provider management command for the Discord bot.

CHANGES v2.1.0: ℹ️/⚙️ prefix tagging for noise filtering
- Settings changes prefixed with ⚙️ (persist for replay)
- Status/error output prefixed with ℹ️ (filter everywhere)

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CREATED v1.0.0: Initial implementation

Usage:
  !ai              - Show current AI provider (all users)
  !ai <provider>   - Switch AI provider (admin only)
  !ai reset        - Reset to default provider (admin only)
"""
from utils.history import get_ai_provider, set_ai_provider, remove_ai_provider, channel_ai_providers
from utils.logging_utils import get_logger

logger = get_logger('commands.ai_provider')

_I = "ℹ️ "
_S = "⚙️ "

VALID_PROVIDERS = ['openai', 'anthropic', 'deepseek']


def get_provider_backend_info(provider_name, channel_id=None):
    """Get provider display name with backend info."""
    return provider_name


def register_ai_provider_commands(bot):

    @bot.command(name='ai')
    async def ai_cmd(ctx, *, arg=None):
        """Manage the AI provider for this channel."""
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        if arg is None:
            from config import AI_PROVIDER
            current = get_ai_provider(channel_id)
            provider_display = current or AI_PROVIDER
            backend = get_provider_backend_info(provider_display, channel_id)
            if current is None:
                await ctx.send(
                    f"{_I}Current AI provider for #{channel_name}: **{backend}** (default)\n"
                    f"Available providers: {', '.join(VALID_PROVIDERS)}")
            else:
                await ctx.send(
                    f"{_I}Current AI provider for #{channel_name}: **{backend}**\n"
                    f"Available providers: {', '.join(VALID_PROVIDERS)}")
            return

        if not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{_I}You need administrator permissions to change this setting.")
            return

        arg = arg.strip().lower()

        if arg == 'reset':
            from config import AI_PROVIDER
            if channel_id not in channel_ai_providers:
                await ctx.send(
                    f"{_I}AI provider for #{channel_name} is already using the default (**{AI_PROVIDER}**).")
                return
            current_provider = get_ai_provider(channel_id)
            remove_ai_provider(channel_id)
            await ctx.send(
                f"{_S}AI provider for #{channel_name} reset from **{current_provider}** to default (**{AI_PROVIDER}**).")
            logger.info(f"AI provider reset for #{channel_name}")
            return

        if arg not in VALID_PROVIDERS:
            await ctx.send(
                f"{_I}Invalid AI provider: **{arg}**. Valid options: {', '.join(VALID_PROVIDERS)}")
            return

        from config import AI_PROVIDER
        current_provider = get_ai_provider(channel_id)
        effective_current = current_provider if current_provider else AI_PROVIDER

        if effective_current == arg:
            await ctx.send(f"{_I}AI provider for #{channel_name} is already set to **{arg}**.")
            return

        set_ai_provider(channel_id, arg)
        await ctx.send(
            f"{_S}AI provider for #{channel_name} changed from **{effective_current}** to **{arg}**.")
        logger.info(f"AI provider changed for #{channel_name}: {effective_current} → {arg}")

    return {"ai": ai_cmd}
