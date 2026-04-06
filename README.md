# README.md
# Version 5.9.0

# Synthergy Discord Bot

A multi-provider AI Discord bot with semantic conversational memory. Supports OpenAI, Anthropic, and DeepSeek providers with per-channel configuration, maintains structured summaries of conversations, and uses embedding-based retrieval to inject only the most relevant historical context at response time.

## Features

- **Multi-provider AI** — OpenAI (GPT), Anthropic (Claude), DeepSeek per channel
- **Semantic memory** — topic-based retrieval injects relevant past messages into every response; always-on context keeps overview, facts, actions, and questions available at all times
- **Structured summaries** — three-pass Secretary/Structurer/Classifier pipeline maintains living meeting minutes tracking decisions, action items, topics, and open questions
- **Token-budget context** — provider-aware context building ensures every API call fits within the context window; recent messages capped at 5 to avoid overwhelming retrieved context
- **Message persistence** — all messages stored in SQLite, surviving restarts without API refetch
- **Citation-backed responses** — when answering from retrieved history, bot cites specific messages inline with `[N]` notation and appends a Sources footer; hallucinated citations stripped automatically
- **Contextual embeddings** — every message embedded with 3-message conversational context prepended (v5.6.0); short replies and bot responses embed with their conversation, not in isolation
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
| `!summary create` | admin | Run full summarization (re-cluster + re-summarize) |
| `!summary update` | admin | Re-summarize only clusters updated since last run |
| `!summary clear` | admin | Delete stored summary and start fresh |
| `!debug noise` | admin | Scan for deletable bot noise in channel |
| `!debug cleanup` | admin | Delete bot noise from Discord history |
| `!debug status` | admin | Show summary internals (IDs, hashes, chains) |
| `!debug backfill` | admin | Embed unembedded messages with contextual text + re-link topics |
| `!debug reembed` | admin | Delete all embeddings + re-embed every message with context |
| `!debug dedup` | admin | Scan for duplicate test messages (3+ identical) |
| `!debug dedup confirm` | admin | Soft-delete duplicates, clean embeddings + clusters |
| `!debug clusters` | admin | Run UMAP + HDBSCAN clustering, show diagnostic report |
| `!debug summarize_clusters` | admin | Run per-cluster Gemini summarization, show results |
| `!explain` | all | Show context receipt for the last bot response |
| `!explain detail` | all | Receipt + injected messages per cluster |
| `!explain <id>` | all | Show context receipt for a specific response by message ID |
| `!explain detail <id>` | all | Detail view for a specific response |
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
├── schema/                        # SQLite migration files (001–005)
├── ai_providers/                  # Provider implementations
│   ├── openai_provider.py             # GPT + image generation
│   ├── anthropic_provider.py          # Claude models
│   ├── openai_compatible_provider.py  # DeepSeek + compatible APIs
│   └── gemini_provider.py            # Summarization only
├── commands/                      # Command modules
│   ├── summary_commands.py            # !summary group
│   ├── debug_commands.py              # !debug group (incl. backfill)
│   ├── auto_respond_commands.py       # !autorespond
│   ├── ai_provider_commands.py        # !ai
│   ├── thinking_commands.py           # !thinking
│   ├── prompt_commands.py             # !prompt
│   ├── status_commands.py             # !status
│   └── history_commands.py            # !history
└── utils/
    ├── cluster_engine.py              # UMAP + HDBSCAN pipeline, noise reduction
    ├── cluster_store.py               # Cluster CRUD, orchestration, dirty-cluster helpers
    ├── cluster_summarizer.py          # Per-cluster Gemini summarization, M-label formatting
    ├── cluster_overview.py            # Pipeline orchestrator, overview LLM, field translation
    ├── cluster_classifier.py          # GPT-4o-mini whitelist filter (classify_overview_items)
    ├── cluster_qa.py                  # Embedding dedup + answered-question removal
    ├── cluster_assign.py              # On-arrival centroid assignment (incremental, v5.4.0)
    ├── cluster_update.py              # Quick re-summarization of dirty clusters (v5.4.0)
    ├── embedding_store.py             # OpenAI embeddings, pack/unpack, message search
    ├── embedding_context.py           # Context-prepended embedding construction (v5.6.0)
    ├── context_retrieval.py           # Cluster retrieval + message fallback search (v5.6.0)
    ├── topic_store.py                 # Topic CRUD + message linking (v4.x rollback)
    ├── summarizer.py                  # Summarization router
    ├── summarizer_authoring.py        # Three-pass Secretary/Structurer/Classifier
    ├── summary_schema.py              # Schema, hashes, delta ops
    ├── summary_delta_schema.py        # anyOf discriminated union schema
    ├── summary_classifier.py          # GPT-4o-mini classifier (KEEP/DROP/RECLASSIFY)
    ├── summary_prompts.py             # Incremental delta prompt
    ├── summary_prompts_authoring.py   # Secretary + Structurer prompts
    ├── summary_display.py             # Paginated Discord output + always-on formatter
    ├── summary_store.py               # SQLite summary persistence
    ├── summary_normalization.py       # Response parsing + classification
    ├── summary_validation.py          # Domain validation
    ├── models.py                      # StoredMessage dataclass
    ├── message_store.py               # SQLite message persistence
    ├── raw_events.py                  # Real-time capture + embedding on arrival
    ├── context_manager.py             # Token budget, semantic retrieval, usage tracking
    ├── response_handler.py            # AI response processing
    └── history/                       # In-memory history subsystem
        ├── message_processing.py          # Noise filtering (prefix-based)
        ├── realtime_settings_parser.py    # Settings recovery
        └── ...
