# SOW v5.2.0 — Per-Cluster LLM Summarization
# Part 1 of 2: Objective, Module Design, Prompt, Schema
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.1.0 (HDBSCAN clustering validated)

---

## Objective

Add a single LLM call per cluster to extract structured information:
label, summary, decisions, key_facts, action_items, open_questions,
and status. Results are stored back into the `clusters` table.

This phase does NOT generate the cross-cluster overview, does NOT
modify `channel_summaries`, and does NOT change the bot's response
pipeline. It adds a `!debug summarize_clusters` command for validation.

---

## Context From v5.1.0

v5.1.0 produced 56 clusters on #openclaw (741 messages, 0.3% noise).
Cluster coherence was validated by manual spot-check — real topic
clusters (animal strength, database decisions, airplane mechanics)
are cleanly separated from meta-clusters (bot denials, filler,
connection testing).

The research report recommends:
- **10-30 messages** per cluster is the sweet spot for summarization
- **Single-stage extraction** (not two-stage) for per-cluster summaries
- **Gemini structured output** with `response_json_schema` is reliable
  for flat schemas with simple types
- Place `summary` field first in schema to force synthesis before
  extraction
- Large clusters (100+ msgs): truncate to most recent 50

---

## New Module: `utils/cluster_summarizer.py`

Must stay under **250 lines**. Contains the per-cluster summarization
logic. v5.3.0 will add the cross-cluster overview and orchestrator
to this file (or a sibling file if it would exceed 250 lines).

### Functions Required

```python
async def summarize_cluster(cluster_id, channel_id, provider):
    """Summarize a single cluster using Gemini structured output.

    Steps:
    1. Load message_ids from cluster_messages table
    2. Fetch message content from messages table
    3. Format messages with M-labels: "M1 [date] author: content"
    4. If > 50 messages, truncate to most recent 50 with prefix note
    5. Call Gemini with structured JSON schema
    6. Parse response, validate fields
    7. Update clusters table: label, summary, status
    8. Return structured result dict

    Returns dict with: label, summary, decisions, key_facts,
    action_items, open_questions, status. Or None on failure.
    """

async def summarize_all_clusters(channel_id, provider):
    """Summarize all clusters for a channel.

    For each cluster in the channel (ordered by message_count desc):
    1. Call summarize_cluster()
    2. Log progress: "Cluster N/M: 'label' (K msgs)"
    3. Store structured fields in clusters table

    Returns summary of results: clusters processed, failures, total
    tokens used.
    """
```

### Message Formatting

Messages are sent to Gemini with M-labels so `source_message_ids`
can reference them:

```
M1 [2026-02-24] absolutebeginner: what about their relative strength?
M2 [2026-02-24] Synthergy-GPT4: Great question! The strength differences...
M3 [2026-02-24] absolutebeginner: how strong are squirrels compared to humans?
```

The M-label is the 1-based index within the cluster's message list.
The actual `message_id` (Discord snowflake) is tracked in a mapping
dict so `source_message_ids` from the LLM response (["M1", "M3"]) can
be converted back to real IDs for storage.

### Large Cluster Handling

If a cluster has > 50 messages, include only the most recent 50 with
a prefix note:

```
NOTE: This cluster contains 95 messages. The 50 most recent are shown.
Earlier messages covered similar topics.

M1 [2026-03-15] ...
```

### Gemini API Call

Use the existing Gemini provider with structured output:

```python
from ai_providers import get_provider
from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL

provider = get_provider(SUMMARIZER_PROVIDER)
response = await provider.generate_ai_response(
    messages=[
        {"role": "system", "content": CLUSTER_SYSTEM_PROMPT},
        {"role": "user", "content": formatted_messages}
    ],
    max_tokens=2048,
    temperature=0.3,
    channel_id=channel_id,
    response_mime_type="application/json",
    response_json_schema=CLUSTER_SUMMARY_SCHEMA,
    use_json_schema=True,
)
```

---

## Prompt Design

### System Prompt (`CLUSTER_SYSTEM_PROMPT`)

```
You are a conversation summarizer. You will receive a group of related
messages from a Discord channel. These messages are about the same
general topic (grouped by semantic similarity). Your job is to extract
durable information.

Return a JSON object with the specified schema.

FIELD DEFINITIONS:
- summary: 1-3 sentence summary of what was discussed and any
  conclusions reached. Write this FIRST.
- label: A concise topic title (3-8 words) describing this group.
  Examples: "Database Selection and Hosting", "Animal Evolution
  Discussion", "Sprint Planning for Q2".
- decisions: Explicit agreements on courses of action. NOT factual
  lookups, casual preferences, or hypothetical discussions.
- key_facts: Durable facts, constraints, metrics, or reference
  information established in the discussion.
- action_items: Tasks someone committed to or was assigned. Include
  owner if identifiable.
- open_questions: Unresolved questions requiring future answers.
  NOT rhetorical, trivia, or already-answered questions.
- status: "active" if the topic is ongoing or has open items;
  "archived" if the discussion concluded with no pending work.
- source_message_ids: Use the M-labels (M1, M2, etc.) provided
  with each message.

RULES:
- If a field has no items, return an empty array.
- Ignore bot self-descriptions, capability statements, and filler.
- Focus on human-generated content; bot responses provide context.
- Be concise. Each field should capture the essence, not restate
  every message.
```

---

## JSON Schema (`CLUSTER_SUMMARY_SCHEMA`)

Flat schema — no anyOf, no discriminated union, no camelCase
conversion. This is dramatically simpler than the v4.x Structurer
schema.

Top-level fields (all required):
- `summary` (string) — listed first to encourage Gemini to synthesize
  before extracting specifics (research finding)
- `label` (string)
- `status` (string, enum: ["active", "archived"])
- `decisions` (array of item objects)
- `key_facts` (array of item objects)
- `action_items` (array of item objects — adds `owner` string and
  `status` enum ["open", "completed"])
- `open_questions` (array of item objects)

Each **item object** has: `id` (string, required), `text` (string,
required), `source_message_ids` (array of strings, optional).

Build `CLUSTER_SUMMARY_SCHEMA` as a Python dict constant following
this structure. Use `"type": "object"` with `"properties"` and
`"required"` at each level. No anyOf, no discriminated union.

---

*Continued in Part 2: Storage, Commands, Testing, File Summary*
