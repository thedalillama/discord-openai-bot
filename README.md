# README.md
# Version 7.3.0

# Synthergy Discord Bot

A multi-provider AI Discord bot with semantic conversational memory. Supports OpenAI, Anthropic, and DeepSeek providers with per-channel configuration, maintains structured summaries of conversations, and uses embedding-based retrieval to inject only the most relevant historical context at response time.

## Features

- **Multi-provider AI** — OpenAI (GPT), Anthropic (Claude), DeepSeek per channel
- **Semantic memory** — segment-based hybrid retrieval (BM25 + dense + RRF) injects relevant past messages into every response; always-on context keeps overview, facts, actions, and questions available at all times
- **Structured summaries** — segment+cluster pipeline (Gemini segmentation → UMAP/HDBSCAN → per-cluster summarization → classify → overview) produces living meeting minutes tracking decisions, action items, topics, and open questions
- **Background pipeline worker** — asyncio task polls every 30s, incrementally segments new messages, embeds, decomposes propositions, and rebuilds FTS index without manual intervention
- **Three-layer context** — Layer 1 (system + always-on summary), Layer 2 (session bridge + unsummarized messages, budget-guaranteed), Layer 3 (RRF retrieval); recent conversation never trimmed by old history
- **Message persistence** — all messages stored in SQLite; on restart, backfill fetches only messages newer than the last stored ID; in-memory history seeded from DB without a full Discord history pull
- **Citation-backed responses** — when answering from retrieved history, bot cites specific messages inline with `[N]` notation and appends a Sources footer; hallucinated citations stripped automatically
- **Contextual embeddings** — every message embedded with 3-message conversational context prepended (v5.6.0); short replies and bot responses embed with their conversation, not in isolation
- **Per-channel settings** — AI provider, system prompt, auto-response, and thinking display configurable per channel
- **Settings recovery** — settings restored from SQLite on startup (⚙️ bot messages); Discord fetched delta-only after last DB message ID

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
| `!summary full` | all | All sections including key facts |
| `!summary create` | admin | Run full summarization (re-cluster + re-summarize) |
| `!summary update` | admin | Re-summarize only clusters updated since last run |
| `!summary clear` | admin | Delete stored summary and start fresh |
| `!debug noise` | admin | Scan for deletable bot noise in channel |
| `!debug cleanup` | admin | Delete bot noise from Discord history |
| `!debug status` | admin | Show summary internals (IDs, hashes, chains) |
| `!debug backfill` | admin | Embed unembedded messages with contextual text |
| `!debug reembed` | admin | Delete all embeddings + re-embed every message with context |
| `!debug dedup` | admin | Scan for duplicate test messages (3+ identical) |
| `!debug dedup confirm` | admin | Soft-delete duplicates, clean embeddings + clusters |
| `!debug segments` | admin | Show segment count, avg size, sample syntheses |
| `!debug propositions` | admin | Show proposition count and samples |
| `!pipeline status` | admin | Show worker state, lock holder, unsegmented count, last run |
| `!pipeline stop` | admin | Stop the background pipeline worker |
| `!pipeline start` | admin | Start the background pipeline worker |
| `!pipeline run` | admin | Run one manual pipeline cycle immediately |
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
├── schema/                        # SQLite migration files (001–009)
├── ai_providers/                  # Provider implementations
│   ├── openai_provider.py             # GPT + image generation
│   ├── anthropic_provider.py          # Claude models
│   ├── openai_compatible_provider.py  # DeepSeek + compatible APIs
│   └── gemini_provider.py            # Summarization only
├── commands/                      # Command modules
│   ├── summary_commands.py            # !summary group
│   ├── debug_commands.py              # !debug group (incl. backfill)
│   ├── pipeline_commands.py           # !pipeline group (v7.3.0)
│   ├── auto_respond_commands.py       # !autorespond
│   ├── ai_provider_commands.py        # !ai
│   ├── thinking_commands.py           # !thinking
│   ├── prompt_commands.py             # !prompt
│   ├── status_commands.py             # !status
│   └── history_commands.py            # !history
└── utils/
    ├── segment_store.py               # Segment CRUD + run_segment_clustering (v6.0.0)
    ├── segmenter.py                   # Gemini segmentation+synthesis, batch with overlap (v6.0.0)
    ├── cluster_engine.py              # UMAP + HDBSCAN pipeline, noise reduction
    ├── cluster_store.py               # Cluster CRUD, orchestration, dirty-cluster helpers
    ├── cluster_summarizer.py          # Per-cluster Gemini summarization, M-label formatting
    ├── cluster_overview.py            # Pipeline orchestrator, overview LLM, field translation
    ├── cluster_classifier.py          # GPT-4o-mini whitelist filter (classify_overview_items)
    ├── cluster_qa.py                  # Embedding dedup + answered-question removal
    ├── pipeline_worker.py             # Background pipeline worker + lock (v7.3.0)
    ├── incremental_segmenter.py       # Incremental segment + extend logic (v7.3.0)
    ├── cluster_assign.py              # On-arrival centroid assignment (incremental, v5.4.0)
    ├── cluster_update.py              # Quick re-summarization of dirty clusters (v5.4.0)
    ├── embedding_store.py             # OpenAI embeddings, pack/unpack, message search
    ├── embedding_noise_filter.py      # Embedding skip gate: thin msgs, deleted placeholders (v5.13.0)
    ├── embedding_context.py           # Context-prepended embedding construction (v5.6.0)
    ├── fts_search.py                  # FTS5 BM25 search + RRF fusion (v6.2.0)
    ├── context_retrieval.py           # Hybrid segment retrieval + fallback (v6.2.0)
    ├── proposition_store.py           # Proposition CRUD + embedding storage (v6.4.0)
    ├── proposition_decomposer.py      # GPT-4o-mini atomic claim decomposition (v6.4.0)
    ├── summarizer.py                  # Summarization router (v4.0.0)
    ├── summary_display.py             # Paginated Discord output + always-on formatter
    ├── summary_store.py               # SQLite summary persistence
    ├── models.py                      # StoredMessage dataclass
    ├── message_store.py               # SQLite message persistence (thread-local connections)
    ├── raw_events.py                  # Real-time capture + embedding on arrival
    ├── context_manager.py             # Token budget, semantic retrieval, usage tracking
    ├── response_handler.py            # AI response processing
    └── history/                       # In-memory history subsystem
        ├── discord_loader.py              # Coordination: DB seed + delta Discord fetch
        ├── discord_fetcher.py             # Discord API fetch (delta-only via after_id)
        ├── realtime_settings_parser.py    # Settings recovery from SQLite + Discord
        ├── message_processing.py          # Noise filtering (prefix-based)
        └── ...