```

## Semantic Retrieval System (v4.1.x)

Every response is built from two context layers:

**Always-on** (injected for every message): overview, key facts, open action items, open questions.

**Retrieved** (per-query): the latest user message is embedded, the top matching topics are found by cosine similarity, and their linked messages are injected. Only topics scoring above `RETRIEVAL_MIN_SCORE` (default 0.25) are included. Bot-noise topics (self-descriptions, capability tests, etc.) are filtered before scoring. The token budget trimmer drops oldest recent messages to make room.

**Message fallback**: fires when no topics score above threshold, OR when matched topics have no linked messages. The query embedding searches `message_embeddings` directly and the top-N most similar messages are injected.

**Summary fallback**: if both topic and message search return empty (degraded state — no embeddings), the full summary is injected. Logs a WARNING.

**Timestamps**: every retrieved message is prefixed with `[YYYY-MM-DD]`. Today's date is injected at the top of the context block so the model can interpret message ages relative to now.

## Summarization System (v5.3.0 — cluster-based)

`!summary create` runs the full cluster pipeline via `summarizer.py` → `cluster_overview.py`:

1. **Cluster**: UMAP + HDBSCAN groups all message embeddings into topic clusters
2. **Per-cluster summarize**: single Gemini call per cluster → label, summary, decisions, key_facts, action_items, open_questions
3. **Classify**: GPT-4o-mini whitelist filter on aggregated items — keeps only project decisions, config, human-owned action items, user identity, channel purpose, genuine open questions; missing verdicts default to DROP
4. **Overview**: Gemini call with cluster labels + summary texts only → channel overview paragraph + participants list (no structured fields — prevents token blowup)
5. **Deduplicate**: embedding cosine similarity (0.85 threshold) drops near-duplicate items across all four arrays
6. **Answered-question check**: GPT-4o-mini YES/NO per open question vs decisions + key facts in the same summary; removes answered questions
7. **Translate + save**: field names mapped to v4.x format (`text` → `fact`/`task`/`question`/`decision`) and stored in `channel_summaries`

The v4.x three-pass Secretary/Structurer/Classifier pipeline (`summarizer_authoring.py`) is retained but no longer called — rollback safety only.

**Key design choices:**
- Classifier runs before overview LLM — prevents 16K+ token response with 50+ clusters
- Overview receives labels + texts only — output is a few hundred tokens max
- Embedding dedup over LLM dedup — LLMs are reluctant to delete content they're given
- Decision = agreement on a course of action (not fact lookups or casual preferences)
- Field translation at storage time — display layer (`format_always_on_context`) unchanged

## Configuration

See `README_ENV.md` for the complete environment variable reference.

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token (required) | — |
| `AI_PROVIDER` | Default conversation provider | `deepseek` |
| `OPENAI_API_KEY` | Required for embeddings + classifier | — |
| `SUMMARIZER_PROVIDER` | Summarization provider | `gemini` |
| `GEMINI_API_KEY` | Required for summarization | — |
| `DATABASE_PATH` | SQLite database location | `./data/messages.db` |
| `CONTEXT_BUDGET_PERCENT` | % of context window for input | `80` |
| `MAX_RECENT_MESSAGES` | Recent messages included in context | `5` |
| `EMBEDDING_MODEL` | OpenAI embedding model | `text-embedding-3-small` |
| `RETRIEVAL_MIN_SCORE` | Min cosine similarity for cluster retrieval | `0.25` (production: `0.45`) |
| `TOPIC_LINK_MIN_SCORE` | Min cosine similarity for topic-message linking | `0.3` |
| `RETRIEVAL_TOP_K` | Max topics retrieved per query | `5` |
| `RETRIEVAL_MSG_FALLBACK` | Max messages returned by direct fallback search | `15` |

## Deployment

The bot runs as a systemd service (`discord-bot`) on a GCP VM:

```bash
sudo systemctl restart discord-bot    # restart
sudo journalctl -u discord-bot -f     # follow logs
sudo journalctl --rotate && sudo journalctl --vacuum-time=1s  # clear logs
```

After first deploy or embedding strategy change (v5.6.0+):
```bash
# In Discord:
!debug reembed       # delete all embeddings + re-embed with contextual text
!summary create      # rebuild clusters from contextual embeddings
```

Incremental backfill (embed only missing messages):
```bash
!debug backfill      # embed unembedded messages with context + re-link topics
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
