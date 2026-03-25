#!/usr/bin/env python3
"""Tier 2 unit tests for v3.2.x summarization modules."""
import os, sys, json, tempfile
sys.path.insert(0, '.')

results = []

def check(label, got, want):
    ok = got == want
    results.append((label, ok))
    status = 'PASS' if ok else 'FAIL'
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         got ={repr(got)}")
        print(f"         want={repr(want)}")

from utils.summary_schema import (
    make_empty_summary, compute_hash, apply_ops,
    verify_protected_hashes, run_source_verification, DELTA_SCHEMA,
)
from utils.summary_prompts import build_label_map, build_prompt
from utils.summary_normalization import (
    parse_json_response, classify_response,
    canonicalize_full_summary, diff_full_to_ops,
)
from utils.summary_validation import validate_domain
from utils.summarizer import _translate_labels_to_ids

# ── make_empty_summary ────────────────────────────────────────────────────────
print()
print("make_empty_summary")
s = make_empty_summary(42)
check("channel_id stored as str", s["channel_id"], "42")
check("schema_version 1.0", s["schema_version"], "1.0")
check("decisions empty list", s["decisions"], [])
check("meta.verification present", "verification" in s["meta"], True)

# ── compute_hash ──────────────────────────────────────────────────────────────
print()
print("compute_hash")
h = compute_hash("hello")
check("returns 8 chars", len(h), 8)
check("hex chars only", all(c in "0123456789abcdef" for c in h), True)
check("deterministic", compute_hash("hello"), compute_hash("hello"))
check("different inputs differ", compute_hash("hello") != compute_hash("world"), True)

# ── DELTA_SCHEMA ──────────────────────────────────────────────────────────────
print()
print("DELTA_SCHEMA")
check("is a dict", isinstance(DELTA_SCHEMA, dict), True)
check("required fields present", DELTA_SCHEMA.get("required"), ["schema_version", "mode", "ops"])
ops_schema = DELTA_SCHEMA["properties"]["ops"]["items"]
op_enum = ops_schema["properties"]["op"]["enum"]
check("noop in op enum", "noop" in op_enum, True)
check("add_decision in op enum", "add_decision" in op_enum, True)
check("supersede_decision in op enum", "supersede_decision" in op_enum, True)

# ── apply_ops — overview and participant ──────────────────────────────────────
print()
print("apply_ops — overview and add_participant")
base = make_empty_summary(1)
upd = apply_ops(base, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "update_overview", "id": "overview", "text": "We are building a bot."},
    {"op": "add_participant", "id": "u1", "text": "Alice"},
]})
check("overview set", upd["overview"], "We are building a bot.")
check("participant added", len(upd["participants"]), 1)
check("participant display_name", upd["participants"][0]["display_name"], "Alice")

upd_dup = apply_ops(upd, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "add_participant", "id": "u1", "text": "Alice"},
]})
check("duplicate participant rejected", len(upd_dup["participants"]), 1)

# ── apply_ops — ADD decision ───────────────────────────────────────────────────
print()
print("apply_ops — add_decision")
upd2 = apply_ops(base, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "add_decision", "id": "dec-001", "text": "Use SQLite",
     "status": "active", "source_message_ids": []},
]})
check("decision added", len(upd2["decisions"]), 1)
check("decision content correct", upd2["decisions"][0]["decision"], "Use SQLite")
check("text_hash assigned", len(upd2["decisions"][0].get("text_hash", "")), 8)

# ── apply_ops — duplicate ADD rejected ────────────────────────────────────────
print()
print("apply_ops — duplicate ADD rejected")
upd3 = apply_ops(upd2, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "add_decision", "id": "dec-001", "text": "Use SQLite again", "source_message_ids": []},
]})
check("duplicate ADD rejected, count still 1", len(upd3["decisions"]), 1)

# ── apply_ops — supersede_decision ────────────────────────────────────────────
print()
print("apply_ops — supersede_decision")
upd4 = apply_ops(upd2, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "supersede_decision", "id": "dec-002", "text": "Use PostgreSQL",
     "status": "active", "supersedes_id": "dec-001", "source_message_ids": []},
]})
check("old decision marked superseded", upd4["decisions"][0]["status"], "superseded")
check("new decision added", len(upd4["decisions"]), 2)
check("supersedes_id ref correct", upd4["decisions"][1]["supersedes_id"], "dec-001")

