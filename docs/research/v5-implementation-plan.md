# v5.0.0 Implementation Plan — Phased Breakdown

## Overview

The v5.0.0 SOW replaces the three-pass LLM summarization pipeline with
embedding-based clustering. Based on the research report, the implementation
uses HDBSCAN (not DBSCAN) with UMAP preprocessing, following the BERTopic-
validated pipeline pattern.

The full SOW is split into **five testable phases**, each producing working
code that can be validated before the next phase begins. No phase leaves
the system in a broken state.

---

## Phase Breakdown

### v5.1.0 — Schema + Clustering Core
**Goal**: HDBSCAN clustering runs on existing embeddings and produces
meaningful clusters. No LLM calls, no integration with the bot.

**Deliverables**:
- `schema/005.sql` — `clusters` and `cluster_messages` tables
- `utils/cluster_store.py` — UMAP + HDBSCAN clustering, cluster CRUD,
  centroid storage, membership storage, noise reduction, diagnostics
- `config.py` v1.13.0 — add HDBSCAN parameters
- `commands/debug_commands.py` v1.4.0 — `!debug clusters` diagnostic

**Test**: Run `!debug clusters` on #openclaw. Verify 8-15 clusters,
reasonable noise ratio, no single cluster dominating. Spot-check 3-5
clusters for message coherence. Tune parameters if needed.

**Why this is first**: Clustering quality is the foundation. If clusters
are bad, nothing downstream works. We need to validate and tune HDBSCAN
parameters before building the summarization layer on top.

---

### v5.2.0 — Per-Cluster LLM Summarization
**Goal**: Each cluster gets a structured LLM summary (label, summary,
decisions, facts, actions, questions, status).

**Deliverables**:
- `utils/cluster_summarizer.py` — per-cluster Gemini calls with
  structured JSON output, prompt construction, schema definition
- Update `cluster_store.py` to store LLM-generated labels and summaries

**Test**: Run per-cluster summarization on the clusters from Phase 1.
Verify labels are concise and accurate. Verify structured fields
(decisions, key_facts, action_items, open_questions) are extracted
correctly. Compare against v4.1.x summary for the same channel.

**Why second**: Depends on Phase 1 clusters. Per-cluster summarization
is the second most important quality gate — if the LLM can't produce
good summaries from clusters, we need to adjust cluster granularity.

---

### v5.3.0 — Cross-Cluster Overview + Summary Storage
**Goal**: Channel-level overview generated from cluster summaries,
stored in `channel_summaries` in a format compatible with always-on
context injection.

**Deliverables**:
- Add `generate_overview()` to `cluster_summarizer.py`
- Add `run_cluster_pipeline()` orchestrator that chains clustering →
  per-cluster summarization → overview generation → storage
- Wire into `summarizer.py` v3.0.0 — route `!summary create` to the
  cluster pipeline

**Test**: Run `!summary create`. Verify the full pipeline completes.
Verify `format_always_on_context()` works with the v5 summary JSON.
Compare overview quality against v4.1.x. Verify `!summary` display
shows cluster-based content.

**Why third**: Depends on Phase 2 summaries. This is the integration
point where the new pipeline replaces the old one for summarization.

---

### v5.4.0 — Retrieval Integration
**Goal**: Cluster centroids replace topic embeddings in the semantic
retrieval path. Bot responses use cluster-retrieved context.

**Deliverables**:
- Add `find_relevant_clusters()` and `get_cluster_messages()` to
  `cluster_store.py`
- Update `context_manager.py` v3.0.0 — swap topic retrieval for
  cluster retrieval
- Update `summary_commands.py` v2.3.0 — cluster-aware display

**Test**: Ask "did we discuss gorillas?" — evolution cluster retrieved.
Ask "what database are we using?" — database cluster, not AI pricing.
Ask about something never discussed — fallback fires. Verify timestamps,
budget trimming, today's date injection all still work.

**Why fourth**: Depends on Phase 3 (clusters must be stored with
centroids). Retrieval is where users see the impact. By this point
clustering and summarization are validated, so retrieval issues point
to centroid quality or threshold tuning — much easier to debug.

---

### v5.5.0 — Polish, Documentation, Testing
**Goal**: Full test plan execution, documentation updates, cleanup.

**Deliverables**:
- Full test plan (Phases 1-6 from SOW Part 4)
- Cost and performance benchmarks
- Update all documentation: STATUS.md, HANDOFF.md, README.md,
  README_ENV.md, CLAUDE.md, AGENT.md
- Update `!debug backfill` to rebuild clusters after embedding

**Test**: Complete test matrix across both channels. Validate cost
reduction vs v4.1.x. Verify degraded-mode fallbacks work correctly.

---

## Design Decisions (Resolved by Research)

These questions from the original SOW Part 4 are now answered:

| Question | Decision | Rationale |
|----------|----------|-----------|
| DBSCAN vs HDBSCAN | **HDBSCAN** | Eliminates eps tuning; handles varying cluster sizes; native in sklearn 1.3+; BERTopic-validated |
| Re-cluster vs incremental | **Full re-cluster** (Option A) | Sub-second at our scale; simpler; no new-cluster detection issues |
| Legacy cleanup timing | **Keep indefinitely** | Zero cost; revert safety; separate future cleanup milestone |
| Per-cluster model | **Gemini Flash Lite** | Simple prompts in its sweet spot; already configured; research confirms flat JSON schema works reliably |
| Dimensionality reduction | **UMAP** to 5 dimensions | BERTopic-proven defaults; critical for HDBSCAN quality in high dimensions |
| Noise handling | **Embedding-based reassignment** | Assign noise points to nearest cluster centroid above threshold; prevents 30-50% of messages being lost |
| Centroid strategy | **Normalized mean** (start), **LLM-summary centroid** (future) | Mean is adequate for launch; LLM-summary re-embedding is a v5.1 optimization |
| Distance metric | **Cosine for UMAP, Euclidean for HDBSCAN** | BERTopic defaults; UMAP output is not normalized so Euclidean is correct |

## New Dependencies

```bash
pip install scikit-learn umap-learn --break-system-packages
```

- `scikit-learn` ≥1.3: HDBSCAN, numpy, scipy (~160-220 MB)
- `umap-learn`: UMAP, pynndescent, numba (~100 MB for numba+llvmlite)

## Configuration (New .env Variables)

```
CLUSTER_MIN_CLUSTER_SIZE=5      # Minimum messages per cluster
CLUSTER_MIN_SAMPLES=3           # HDBSCAN noise sensitivity
UMAP_N_NEIGHBORS=15             # UMAP neighborhood size
UMAP_N_COMPONENTS=5             # UMAP output dimensions
```

Existing variables unchanged: EMBEDDING_MODEL, RETRIEVAL_TOP_K,
RETRIEVAL_MIN_SCORE, RETRIEVAL_MSG_FALLBACK, SUMMARIZER_PROVIDER,
SUMMARIZER_MODEL.
