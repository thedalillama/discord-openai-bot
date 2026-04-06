# commands/__init__.py
# Version 2.6.0
"""
Commands package initialization.
Registers all command modules with the bot.

CHANGES v2.6.0: Register explain_commands (SOW v5.7.0)
- ADDED: register_explain_commands — !explain command

CHANGES v2.5.0: Add cluster_commands registration (SOW v5.6.0)
- ADDED: register_cluster_commands — adds !debug backfill/reembed/clusters/
  summarize_clusters as subcommands of the !debug group returned by
  register_debug_commands()

CHANGES v2.4.0: Replace !cleanup with !debug command group
CHANGES v2.3.0: Cleanup command + prefix tagging
CHANGES v2.2.0: Summary command group restructure
CHANGES v2.1.0: Summary commands (SOW v3.2.0)
CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
CHANGES v1.1.0: Added status command module
"""
from .history_commands import register_history_commands
from .auto_respond_commands import register_auto_respond_commands
from .prompt_commands import register_prompt_commands
from .ai_provider_commands import register_ai_provider_commands
from .thinking_commands import register_thinking_commands
from .status_commands import register_status_commands
from .summary_commands import register_summary_commands
from .debug_commands import register_debug_commands
from .cluster_commands import register_cluster_commands
from .explain_commands import register_explain_commands


def register_commands(bot, auto_respond_channels):
    """Register all commands with the bot"""
    register_history_commands(bot)
    register_auto_respond_commands(bot, auto_respond_channels)
    register_prompt_commands(bot)
    register_ai_provider_commands(bot)
    register_thinking_commands(bot)
    register_status_commands(bot, auto_respond_channels)
    register_summary_commands(bot)
    debug_cmd = register_debug_commands(bot)
    register_cluster_commands(debug_cmd)
    register_explain_commands(bot)
