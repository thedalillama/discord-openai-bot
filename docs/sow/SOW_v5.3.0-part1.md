# SOW v5.3.0 — Cross-Cluster Overview + Pipeline Wiring
# Part 1 of 2: Objective, Overview Generation, Compatibility
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.2.0 (per-cluster summarization validated)

---

## Objective

Generate a channel-level overview from per-cluster summaries, store it
in `channel_summaries` in a format compatible with the existing always-on
context system, and wire the full pipeline into `!summary create` so it
replaces the three-pass Secretary/Structurer/Classifier pipeline.

After v5.3.0, running `!summary create` executes:
clustering → per-cluster summarization → cross-cluster overview → store.

---

## Context From v5.2.0

56 clusters summarized with zero failures. Each cluster has a label,
summary text, status, and structured fields (decisions, key_facts,
action_items, open_questions) stored as JSON in the `clusters.summary`
column.

The cross-cluster overview aggregates these into a single channel-level
summary stored in `channel_summaries.summary_json` — the same table
the v4.x pipeline writes to. The existing `format_always_on_context()`
and `format_summary_for_context()` in `summary_display.py` read from
this JSON to inject always-on context into every bot response.

---

## Critical: Summary JSON Compatibility

The existing `format_always_on_context()` expects specific field names:

```python
# Current format_always_on_context reads:
summary.get("overview")                          # string
summary.get("key_facts")     → f.get("fact")     # "fact" not "text"
summary.get("action_items")  → a.get("task")     # "task" not "text"
summary.get("action_items")  → a.get("owner")
summary.get("action_items")  → a.get("status")   # "open"/"in_progress"
summary.get("open_questions") → q.get("question") # "question" not "text"
```

The v5.2.0 per-cluster summaries use `"text"` for all item fields.
The cross-cluster overview must **translate** to the v4.x field names
when building the channel_summaries JSON:

| v5.2.0 cluster field | channel_summaries field |
|-----------------------|------------------------|
| `key_facts[].text` | `key_facts[].fact` |
| `action_items[].text` | `action_items[].task` |
| `open_questions[].text` | `open_questions[].question` |
| `decisions[].text` | `decisions[].decision` |

This means `format_always_on_context()` and `format_summary_for_context()`
require **zero changes**. The translation happens in the overview
generation step, not in the display layer.

Additionally, add `"status": "active"` to each key_fact item since
`format_always_on_context()` filters on `f.get("status") == "active"`.

---

## Cross-Cluster Overview Generation

### Overview Prompt

A single Gemini call receives all cluster summaries and produces the
channel-level always-on context. Input is small (cluster summaries,
not raw messages), so token cost is minimal.

**System prompt** (`OVERVIEW_SYSTEM_PROMPT`):
```
You are a conversation analyst. You will receive summaries of multiple
discussion topics from a Discord channel. Generate a channel-level
overview.

Return a JSON object with the specified schema.

FIELD DEFINITIONS:
- overview: 2-3 sentence description of what this channel is about
  and its main themes.
- key_facts: Only facts that span multiple topics or are universally
  relevant. Do not duplicate every fact from every cluster.
- action_items: Only OPEN items. Omit completed items.
- open_questions: Only UNRESOLVED questions.
- decisions: Active decisions. If a decision was superseded, include
  only the latest version.
- participants: All human participants mentioned across clusters.

RULES:
- Be concise. This context is injected into every bot response.
- Deduplicate: if the same fact/decision appears in multiple clusters,
  include it once.
- If a question in one cluster was answered in another, omit it from
  open_questions.
- Preserve all decisions — these are the most important items.
```

**User prompt**: formatted cluster summaries:
```
Cluster 1 — "Database Selection and Decision" (active, 23 msgs):
  Summary: The team has gone back and forth on the database choice...
  Decisions: The team will use PostgreSQL for the database.
  Key facts: PostgreSQL is a powerful open-source relational database...
  Open items: What are the options for the database given our platform?

Cluster 2 — "Animal Strength and Speed Comparisons" (archived, 21 msgs):
  Summary: Extended discussion about primate evolution...
  Key facts: Squirrels are 5-10x stronger than humans relative to size...

...
```

### Overview JSON Schema

Same Gemini structured output approach as v5.2.0. Flat schema:

```python
OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "key_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"}
                },
                "required": ["id", "text"]
            }
        },
        "decisions": { ... },      # same item structure
        "action_items": { ... },   # adds "owner" and "status"
        "open_questions": { ... }, # same item structure
        "participants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "display_name": {"type": "string"}
                },
                "required": ["id", "display_name"]
            }
        }
    },
    "required": ["overview", "key_facts", "decisions",
                  "action_items", "open_questions", "participants"]
}
```

### Post-Processing: Translate to v4.x Field Names

After receiving the Gemini response, map fields before storing:

```python
def translate_to_channel_summary(overview_result, cluster_count,
                                  noise_count):
    """Convert overview LLM output to channel_summaries format
    compatible with format_always_on_context()."""
    return {
        "schema_version": "2.0",
        "overview": overview_result["overview"],
        "participants": overview_result.get("participants", []),
        "key_facts": [
            {"id": f["id"], "fact": f["text"], "status": "active"}
            for f in overview_result.get("key_facts", [])
        ],
        "decisions": [
            {"id": d["id"], "decision": d["text"], "status": "active"}
            for d in overview_result.get("decisions", [])
        ],
        "action_items": [
            {"id": a["id"], "task": a["text"],
             "owner": a.get("owner", "unassigned"),
             "status": a.get("status", "open")}
            for a in overview_result.get("action_items", [])
        ],
        "open_questions": [
            {"id": q["id"], "question": q["text"], "status": "open"}
            for q in overview_result.get("open_questions", [])
        ],
        "cluster_count": cluster_count,
        "noise_message_count": noise_count,
        "meta": {
            "pipeline": "cluster-v5",
            "summarized_at": datetime.now(timezone.utc).isoformat()
        }
    }
```

This JSON is stored via `save_channel_summary()` and is immediately
compatible with `format_always_on_context()` — no display changes.

---

*Continued in Part 2: Pipeline Orchestration, Summarizer Routing,
Commands, Testing, File Summary*
