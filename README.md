# README.md
# Version 3.0.0
# Discord AI Bot

A Discord bot that integrates with multiple AI providers (OpenAI, Anthropic,
DeepSeek) to provide intelligent responses and brainstorming support in
Discord channels.

## Quick Start

1. **Clone and install dependencies**:
   ```bash
   git clone <repository>
   cd discord-ai-bot
   pip install -r requirements.txt
   ```

2. **Configure environment** (create `.env` file):
   ```bash
   # Required
   DISCORD_TOKEN=your_discord_bot_token

   # Choose your AI provider
   AI_PROVIDER=deepseek
   OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
   OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
   OPENAI_COMPATIBLE_MODEL=deepseek-chat
   ```

3. **Run the bot**:
   ```bash
   python main.py
   ```

---

## AI Providers

### DeepSeek (Recommended — Cost-Effective)
```bash
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat        # Fast, cost-effective
# OPENAI_COMPATIBLE_MODEL=deepseek-reasoner  # Reasoning model with CoT display
```

**DeepSeek models:**
- `deepseek-chat` — General purpose, fast responses, lowest cost
- `deepseek-reasoner` — Chain-of-thought reasoning model; use with
  `!thinking on` to display full reasoning process in Discord

### OpenAI (GPT Models + Image Generation)
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
ENABLE_IMAGE_GENERATION=true
```

### Anthropic (Claude Models)
```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

### Other OpenAI-Compatible Providers
```bash
# OpenRouter
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1

# Local APIs (Ollama, LM Studio, etc.)
OPENAI_COMPATIBLE_BASE_URL=http://localhost:8000
```

### Provider Specifications (verified 2025-02-26)
| Provider | Model | Context Window | Max Output | Cost per 1M tokens |
|----------|-------|---------------|------------|---------------------|
| OpenAI | gpt-4o-mini | 128K | 16,384 | ~$0.15 input / $0.60 output |
| DeepSeek | deepseek-chat | 64K | 8,000 | ~$0.27 input / $1.10 output |
| DeepSeek | deepseek-reasoner | 64K | 8,000 (+32K CoT) | ~$0.55 input / $2.19 output |
| Anthropic | claude-haiku-4-5 | 200K | 64,000 | ~$0.80 input / $4.00 output |

*Prices approximate — check provider docs for current rates.*

---

## Context Management

The bot uses a two-layer context management system to ensure every API call
fits within the provider's context window:

1. **Message-count trim** (`MAX_HISTORY`, default 10) — bounds in-memory
   storage after every message append
2. **Token-budget trim** (`CONTEXT_BUDGET_PERCENT`, default 80%) — at API
   call time, ensures total tokens fit within the provider's context window

The token budget uses `tiktoken` for accurate token counting. The budget
formula is: `input_budget = (context_window × 80%) − max_output_tokens`.

Increase `MAX_HISTORY` (e.g., 50) to let the token budget be the
primary decision-maker for which messages go to the API.

### Token Usage Logging
Every API call logs actual token consumption (input + output) at INFO level,
extracted from each provider's response metadata — not estimates. Per-channel
cumulative totals are tracked in memory and logged at DEBUG. This provides a
cost baseline for comparing context management techniques.

Set `LOG_LEVEL=DEBUG` to see full token budget and usage details on every call.

### Message Persistence (v3.0.0)
All messages are stored in a local SQLite database (`./data/messages.db`)
in real-time as they arrive via Discord Gateway events. This includes both
user messages and bot responses. The database:

- **Survives restarts** — no need to refetch from Discord API on startup
- **Tracks edits and deletions** — edits update content, deletes are soft
  (flagged, not removed) to preserve conversational context
- **Enables summarization** — the complete message history is available for
  the planned fresh-from-source summarization subsystem (v3.1.0)
- **Startup backfill** — on restart, fetches only messages missed while the
  bot was offline (up to 10,000 per channel)