```

## Semantic Retrieval (v6.4.0 — three-signal proposition+dense+BM25+RRF)

Every response is built from two context layers:

**Always-on** (injected for every message): overview, key facts, open action items, open questions.

**Retrieved** (per-query): three-signal hybrid retrieval fused via Reciprocal Rank Fusion:
1. Query embedded via `embed_query_with_smart_context()` — adds conversational context to avoid topic bleed
2. Propositions: `find_relevant_propositions()` scores query against atomic claim embeddings; collapses to max-score-per-segment → segment IDs
3. Dense: `find_relevant_segments()` scores query against all segment embeddings (top_k × 2 expanded pool, `RETRIEVAL_FLOOR` minimum)
4. Score-gap: `_apply_score_gap()` cuts dense candidates at largest inter-score gap ≥ `RETRIEVAL_SCORE_GAP`
5. BM25: `fts_search()` via SQLite FTS5 — matches synthesis + raw message content
6. RRF: `rrf_fuse(prop, dense, bm25, k=RRF_K)` — rank-based fusion, returns top-`RETRIEVAL_TOP_K` fused IDs
7. Per segment: synthesis + source messages injected as `[Topic: label]\nSummary: ...\n\nSource messages:\n[N] ...`

**Rollback**: if no segments in DB (pre-v6 channel), `_cluster_rollback()` uses cluster centroid scoring with `RETRIEVAL_MIN_SCORE` threshold.

**Message fallback**: fires when segment retrieval returns empty — direct cosine search over `message_embeddings`.

**Summary fallback**: if both segment and message search return empty, full summary injected. Logs WARNING.

**Timestamps**: every retrieved message prefixed with `[YYYY-MM-DD]`. Today's date injected at top of context block.

## Summarization System (v6.0.0 — segment-based)

`!summary create` runs the segment pipeline via `summarizer.py` → `segmenter.py` → `cluster_overview.py`:

1. **Segment**: Gemini batch-processes messages (500/batch, 20 overlap) — identifies topic boundaries and writes a synthesis per segment resolving implicit references ("yes" → "Alice agreed to use PostgreSQL")
2. **Embed segments**: OpenAI embeds each synthesis, stored in `segments.embedding`
3. **Cluster segments**: UMAP + HDBSCAN on segment embeddings → cluster records + `cluster_segments` junction (no `cluster_messages` rows — rollback safe)
4. **Per-cluster summarize**: Gemini per cluster using segment syntheses as M-labeled inputs
5. **Classify**: GPT-4o-mini whitelist filter — keeps project decisions, config, human-owned actions, user identity, genuine open questions; missing verdicts default to DROP
6. **Overview**: Gemini with cluster labels + summary texts → channel overview + participants
7. **Deduplicate**: embedding cosine similarity (0.85 threshold) drops near-duplicate items
8. **Answered-question check**: GPT-4o-mini YES/NO per open question vs decisions + facts
9. **Translate + save**: field names mapped to v4.x format and stored in `channel_summaries`

**Fallback**: if segmentation yields 0 segments or segment clustering fails, falls back automatically to direct message clustering (v5.x path).

**Key design choices:**
- Synthesis resolves implicit meaning — context is preserved across segment boundaries
- Segment embeddings replace per-message embeddings for clustering and retrieval
- Classifier runs before overview LLM — prevents 16K+ token response with 50+ clusters
- `cluster_messages` not written in segment path — `message_embeddings` retained for rollback
- Field translation at storage time — display layer (`format_always_on_context`) unchanged

## Configuration

See `README_ENV.md` for the complete environment variable reference.

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token (required) | — |
| `AI_PROVIDER` | Default conversation provider | `openai` |
| `OPENAI_API_KEY` | Required for embeddings + classifier | — |
| `SUMMARIZER_PROVIDER` | Summarization provider | `gemini` |
| `GEMINI_API_KEY` | Required for summarization | — |
| `DATABASE_PATH` | SQLite database location | `./data/messages.db` |
| `CONTEXT_BUDGET_PERCENT` | % of context window for input | `80` |
| `MAX_RECENT_MESSAGES` | Recent messages included in context | `5` |
| `EMBEDDING_MODEL` | OpenAI embedding model | `text-embedding-3-small` |
| `RETRIEVAL_TOP_K` | Max segments returned per query (dense pool = top_k × 2) | `7` |
| `PROPOSITION_BATCH_SIZE` | Segment syntheses per GPT-4o-mini decomposition call | `10` |
| `RETRIEVAL_FLOOR` | Absolute minimum score for segment retrieval | `0.20` |
| `RETRIEVAL_SCORE_GAP` | Cut dense candidates at largest inter-score gap ≥ this | `0.08` |
| `RRF_K` | Reciprocal Rank Fusion constant (lower = more top-rank weight) | `15` |
| `RETRIEVAL_MIN_SCORE` | Min cosine similarity for cluster rollback path | `0.25` (production: `0.5`) |
| `QUERY_TOPIC_SHIFT_THRESHOLD` | Topic-shift detection threshold for smart query embedding | `0.5` |
| `EMBEDDING_CONTEXT_MIN_SCORE` | Min cosine similarity for context prepending in stored embeddings | `0.3` |
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
!debug backfill      # embed unembedded messages with context
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
