# commands/__init__.py
# Version 2.0.0
"""
Commands package initialization.
Registers all command modules with the bot.

CHANGES v2.0.0: Command interface redesign (SOW v2.13.0)
- REDESIGNED: !prompt replaces !setprompt, !getprompt, !resetprompt
- REDESIGNED: !ai replaces !setai, !getai, !resetai
- REDESIGNED: !autorespond - fixed permissions, removed !autostatus and !autosetup
- REDESIGNED: !thinking - fixed permissions, removed !thinkingstatus
- REDESIGNED: !history - merged !cleanhistory and !loadhistory as subcommands
- RESULT: 15 commands consolidated into 6 unified base commands
- MAINTAINED: All module filenames and registration calls unchanged

CHANGES v1.1.0: Added status command module
- ADDED: register_status_commands for !status command
- MAINTAINED: All existing command registrations
"""
from .history_commands import register_history_commands
from .auto_respond_commands import register_auto_respond_commands
from .prompt_commands import register_prompt_commands
from .ai_provider_commands import register_ai_provider_commands
from .thinking_commands import register_thinking_commands
from .status_commands import register_status_commands

def register_commands(bot, auto_respond_channels):
    """Register all commands with the bot"""
    register_history_commands(bot)
    register_auto_respond_commands(bot, auto_respond_channels)
    register_prompt_commands(bot)
    register_ai_provider_commands(bot)
    register_thinking_commands(bot)
    register_status_commands(bot, auto_respond_channels)