The database uses WAL mode for concurrent read/write safety and requires
no external dependencies (Python's built-in `sqlite3` module).

---

## Commands

🔒 = Administrator permission required

### `!prompt` — System Prompt
| Usage | Description | Permission |
|-------|-------------|------------|
| `!prompt` | Show current system prompt | All users |
| `!prompt <text>` | Set new system prompt | 🔒 Admin |
| `!prompt reset` | Reset to default prompt | 🔒 Admin |

### `!ai` — AI Provider
| Usage | Description | Permission |
|-------|-------------|------------|
| `!ai` | Show current provider and available options | All users |
| `!ai <provider>` | Set provider: `openai`, `anthropic`, `deepseek` | 🔒 Admin |
| `!ai reset` | Reset to default provider | 🔒 Admin |

### `!autorespond` — Auto-Response
| Usage | Description | Permission |
|-------|-------------|------------|
| `!autorespond` | Show current status and options | All users |
| `!autorespond on` | Enable auto-response to all messages | 🔒 Admin |
| `!autorespond off` | Disable auto-response | 🔒 Admin |

### `!thinking` — DeepSeek Reasoning Display
| Usage | Description | Permission |
|-------|-------------|------------|
| `!thinking` | Show current status and options | All users |
| `!thinking on` | Display full reasoning in Discord + log at INFO | 🔒 Admin |
| `!thinking off` | Answer only in Discord, reasoning logged at DEBUG | 🔒 Admin |

**Notes:**
- Only applies to `deepseek-reasoner` model which returns `reasoning_content`
- Reasoning content is always logged (INFO when on, DEBUG when off)
- Reasoning never stored in conversation history or sent to API
- Displayed as a separate message before the answer, prefixed with
  `[DEEPSEEK_REASONING]:`

### `!history` — History Management
| Usage | Description | Permission |
|-------|-------------|------------|
| `!history` | Display recent history (last 25 messages) | 🔒 Admin |
| `!history <count>` | Display N most recent messages | 🔒 Admin |
| `!history clean` | Remove commands/artifacts from history | 🔒 Admin |
| `!history reload` | Reload history from Discord | 🔒 Admin |

### `!status` — Channel Overview
| Usage | Description | Permission |
|-------|-------------|------------|
| `!status` | Show all current channel settings | All users |

### Direct Provider Addressing
Address a specific provider without changing channel defaults:
```
openai, draw a picture of a sunset
anthropic, explain quantum physics
deepseek, solve this math problem
```

---

## Configuration

See [README_ENV.md](README_ENV.md) for comprehensive environment variable
documentation.

---

## Architecture

```
├── main.py                    # Entry point
├── bot.py                     # Core Discord events, message routing
├── config.py                  # Environment variable configuration
├── commands/                  # Modular command system (6 commands)
├── ai_providers/              # Provider implementations + factory
│   ├── openai_provider.py         # GPT models + image generation
│   ├── anthropic_provider.py      # Claude models
│   └── openai_compatible_provider.py  # DeepSeek + any compatible API
└── utils/
    ├── models.py                  # StoredMessage dataclass
    ├── message_store.py           # SQLite persistence layer
    ├── raw_events.py              # Real-time message capture + backfill
    ├── context_manager.py         # Token budget + usage accumulator
    ├── response_handler.py        # AI response processing + Discord delivery
    ├── provider_utils.py          # Provider override parsing
    └── history/                   # History management subsystem
        ├── message_processing.py      # Noise filtering + API payload builder
        ├── cleanup_coordinator.py     # Post-load trim and cleanup
        ├── realtime_settings_parser.py # Settings recovery from Discord history
        └── ...                        # Loading, storage, diagnostics
```

### Key Patterns
- **Provider singleton caching** — each provider instantiated once, reused
- **Async executor wrapping** — all synchronous API calls in thread pool
- **Three-layer noise filtering** — runtime, load-time, and API payload
- **Token-budget context building** — provider-aware, percentage-based
- **Token usage tracking** — actual API usage logged per-call and accumulated
- **Settings persistence** — parsed from Discord message history on startup
- **SQLite message persistence** — all messages stored durably via on_message listener