# ── apply_ops — complete_action_item ─────────────────────────────────────────
print()
print("apply_ops — complete_action_item")
with_action = apply_ops(base, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "add_action_item", "id": "act-001", "text": "Write tests",
     "status": "open", "source_message_ids": []},
]})
completed = apply_ops(with_action, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "complete_action_item", "id": "act-001"},
]})
check("action item completed", completed["action_items"][0]["status"], "completed")
check("task content unchanged", completed["action_items"][0]["task"], "Write tests")

# ── apply_ops — update_topic_status unknown ID ────────────────────────────────
print()
print("apply_ops — update_topic_status unknown ID skipped")
unchanged = apply_ops(base, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "update_topic_status", "id": "topic-999", "status": "resolved"},
]})
check("unknown id update skipped, topics still empty", len(unchanged["active_topics"]), 0)

# ── apply_ops — does not mutate original ──────────────────────────────────────
print()
print("apply_ops — does not mutate original")
original = make_empty_summary(99)
_ = apply_ops(original, {"schema_version": "delta.v1", "mode": "incremental", "ops": [
    {"op": "update_overview", "id": "overview", "text": "Changed"},
]})
check("original overview unchanged", original["overview"], "")

# ── verify_protected_hashes — assigns text_hash to new items ─────────────────
print()
print("verify_protected_hashes — assigns text_hash to new items")
new_item_summary = make_empty_summary(1)
new_item_summary["decisions"].append({
    "id": "dec-001", "decision": "Use SQLite", "status": "active"
    # no text_hash — should be assigned
})
snapshot = json.loads(json.dumps(new_item_summary))
mismatches, verified = verify_protected_hashes(new_item_summary, snapshot)
check("text_hash assigned to new item",
      new_item_summary["decisions"][0].get("text_hash"),
      compute_hash("Use SQLite"))
check("no mismatches on new item", mismatches, 0)
check("verified count 1", verified, 1)

# ── verify_protected_hashes — detects and restores mismatch ──────────────────
print()
print("verify_protected_hashes — detect and restore mismatch")
tampered = json.loads(json.dumps(new_item_summary))
snap2     = json.loads(json.dumps(new_item_summary))
tampered["decisions"][0]["decision"] = "Use Redis"  # tamper content, hash stays old
mismatches2, _ = verify_protected_hashes(tampered, snap2)
check("mismatch detected", mismatches2, 1)
check("original content restored", tampered["decisions"][0]["decision"], "Use SQLite")
check("original hash preserved",
      tampered["decisions"][0]["text_hash"], compute_hash("Use SQLite"))

# ── run_source_verification ───────────────────────────────────────────────────
print()
print("run_source_verification")
sv_summary = make_empty_summary(1)
sv_summary["key_facts"].append({
    "id": "fact-001", "fact": "We use SQLite",
    "text_hash": compute_hash("We use SQLite"),
    "category": "reference", "source_message_ids": [100, 101], "source_verified": None,
})
sv_summary["key_facts"].append({
    "id": "fact-002", "fact": "Budget is 50K",
    "text_hash": compute_hash("Budget is 50K"),
    "category": "metric", "source_message_ids": [102], "source_verified": None,
})
sv_summary["key_facts"].append({
    "id": "fact-003", "fact": "Team size is 5",
    "text_hash": compute_hash("Team size is 5"),
    "category": "commitment", "source_message_ids": [103], "source_verified": None,
})
sv_summary["pinned_memory"].append({
    "id": "pin-001", "text": "Never use Redis",
    "text_hash": compute_hash("Never use Redis"),
    "source_message_ids": [104], "source_verified": None,
})
messages_by_id = {
    100: "Agreed, We use SQLite for storage",
    101: "yes that is the plan",
    102: "the budget is completely different",   # fact-002 will fail
    103: "team has five people, Team size is 5", # fact-003 will pass
    104: "Never use Redis under any circumstances",
}
passed, failed = run_source_verification(sv_summary, messages_by_id)
check("fact-001 source_verified True",  sv_summary["key_facts"][0]["source_verified"], True)
check("fact-002 source_verified False", sv_summary["key_facts"][1]["source_verified"], False)
check("fact-003 source_verified True",  sv_summary["key_facts"][2]["source_verified"], True)
check("pin-001 source_verified True",   sv_summary["pinned_memory"][0]["source_verified"], True)
check("passed count", passed, 3)
check("failed count", failed, 1)

print()
print("run_source_verification — skips already-verified items")
passed2, failed2 = run_source_verification(sv_summary, messages_by_id)
check("already-verified items all skipped", passed2 + failed2, 0)

# ── build_label_map ───────────────────────────────────────────────────────────
print()
print("build_label_map")

class FakeMsg:
    def __init__(self, id_, author, content, created_at="2026-03-10T14:30:00"):
        self.id = id_; self.author_name = author
        self.content = content; self.created_at = created_at

