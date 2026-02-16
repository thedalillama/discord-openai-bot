# commands/ai_provider_commands.py
# Version 2.0.0
"""
AI provider management command for the Discord bot.

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REPLACED: !setai, !getai, !resetai with single unified !ai command
- ADDED: No-arg path shows current provider + available providers (all users)
- ADDED: Value arg sets provider (admin only, manual permission check)
- ADDED: 'reset' arg resets to default (admin only, with already-at-default check)
- PRESERVED: Exact confirmation message strings required by realtime_settings_parser

Usage:
  !ai              - Show current AI provider and available options (all users)
  !ai <provider>   - Set AI provider: openai, anthropic, deepseek (admin only)
  !ai reset        - Reset to default provider (admin only)
"""
from utils.history import (
    get_ai_provider, set_ai_provider, remove_ai_provider, channel_ai_providers
)
from utils.logging_utils import get_logger

logger = get_logger('commands.ai_provider')

VALID_PROVIDERS = ['openai', 'anthropic', 'deepseek']

def register_ai_provider_commands(bot):
    """Register AI provider management command with the bot"""

    @bot.command(name='ai')
    async def ai_cmd(ctx, arg=None):
        """
        Manage the AI provider for this channel.

        Usage:
          !ai              - Show current provider and available options (all users)
          !ai <provider>   - Set AI provider (🔒 admin only)
          !ai reset        - Reset to default provider (🔒 admin only)

        Valid providers: openai, anthropic, deepseek

        Args:
            arg: None to show status, 'reset' to reset, or provider name to set
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        # --- No-arg: show current provider + available list (all users) ---
        if arg is None:
            from config import AI_PROVIDER
            channel_provider = get_ai_provider(channel_id)

            if channel_provider is None:
                provider = AI_PROVIDER
                source = "default"
            else:
                provider = channel_provider
                source = "channel setting"

            logger.debug(f"AI provider requested for #{channel_name} by {ctx.author.display_name}")
            await ctx.send(
                f"AI provider for #{channel_name}: **{provider}** ({source})\n"
                f"Available providers: {', '.join(VALID_PROVIDERS)}"
            )
            return

        # --- Write operations: admin only ---
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to change this setting.")
            logger.warning(f"Unauthorized AI provider change attempt by {ctx.author.display_name} in #{channel_name}")
            return

        arg = arg.strip().lower()

        # --- 'reset': restore default provider ---
        if arg == 'reset':
            from config import AI_PROVIDER
            logger.info(f"AI provider reset requested for #{channel_name} by {ctx.author.display_name}")

            # Check if already at default
            if channel_id not in channel_ai_providers:
                await ctx.send(f"AI provider for #{channel_name} is already using the default (**{AI_PROVIDER}**).")
                logger.debug(f"AI provider already at default for #{channel_name}")
                return

            # Get current before removing
            current_provider = get_ai_provider(channel_id)

            # Remove channel-specific setting
            remove_ai_provider(channel_id)

            # CRITICAL: "AI provider for" and " to " required by realtime_settings_parser.py
            await ctx.send(f"AI provider for #{channel_name} reset from **{current_provider}** to default (**{AI_PROVIDER}**).")
            logger.info(f"AI provider for #{channel_name} reset from {current_provider} to default ({AI_PROVIDER})")
            return

        # --- Validate provider name ---
        if arg not in VALID_PROVIDERS:
            await ctx.send(f"Invalid AI provider: **{arg}**. Valid options: {', '.join(VALID_PROVIDERS)}")
            logger.warning(f"Invalid AI provider requested: {arg} in #{channel_name}")
            return

        # --- Set new provider ---
        from config import AI_PROVIDER
        current_provider = get_ai_provider(channel_id)

        # Resolve effective current provider for comparison and confirmation message
        if current_provider is None:
            effective_current = AI_PROVIDER
        else:
            effective_current = current_provider

        if effective_current == arg:
            await ctx.send(f"AI provider for #{channel_name} is already set to **{arg}**.")
            logger.debug(f"AI provider unchanged for #{channel_name}: {arg}")
            return

        set_ai_provider(channel_id, arg)

        # CRITICAL: "AI provider for" and " to " required by realtime_settings_parser.py
        await ctx.send(f"AI provider for #{channel_name} changed from **{effective_current}** to **{arg}**.")
        logger.info(f"AI provider for #{channel_name} changed from {effective_current} to {arg}")

    return {"ai": ai_cmd}
