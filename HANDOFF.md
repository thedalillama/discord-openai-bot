# HANDOFF.md
# Version 2.19.0
# Agent Development Handoff Document

## Current Status

**Branch**: development (in sync with main at v2.19.0)  
**Bot**: Running in production on GCP (synthergy-development-2)  
**State**: Stable — all tests passing

---

## Recent Work (This Session)

### v2.18.0 — Continuous Context Accumulation
Regular messages were not added to channel_history when auto-respond was
disabled. Bot now always listens and accumulates context regardless of
auto-respond state. When addressed directly after a silent period, the bot
has full awareness of the intervening conversation.

**File**: bot.py → v2.9.0

### v2.19.0 — Runtime History Noise Filtering
Bot confirmation messages, error messages, and settings persistence messages
were appearing in the API context. Fixed across three paths:

1. **Runtime**: add_response_to_history() filters noise before storing
2. **Load time**: discord_converter.py filters noise before storing bot messages
3. **API payload**: prepare_messages_for_api() filters is_history_output() and
   is_settings_persistence_message() — settings persistence messages stay in
   channel_history for the parser but never reach the AI

Error messages use a standard prefix (`I'm sorry an API error occurred when
attempting to respond: `) so users see them in Discord but they never enter
channel_history.

**Files**: response_handler.py → v1.1.1, message_processing.py → v2.2.5,
discord_converter.py → v1.0.1

---

## Pending Items (Todo)

### 1. Provider Singleton Caching (MEDIUM)
**Problem**: get_provider() in ai_providers/__init__.py creates a new provider
instance on every API call. The garbage collected httpx client causes a
reentrant stdout flush RuntimeError visible in production logs.
**Fix**: Cache provider instances as singletons keyed by provider name.
**File**: ai_providers/__init__.py
**Needs SOW**: Yes

### 2. README.md Pricing Table (LOW)
**Problem**: Pricing table is stale — OpenAI and Anthropic figures are outdated.
**Fix**: Update with current API pricing from provider docs.
**Needs SOW**: No — documentation only

### 3. Token-Based Context Trimming (MEDIUM)
**Problem**: MAX_HISTORY limits message count but not token count. A verbose
channel can exceed provider token limits even at low message counts.
**Fix**: Token estimation before API calls, trim to MAX_CONTEXT_TOKENS budget.
**Needs SOW**: Yes

---

## Architecture Notes

### Settings Persistence — How It Works
Settings (provider, system prompt, auto-respond, thinking) are persisted by
storing confirmation messages in Discord channel history. On restart, the
realtime_settings_parser reads these messages back and restores settings.

**Critical**: The following message patterns must never be filtered from
channel_history as they carry settings data:
- `"Auto-response is now **enabled/disabled**"`
- `"AI provider for #channel changed from X to Y"`
- `"AI provider for #channel reset from X to Y"`
- `"DeepSeek thinking display **enabled/disabled**"`
- `"System prompt updated for #channel"`

They ARE filtered from the API payload in prepare_messages_for_api() via
is_settings_persistence_message() so the AI never sees them.

### History Filtering — Three Layers
1. **discord_converter.py**: Filters noise at load time before storing
2. **response_handler.py**: Filters noise at runtime before storing
3. **message_processing.py prepare_messages_for_api()**: Filters settings
   persistence messages from API payload without removing from channel_history

### File Size Limit
250 lines mandatory. Check with `wc -l` or nano before committing.

---

## Development Process

- Always follow AGENT.md
- Get approval before any code changes
- Use development branch, merge to main after testing
- Two-branch strategy: development → main
- Separate commits per SOW
- All changed files need version bumps

---

## Key File Versions (current)

| File | Version |
|------|---------|
| bot.py | 2.9.0 |
| utils/response_handler.py | 1.1.1 |
| utils/history/message_processing.py | 2.2.5 |
| utils/history/discord_converter.py | 1.0.1 |
| utils/history/cleanup_coordinator.py | 2.2.0 |
| ai_providers/__init__.py | 1.2.0 |
| config.py | 1.5.0 |
