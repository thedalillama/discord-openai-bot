# README.md
# Version 3.3.2

# Synthergy Discord Bot

A multi-provider AI Discord bot with structured conversational memory. Supports OpenAI, Anthropic, and DeepSeek providers with per-channel configuration, and maintains durable meeting-minutes-style summaries of conversations using Gemini.

## Features

- **Multi-provider AI** — OpenAI (GPT), Anthropic (Claude), DeepSeek per channel
- **Conversational memory** — structured summaries track decisions, action items, topics, and open questions across conversations of any length
- **Token-budget context** — provider-aware context building ensures every API call fits within the context window
- **Message persistence** — all messages stored in SQLite, surviving restarts without API refetch
- **Per-channel settings** — AI provider, system prompt, auto-response, and thinking display configurable per channel
- **Settings recovery** — settings restored from Discord message history on startup

## Quick Start

```bash
# Clone and install
git clone https://github.com/thedalillama/synthergy.git
cd synthergy/bot/src/discord-bot
pip install -r requirements.txt

# Configure (see README_ENV.md for all variables)
cp .env.example .env
# Edit .env with your tokens

# Run
python main.py
```

## Commands

| Command | Access | Description |
|---------|--------|-------------|
| `!summary` | all | Show channel summary (decisions, topics, actions) |
| `!summary full` | all | All sections including facts and archived topics |
| `!summary raw` | all | Secretary's natural language minutes |
| `!summary create` | admin | Run summarization on new messages |
| `!summary clear` | admin | Delete stored summary and start fresh |
| `!debug noise` | admin | Scan for deletable bot noise in channel |
| `!debug cleanup` | admin | Delete bot noise from Discord history |
| `!debug status` | admin | Show summary internals (IDs, hashes, chains) |
| `!status` | all | Show bot settings for this channel |
| `!autorespond on/off` | admin | Toggle auto-response |
| `!ai [provider]` | admin | Switch AI provider (openai/anthropic/deepseek) |
| `!thinking on/off` | admin | Toggle DeepSeek reasoning display |
| `!prompt [text]` | admin | Set/view/reset system prompt |
| `!history [count]` | all | View conversation history |
| `!history clean` | all | Remove command noise from history |
| `!history reload` | all | Reload history from Discord |

## Architecture

```
discord-bot/
├── main.py                        # Entry point
├── bot.py                         # Discord events, message routing
├── config.py                      # Environment configuration
├── schema/                        # SQLite migration files
├── ai_providers/                  # Provider implementations
│   ├── openai_provider.py             # GPT + image generation
│   ├── anthropic_provider.py          # Claude models
│   ├── openai_compatible_provider.py  # DeepSeek + compatible APIs
│   └── gemini_provider.py            # Summarization only
├── commands/                      # Command modules
│   ├── summary_commands.py            # !summary group
│   ├── debug_commands.py              # !debug group
│   ├── auto_respond_commands.py       # !autorespond
│   ├── ai_provider_commands.py        # !ai
│   ├── thinking_commands.py           # !thinking
│   ├── prompt_commands.py             # !prompt
│   ├── status_commands.py             # !status
│   └── history_commands.py            # !history
└── utils/
    ├── summarizer.py                  # Summarization router
    ├── summarizer_authoring.py        # Cold start Secretary pipeline
    ├── summary_schema.py              # Schema, hashes, delta ops
    ├── summary_prompts.py             # Incremental delta prompt
    ├── summary_prompts_authoring.py   # Secretary + Structurer prompts
    ├── summary_display.py             # Paginated Discord output
    ├── summary_store.py               # SQLite summary persistence
    ├── summary_normalization.py       # Response parsing + classification
    ├── summary_validation.py          # Domain validation
    ├── models.py                      # StoredMessage dataclass
    ├── message_store.py               # SQLite message persistence
    ├── raw_events.py                  # Real-time capture + backfill
    ├── context_manager.py             # Token budget + usage tracking
    ├── response_handler.py            # AI response processing
    └── history/                       # In-memory history subsystem
        ├── message_processing.py          # Noise filtering (prefix-based)
        ├── realtime_settings_parser.py    # Settings recovery
        └── ...
```

## Summarization System

The bot maintains "living meeting minutes" for each channel — a structured summary that tracks decisions, action items, topics, and open questions.

**Cold start** (no prior summary): all messages sent to a "Secretary" AI that writes natural language minutes, then a "Structurer" converts them to JSON.

**Incremental updates**: new messages processed as delta operations against the existing summary using Gemini Structured Outputs.

**Key design choices:**
- Decision = agreement on a course of action (not fact lookups)
- Fresh-from-source summarization (no recursive summary-of-summary)
- Hash-protected fields with supersession lifecycle
- Prefix-based noise filtering (ℹ️/⚙️) replaces pattern matching

## Configuration

See `README_ENV.md` for the complete environment variable reference.

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token (required) | — |
| `AI_PROVIDER` | Default conversation provider | `deepseek` |
| `SUMMARIZER_PROVIDER` | Summarization provider | `gemini` |
| `SUMMARIZER_MODEL` | Gemini model for summaries | `gemini-3.1-flash-lite-preview` |
| `DATABASE_PATH` | SQLite database location | `./data/messages.db` |
| `CONTEXT_BUDGET_PERCENT` | % of context window for input | `80` |

## Deployment

The bot runs as a systemd service (`discord-bot`) on a GCP VM:

```bash
sudo systemctl restart discord-bot    # restart
sudo journalctl -u discord-bot -f     # follow logs
```

## Documentation

| File | Purpose |
|------|---------|
| `STATUS.md` | Version history and current state |
| `HANDOFF.md` | Architecture details and handoff context |
| `AGENT.md` | Development rules for AI agents |
| `CLAUDE.md` | Claude Code-specific guidance |
| `README_ENV.md` | Environment variable reference |
| `docs/sow/` | Design documents (SOWs) |