msgs = [FakeMsg(1001, "Alice", "Use SQLite"), FakeMsg(1002, "Bob", "Agreed")]
label_to_id, text = build_label_map(msgs)
check("M1 maps to 1001", label_to_id["M1"], 1001)
check("M2 maps to 1002", label_to_id["M2"], 1002)
check("[M1] in labeled text", "[M1]" in text, True)
check("Alice in labeled text", "Alice" in text, True)
check("two labels generated", len(label_to_id), 2)

print()
print("build_label_map — empty messages")
empty_map, empty_text = build_label_map([])
check("empty messages → empty map", empty_map, {})
check("empty messages → empty text", empty_text, "")

# ── build_prompt ──────────────────────────────────────────────────────────────
print()
print("build_prompt")
current = make_empty_summary(1)
prompt = build_prompt(current, "[M1] Alice: hello")
check("returns two messages", len(prompt), 2)
check("first role is system", prompt[0]["role"], "system")
check("second role is user", prompt[1]["role"], "user")
check("TASK in user content", "TASK:" in prompt[1]["content"], True)
check("CURRENT_STATE in user content", "CURRENT_STATE" in prompt[1]["content"], True)
check("NEW_MESSAGES in user content", "NEW_MESSAGES" in prompt[1]["content"], True)
check("[M1] Alice in user content", "[M1] Alice" in prompt[1]["content"], True)
check("system prompt contains FORBIDDEN", "FORBIDDEN" in prompt[0]["content"], True)

# ── parse_json_response ───────────────────────────────────────────────────────
print()
print("parse_json_response — valid JSON")
r = parse_json_response('{"schema_version": "delta.v1", "ops": []}')
check("parses clean JSON", r, {"schema_version": "delta.v1", "ops": []})

print()
print("parse_json_response — markdown fenced JSON")
fenced = '```json\n{"schema_version": "delta.v1", "ops": []}\n```'
r2 = parse_json_response(fenced)
check("strips markdown fence", r2, {"schema_version": "delta.v1", "ops": []})

print()
print("parse_json_response — prose-wrapped JSON")
prose = 'Here you go:\n{"schema_version": "delta.v1", "ops": []}\nDone.'
r2b = parse_json_response(prose)
check("extracts JSON from prose", r2b, {"schema_version": "delta.v1", "ops": []})

print()
print("parse_json_response — invalid JSON returns None")
r3 = parse_json_response("not json at all")
check("invalid JSON → None", r3, None)

print()
print("parse_json_response — empty string returns None")
r4 = parse_json_response("   ")
check("empty string → None", r4, None)

# ── classify_response ─────────────────────────────────────────────────────────
print()
print("classify_response")
check("delta classified",
    classify_response({"schema_version": "delta.v1", "ops": []}), "delta")
check("full classified",
    classify_response({"overview": "hi", "decisions": []}), "full")
check("unknown classified",
    classify_response({"something": "else"}), "unknown")
check("non-dict classified as unknown",
    classify_response("not a dict"), "unknown")

# ── canonicalize_full_summary ─────────────────────────────────────────────────
print()
print("canonicalize_full_summary — field remap")
full = {
    "decisions": [{"id": "d1", "decision": "x", "name": "ignored",
                   "source_message_id": "M1"}],
    "active_topics": [{"id": "t1", "name": "My Topic", "status": "active"}],
}
canon = canonicalize_full_summary(full)
check("source_message_id → source_message_ids array",
    canon["decisions"][0]["source_message_ids"], ["M1"])
check("source_message_id removed",
    "source_message_id" not in canon["decisions"][0], True)
check("name → title on topic",
    canon["active_topics"][0].get("title"), "My Topic")
check("original not mutated",
    "source_message_id" in full["decisions"][0], True)

# ── diff_full_to_ops ──────────────────────────────────────────────────────────
print()
print("diff_full_to_ops — new items become add ops")
pre = make_empty_summary(1)
full2 = {
    "overview": "New overview",
    "decisions": [{"id": "dec-1", "decision": "Use SQLite", "status": "active",
                   "source_message_ids": ["M1"]}],
    "active_topics": [], "key_facts": [], "action_items": [],
    "open_questions": [], "pinned_memory": [],
}
ops_out = diff_full_to_ops(pre, full2)
op_types = [o["op"] for o in ops_out]
check("update_overview op emitted", "update_overview" in op_types, True)
check("add_decision op emitted", "add_decision" in op_types, True)
add_dec = next(o for o in ops_out if o["op"] == "add_decision")
check("add_decision has correct text", add_dec["text"], "Use SQLite")

