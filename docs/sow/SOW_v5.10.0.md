# SOW v5.10.0 — Dead Code Removal (v4.x Pipeline)
# Status: PROPOSED — awaiting approval
# Branch: development
# Prerequisite: claude-code merged into development (done)

---

## Objective

Remove the v4.x three-pass summarization pipeline and topic-based
retrieval code that has been dead since v5.3.0 (summarization) and
v5.5.0 (retrieval). These files were retained for rollback safety
during v5 development. The v5 cluster pipeline has been live and
validated through 9 versions (v5.1.0–v5.9.0). Git history preserves
all deleted files for recovery if ever needed.

---

## Scope

### Delete 10 files (entire v4.x pipeline + topic system)

| File | Version | Why dead |
|------|---------|----------|
| `utils/summarizer_authoring.py` | v1.10.2 | Three-pass Secretary/Structurer/Classifier — replaced by cluster pipeline in v5.3.0 |
| `utils/summary_delta_schema.py` | v1.0.0 | anyOf schema + translate_ops() — only used by summarizer_authoring |
| `utils/summary_classifier.py` | v1.3.0 | Old GPT-4o-mini KEEP/DROP/RECLASSIFY — replaced by cluster_classifier.py |
| `utils/summary_prompts_authoring.py` | v1.7.0 | Secretary prompt — only used by summarizer_authoring |
| `utils/summary_prompts_structurer.py` | v1.0.0 | Structurer prompt — only used by summarizer_authoring |
| `utils/summary_prompts.py` | v1.6.0 | build_label_map() — only used by summarizer_authoring |
| `utils/summary_schema.py` | v1.4.0 | apply_ops(), verify_protected_hashes() — only used by summarizer_authoring |
| `utils/summary_normalization.py` | v1.0.1 | Layer 2 normalization — only called from _process_response() in summarizer.py (dead) |
| `utils/summary_validation.py` | v1.0.0 | Layer 3 domain validation — only called from _process_response() in summarizer.py (dead) |
| `utils/topic_store.py` | v1.0.0 | Topic CRUD + linking — replaced by cluster_retrieval.py in v5.5.0; one remaining caller in !debug backfill is itself vestigial (see below) |

### Clean 1 file — `utils/summarizer.py`

Remove 5 dead functions that were only called by the old pipeline:

- `_incremental_loop()` — old batch-and-delegate loop
- `_process_response()` — parse/classify/normalize/validate
- `_repair_call()` — one-retry repair prompt
- `_get_unsummarized_messages()` — query for unprocessed messages
- `_partial()` — result builder for incremental loop

After removal, summarizer.py becomes a clean router (~40 lines):
`summarize_channel()` and `quick_update_channel()`.

### Clean 1 file — `commands/cluster_commands.py`

Remove the topic re-linking tail section from `!debug backfill`.
This code loads `active_topics` + `archived_topics` from the stored
summary and calls `link_topic_to_messages()` for each. Since v5.5.0
nothing reads from the `topics` or `topic_messages` tables, so this
re-linking has no effect. The backfill command's primary job
(embedding messages with contextual text) is unchanged.

Specifically, remove everything after the "Embedded X/Y" status
message through the "Re-linked N topics. Backfill complete." message.
Replace with a simple completion message.

---

## What is NOT in scope

- **Database tables** (`topics`, `topic_messages`): These remain in
  the schema. Dropping tables requires a new migration file and risks
  data loss if the assessment is wrong. Separate SOW if desired.
- **`utils/history/` consolidation**: Separate concern, separate SOW.
- **`config.py` stale default**: Trivial fix, can be a one-liner
  alongside this work or done separately.
- **Schema migration files** (`schema/004.sql`): Migration files are
  historical records — they must remain so the runner works correctly
  on fresh databases.

---

## Verification

Before deleting anything, confirm zero active callers via grep:

```bash
cd /path/to/discord-bot
# For each file being deleted, verify no active code imports it:
grep -r "summarizer_authoring" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_delta_schema" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_classifier" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_prompts_authoring" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_prompts_structurer" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_prompts" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__" | grep -v "summary_prompts_authoring" | grep -v "summary_prompts_structurer"
grep -r "summary_schema" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__" | grep -v "summary_delta_schema"
grep -r "summary_normalization" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "summary_validation" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
grep -r "topic_store" --include="*.py" | grep -v "^docs/" | grep -v "__pycache__"
```

Expected results:
- Each file should only appear in: (a) its own definition, (b) other
  dead files being deleted, (c) docs/sow/ references, (d) the dead
  functions inside summarizer.py.
- `topic_store` will also match in `cluster_commands.py` — that's the
  backfill tail section being cleaned.

Any unexpected callers must be investigated before proceeding.

---

## Files Changed Summary

| File | Action |
|------|--------|
| `utils/summarizer_authoring.py` | DELETE |
| `utils/summary_delta_schema.py` | DELETE |
| `utils/summary_classifier.py` | DELETE |
| `utils/summary_prompts_authoring.py` | DELETE |
| `utils/summary_prompts_structurer.py` | DELETE |
| `utils/summary_prompts.py` | DELETE |
| `utils/summary_schema.py` | DELETE |
| `utils/summary_normalization.py` | DELETE |
| `utils/summary_validation.py` | DELETE |
| `utils/topic_store.py` | DELETE |
| `utils/summarizer.py` | MODIFY — remove 5 dead functions, bump version |
| `commands/cluster_commands.py` | MODIFY — remove topic re-link from backfill, bump version |
| `STATUS.md` | UPDATE — add v5.10.0 entry |
| `HANDOFF.md` | UPDATE — remove v4.x rollback references, update file tables |
| `README.md` | UPDATE — remove deleted files from project tree |
| `AGENT.md` | UPDATE — remove v4.x pipeline from architecture context |
| `CLAUDE.md` | UPDATE — remove v4.x references |

---

## Testing

1. **Bot starts cleanly**: `sudo systemctl restart discord-bot` —
   no import errors in logs
2. **!summary create**: Full cluster pipeline runs, produces summary
3. **!summary update**: Dirty cluster re-summarization works
4. **!summary / !summary full**: Display works
5. **!summary clear**: Clears summary and clusters
6. **Bot responds**: Direct mention → retrieval + citations working
7. **!debug backfill**: Embeds messages, no topic re-link step,
   completes without error
8. **!debug reembed**: Invokes backfill, completes cleanly
9. **!explain**: Context receipt still works
10. **No import errors**: `grep -r "import.*summarizer_authoring\|import.*summary_delta\|import.*summary_classifier\|import.*summary_prompts\|import.*summary_schema\|import.*summary_normalization\|import.*summary_validation\|import.*topic_store" --include="*.py"` returns nothing

---

## Risk Assessment

**Low.** All deleted code has zero active callers. The v5 pipeline has
been the sole active path since v5.3.0 (summarization) and v5.5.0
(retrieval). Every function being removed was confirmed dead via the
pseudocode call-graph analysis. The grep verification step catches
any missed dependencies before files are deleted.

The only caller that touches deleted code (`!debug backfill` →
`topic_store.link_topic_to_messages`) is itself removing dead
functionality — topic re-linking has had no observable effect since
cluster-based retrieval replaced topic-based retrieval.

---

## Constraints

1. Full files only for modified files (summarizer.py, cluster_commands.py)
2. Increment version numbers
3. 250-line limit maintained
4. All development on `development` branch
5. Run grep verification BEFORE deleting
6. Update all documentation files
