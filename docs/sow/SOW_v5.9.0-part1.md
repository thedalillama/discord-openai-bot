# SOW v5.9.0 — Citation-Backed Responses
# Part 1 of 2: Architecture, Prompt Design, Validation
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.8.0 (clean clusters + explainability)

---

## Objective

When the bot answers a question using retrieved conversation history,
it cites the specific messages it used. Users can see exactly which
past messages informed the answer, inline with the response — not
just via `!explain` after the fact.

**Before:**
> Gorillas can lift about 5-10 times their body weight! Their muscle
> density gives them incredible strength.

**After:**
> Gorillas can lift about 5-10 times their body weight! [1][2] Their
> muscle density gives them incredible strength. [2]
>
> **Sources:**
> [1] absolutebeginner (Feb 25): "how strong are gorillas compared
> to humans?"
> [2] Synthergy-GPT4 (Feb 25): "Gorillas can lift 5-10x their body
> weight..."

---

## Design

### Step 1: Label Retrieved Messages in the Prompt

Currently, retrieved messages are injected as:

```
[Topic: Gorilla Strength and Diet Facts]
[2026-02-25] absolutebeginner: how strong are gorillas?
[2026-02-25] Synthergy-GPT4: Gorillas can lift 5-10x their body weight
```

Change to numbered citation labels:

```
[Topic: Gorilla Strength and Diet Facts]
[1] [2026-02-25] absolutebeginner: how strong are gorillas?
[2] [2026-02-25] Synthergy-GPT4: Gorillas can lift 5-10x their body weight
```

Each message gets a unique sequential number across all retrieved
clusters. The numbering is contiguous: cluster 1 messages are [1]
through [N], cluster 2 continues from [N+1], etc.

### Step 2: Instruct the LLM to Cite

Add citation instructions to the system prompt or to the context
block header. Keep it simple — LLMs follow citation instructions
well when the format is clear:

```
When your answer uses information from the retrieved messages below,
cite the source using [N] notation where N is the message number.
Place citations at the end of the sentence or claim they support.
If you answer from your own knowledge (not from retrieved messages),
do not add citations. Only cite messages you actually use.
```

This goes in the `--- PAST MESSAGES FROM THIS CHANNEL ---` header
block in `context_manager.py` / `context_retrieval.py`, NOT in the
base system prompt. Citations only apply when retrieved messages
exist.

### Step 3: Build Citation Footer

After receiving the LLM response, scan it for citation markers
([1], [2], etc.) and build a footer with the referenced sources.

```python
def build_citation_footer(response_text, citation_map):
    """Extract cited numbers from response, build source footer.

    citation_map: {1: {"author": "...", "date": "...", "content": "..."},
                   2: {...}, ...}

    Returns footer string or empty string if no citations found.
    """
    # Find all [N] patterns in response
    cited = set(re.findall(r'\[(\d+)\]', response_text))
    cited_nums = sorted(int(n) for n in cited if int(n) in citation_map)

    if not cited_nums:
        return ""

    lines = ["\n**Sources:**"]
    for n in cited_nums:
        src = citation_map[n]
        author = src["author"]
        date = src["date"][:10]  # YYYY-MM-DD
        content = src["content"][:100]  # truncate
        lines.append(f'[{n}] {author} ({date}): "{content}"')

    return "\n".join(lines)
```

### Step 4: Validate Citations

Before appending the footer, validate that every cited number
actually exists in the citation_map. Remove any hallucinated
citations (numbers that don't correspond to a real message).

```python
# Remove hallucinated citations from response text
for match in re.findall(r'\[(\d+)\]', response_text):
    if int(match) not in citation_map:
        response_text = response_text.replace(f'[{match}]', '')
```

### Step 5: Append Footer to Response

The citation footer is appended to the bot's response before
sending to Discord. This keeps it simple — no separate message,
no embed, just text appended to the response.

If the response + footer exceeds Discord's 2000 char limit, truncate
the footer (show top 5 citations) or send as a follow-up message.

---

## Citation Map Construction

The citation map is built during context assembly in
`_retrieve_cluster_context()`. When formatting retrieved messages:

```python
citation_map = {}
citation_num = 1

for cluster_id, label, score in clusters:
    msgs = get_cluster_messages(cluster_id, exclude_ids=recent_ids)
    for msg_id, author, content, created_at in msgs:
        citation_map[citation_num] = {
            "message_id": msg_id,
            "author": author,
            "content": content,
            "date": created_at,
            "cluster": label,
        }
        line = f"[{citation_num}] [{created_at[:10]}] {author}: {content}"
        citation_num += 1
```

The citation_map is returned alongside the context text (add it
to the receipt data or return separately). It flows through to
`handle_ai_response()` where it's used to build the footer after
the LLM responds.

---

## When NOT to Cite

- **No retrieved messages**: If retrieval returned empty and the
  bot answers from training knowledge, no citations. No footer.
- **Commands**: `!summary`, `!explain`, `!debug` — no citations.
- **Error responses**: No citations.
- **Greetings/casual**: If the bot responds to "hi" with "hello!",
  no citations even if always-on context was injected.

The LLM handles this naturally — the instruction says "only cite
messages you actually use." If the response doesn't reference
retrieved content, no citation markers appear, and the footer
builder returns empty.

---

*Continued in Part 2: Data Flow, Response Handler, Testing*