print()
print("diff_full_to_ops — protected rewrite rejected")
pre2 = make_empty_summary(1)
pre2["decisions"].append({"id": "dec-1", "decision": "Use SQLite", "text_hash": compute_hash("Use SQLite"), "status": "active"})
full3 = {
    "decisions": [{"id": "dec-1", "decision": "Use Redis", "status": "active",
                   "source_message_ids": []}],
    "active_topics": [], "key_facts": [], "action_items": [],
    "open_questions": [], "pinned_memory": [],
}
ops_out2 = diff_full_to_ops(pre2, full3)
check("protected rewrite rejected (no ops for existing id)", ops_out2, [])

# ── validate_domain ───────────────────────────────────────────────────────────
print()
print("validate_domain — valid ops pass through")
pre3 = make_empty_summary(1)
delta_valid = {"ops": [
    {"op": "add_decision", "id": "d1", "text": "x", "source_message_ids": ["M1"]},
    {"op": "noop", "id": "noop"},
]}
valid_ops = validate_domain(delta_valid, pre3, {"M1", "M2"})
check("valid ops count", len(valid_ops), 2)

print()
print("validate_domain — invalid source ID rejected")
delta_bad_src = {"ops": [
    {"op": "add_fact", "id": "f1", "text": "y", "source_message_ids": ["M99"]},
]}
valid_ops2 = validate_domain(delta_bad_src, pre3, {"M1", "M2"})
check("invalid source_message_id rejected", len(valid_ops2), 0)

print()
print("validate_domain — duplicate ADD ID rejected")
delta_dup = {"ops": [
    {"op": "add_decision", "id": "dup-1", "text": "a", "source_message_ids": ["M1"]},
    {"op": "add_decision", "id": "dup-1", "text": "b", "source_message_ids": ["M1"]},
]}
valid_ops3 = validate_domain(delta_dup, pre3, {"M1"})
check("duplicate ADD ID: only first accepted", len(valid_ops3), 1)

print()
print("validate_domain — ADD of pre-existing ID rejected")
pre4 = make_empty_summary(1)
pre4["decisions"].append({"id": "existing-1", "decision": "x", "text_hash": "abc", "status": "active"})
delta_existing = {"ops": [
    {"op": "add_decision", "id": "existing-1", "text": "y", "source_message_ids": ["M1"]},
]}
valid_ops4 = validate_domain(delta_existing, pre4, {"M1"})
check("ADD of pre-existing ID rejected", len(valid_ops4), 0)

# ── _translate_labels_to_ids ──────────────────────────────────────────────────
print()
print("_translate_labels_to_ids")
ops_list = [
    {"op": "add_decision", "id": "dec-001", "text": "x", "source_message_ids": ["M1", "M2"]},
    {"op": "add_fact",     "id": "fact-001","text": "y", "source_message_ids": ["M2", 99]},
    {"op": "add_topic",    "id": "t-001",   "title": "z"},  # no source_message_ids
]
_translate_labels_to_ids(ops_list, {"M1": 1001, "M2": 1002})
check("M1 translated to 1001", ops_list[0]["source_message_ids"], [1001, 1002])
check("M2 translated, int 99 preserved", ops_list[1]["source_message_ids"], [1002, 99])
check("missing source_message_ids no crash", "source_message_ids" not in ops_list[2], True)

# ── save_channel_summary / get_channel_summary ────────────────────────────────
print()
print("save_channel_summary / get_channel_summary (SQLite)")
tmp_db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = tmp_db
import importlib, config as cfg
importlib.reload(cfg)
import utils.message_store as ms
importlib.reload(ms)
ms.init_database()

from utils.summary_store import save_channel_summary, get_channel_summary

save_channel_summary(555, '{"schema_version": "1.0"}', 10, 9999)
sj, last_id = get_channel_summary(555)
check("summary_json stored", sj, '{"schema_version": "1.0"}')
check("last_message_id stored", last_id, 9999)

sj2, last2 = get_channel_summary(999)
check("missing channel returns (None, None)", (sj2, last2), (None, None))

save_channel_summary(555, '{"schema_version": "1.0", "v": 2}', 20, 11111)
sj3, last3 = get_channel_summary(555)
check("upsert updates last_message_id", last3, 11111)

os.unlink(tmp_db)

# ── Summary ───────────────────────────────────────────────────────────────────
print()
passed_count = sum(1 for _, ok in results if ok)
failed_count = sum(1 for _, ok in results if not ok)
print(f"Results: {passed_count} passed, {failed_count} failed")
if failed_count:
    sys.exit(1)
