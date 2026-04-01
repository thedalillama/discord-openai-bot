# AGENT.md
# Version 5.3.0
# Agent Development Rules for Discord Bot Project

## Core Agent Principles

### 1. MANDATORY APPROVAL PROCESS
- NO CODE CHANGES WITHOUT APPROVAL
- Present proposed changes with rationale and impact assessment
- Wait for explicit approval before implementing
- If uncertain, always ask first

### 2. DISCUSSION-FIRST APPROACH
- Discuss the problem, proposed solution, and alternatives before coding
- Explain reasoning behind technical decisions
- Consider impact on existing functionality and architecture

## Git Workflow

### 3. BRANCH MANAGEMENT
- `main` branch: Stable, production-ready code only
- `development` branch: Primary development branch
- Feature branches (e.g. `claude-code`): For isolated work streams
- Never commit untested code to `main`

### 4. DEVELOPMENT PROCESS
- Develop and test in `development` or feature branches
- Commit frequently with clear, descriptive messages
- Test all functionality before considering merge to `main`
- `main` should always be deployable

### 5. RELEASE WORKFLOW
- All development stays in branch until fully tested
- Validate existing functionality after changes
- Tag releases in `main` for version tracking (v2.x, v3.x, v4.x)

## Code Standards

### 6. FILE AND CODE REQUIREMENTS
- 250-line file limit — mandatory for all files
- Single responsibility — each module serves one clear purpose
- Comprehensive docstrings and inline comments
- Module-specific logging with appropriate levels
- Graceful error handling and recovery
- Version header in every file (e.g. `# Version 1.2.0`)
- Increment version on every change
- Update changelog in docstring

### 7. ASYNC SAFETY
- All provider API calls wrapped in `run_in_executor()`
- Never block the Discord event loop with synchronous calls
- All SQLite operations via `asyncio.to_thread()`

### 8. PREFIX TAGGING
- All bot command output must be prefixed:
  - `ℹ️` — informational/noise (filter from API, summarizer, everything)
  - `⚙️` — settings changes (keep for replay, filter from API/summarizer)
- New commands must use these prefixes on all `ctx.send()` calls
- This replaces pattern-matching for noise filtering

### 9. DOCUMENTATION
- **Update README.md, STATUS.md, HANDOFF.md, and README_ENV.md alongside every code change**
- Keep CLAUDE.md current for Claude Code sessions
- Full files only — never partial diffs or patches
- Always provide complete file contents when delivering changes

### 10. MAINTAIN CONSISTENCY
- Follow established patterns and conventions
- Respect modular architecture and file organization
- Maintain backward compatibility with existing APIs and imports

## Current Architecture Context

### Semantic Retrieval (v4.1.x)
- Messages embedded on arrival via OpenAI `text-embedding-3-small`
- Topics cleared and re-linked on every `!summary create` — no duplicates accumulate
- Topics linked to all messages above `TOPIC_LINK_MIN_SCORE` (0.3) by cosine similarity
- Bot-noise topics filtered at retrieval time (`_is_noise_topic()` in `embedding_store.py`)
- At response time: always-on context (overview/facts/actions/questions) + retrieved topic messages
- Only topics above `RETRIEVAL_MIN_SCORE` (0.25) are injected; recent messages capped at 5
- Message fallback fires when no topics pass threshold OR all matched topics have 0 linked messages
- Each retrieved message prefixed with `[YYYY-MM-DD]`; today's date injected at top of context block
- `!debug backfill` batch-embeds 1000 messages per API call; re-links active + archived topics

### Summarization Pipeline (v5.3.0 — cluster-based)
- `!summary create` → `summarizer.py` → `run_cluster_pipeline()` in `cluster_overview.py`
- UMAP + HDBSCAN clustering → per-cluster Gemini summarization → classify → overview → dedup → QA → save
- Classifier (`cluster_classifier.py`): GPT-4o-mini whitelist filter; default-to-DROP on missing verdict
- Overview LLM receives labels + summary texts only (not structured fields) — prevents 16K+ token blowup
- Dedup (`cluster_qa.py`): embedding cosine similarity, 0.85 threshold, all four arrays
- Answered-Q check (`cluster_qa.py`): GPT-4o-mini YES/NO, removes questions answered by facts/decisions
- Field translation at storage time: `text` → `fact`/`task`/`question`/`decision` (v4.x display layer unchanged)
- v4.x three-pass pipeline (`summarizer_authoring.py`) retained for rollback — not called

### Clustering Core (v5.1.0)
- `utils/cluster_engine.py` — UMAP (cosine, 1536→5 dims) + HDBSCAN (euclidean, eom)
- Noise reduction: noise points reassigned to nearest centroid above RETRIEVAL_MIN_SCORE
- `utils/cluster_store.py` — CRUD, run_clustering() orchestrator, format_cluster_report()
- `schema/005.sql` — clusters + cluster_messages tables (alongside v4.x topics)

### Conversation Providers
- OpenAI, Anthropic, DeepSeek — per-channel configurable
- Provider singleton caching, async executor wrapping
- Token-budget context: always-on + retrieved + 5 recent messages

### Persistence
- SQLite with WAL mode: messages, summaries, embeddings, topics, topic_messages
- Settings recovered from Discord message history on startup
- Prefix system (ℹ️/⚙️) for noise vs settings classification

## REMEMBER:
1. NO CODE CHANGES WITHOUT APPROVAL!
2. ALL DEVELOPMENT IN `development` OR FEATURE BRANCHES
3. `main` BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. 250-LINE LIMIT AND MODULAR PATTERNS
6. PREFIX ALL BOT OUTPUT WITH ℹ️ OR ⚙️
7. **UPDATE ALL DOCUMENTATION BEFORE MERGING**

For Technical Details: See README.md and STATUS.md
For Current State: See HANDOFF.md
For Environment Config: See README_ENV.md
For Claude Code: See CLAUDE.md
For Agent Workflow: This document
