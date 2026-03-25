# utils/summary_classifier.py
# Version 1.3.0
"""
GPT-5.4 nano classification pass for summary ops quality control.

CHANGES v1.3.0: Dedup against existing items in stored summary
- classify_ops() accepts existing_summary for dedup comparison
- _build_existing_items() extracts items from summary
- Classifier prompt includes EXISTING ITEMS section

CHANGES v1.2.0: Protect topics with decisions, action items with owners
CHANGES v1.1.0: Classifier respects Secretary judgment
CHANGES v1.0.0-v1.0.2: Initial classifier, dedup rules, audit trail
"""
import json
import os
from utils.logging_utils import get_logger

logger = get_logger('summarizer.classifier')

CLASSIFIER_PROMPT = """\
You are a summary quality classifier. The Secretary has already decided \
what content matters. Your job is to organize and deduplicate, not to \
remove content the Secretary included.

For each item, decide:
- KEEP: correctly classified, retain as-is
- DROP: duplicate of another item OR duplicate of an EXISTING ITEM, \
or an individual bot response repackaged as a topic
- RECLASSIFY: wrong category — specify the correct one

Categories:
- DECISION: A choice agreed upon by participants
- KEY_FACT: Durable personal detail or project info
- ACTION_ITEM: A task someone committed to do
- OPEN_QUESTION: Unresolved question affecting plans
- ACTIVE_TOPIC: Ongoing discussion worth tracking
- ARCHIVED_TOPIC: Resolved discussion kept for reference

Rules:
- Scientific facts are NOT decisions — RECLASSIFY to KEY_FACT or KEEP \
as ACTIVE_TOPIC
- If the Secretary included a topic, KEEP it unless it's a duplicate \
or an individual bot response repackaged as a topic
- NEVER drop an ACTIVE_TOPIC that provides context for a kept DECISION. \
The topic has richer narrative than the one-line decision — both are kept.
- NEVER drop an ACTION_ITEM that has an assigned owner
- DEDUPLICATION: If two items cover the same subject, DROP the less \
specific one. If an archived topic duplicates an active topic, DROP \
the archived one
- Individual bot responses repackaged as topics are DROP \
(e.g. "User asking about the moon phase", "Bot provided gold prices")
- Category-level archived topics are KEEP \
(e.g. "Bot interaction and testing", "Mathematical calculations")

Respond ONLY with a JSON array. Each element:
{"id":"item-id","verdict":"KEEP|DROP|RECLASSIFY",\
"reclassify_to":"new_category or null"}

EXISTING ITEMS (if provided) are already in the stored summary. \
DROP any new op that duplicates an existing item by meaning, even if \
the ID or exact wording differs. Example: new op "The project uses \
PostgreSQL" duplicates existing "Use PostgreSQL for the database" — \
DROP the new op."""

_RECLASSIFY_MAP = {
    "DECISION": "add_decision", "KEY_FACT": "add_fact",
    "ACTION_ITEM": "add_action_item",
    "OPEN_QUESTION": "add_open_question",
    "ACTIVE_TOPIC": "add_topic", "ARCHIVED_TOPIC": "add_topic",
}


async def classify_ops(ops, existing_summary=None):
    """Send ops to GPT-5.4 nano for classification.

    Args:
        ops: list of delta ops dicts from Structurer
        existing_summary: current summary dict for dedup, or None

    Returns:
        dict mapping op id → {"verdict": ..., "reclassify_to": ...}
        Returns empty dict on failure (all ops kept by default).
    """
    if not ops or all(op.get("op") == "noop" for op in ops):
        return {}

    items = []
    for op in ops:
        op_type = op.get("op", "")
        if op_type in ("noop", "update_overview", "add_participant"):
            continue
        text = op.get("text", "") or op.get("title", "")
        items.append({
            "id": op.get("id", ""),
            "category": _op_to_category(op_type, op.get("status")),
            "status": op.get("status", ""), "text": text,
        })
    if not items:
        return {}

    existing = _build_existing_items(existing_summary)
    user_content = f"NEW OPS:\n{json.dumps(items)}"
    if existing:
        user_content += f"\n\nEXISTING ITEMS:\n{json.dumps(existing)}"
    logger.debug(
        f"Classifying {len(items)} items against "
        f"{len(existing)} existing")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        result_text = response.choices[0].message.content
        usage = response.usage
        if usage:
            cost = (usage.prompt_tokens * 0.03 +
                    usage.completion_tokens * 0.15) / 1_000_000
            logger.info(
                f"Classifier: {usage.prompt_tokens}+{usage.completion_tokens}"
                f" tokens, ${cost:.6f}")
    except Exception as e:
        logger.error(f"Classifier API call failed: {e}")
        return {}

    try:
        clean = result_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        verdicts_list = json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse classifier response: {e}")
        logger.debug(f"Raw classifier response: {result_text}")
        return {}

    verdicts = {}
    for v in verdicts_list:
        vid = v.get("id", "")
        verdicts[vid] = {
            "verdict": v.get("verdict", "KEEP"),
            "reclassify_to": v.get("reclassify_to"),
        }
    kept = sum(1 for v in verdicts.values() if v["verdict"] == "KEEP")
    dropped = sum(1 for v in verdicts.values() if v["verdict"] == "DROP")
    reclassified = sum(
        1 for v in verdicts.values() if v["verdict"] == "RECLASSIFY")
    logger.info(
        f"Classifier verdicts: {kept} KEEP, {dropped} DROP, "
        f"{reclassified} RECLASSIFY")
    return verdicts


def filter_ops(ops, verdicts):
    """Apply verdicts: remove DROPs, apply RECLASSIFYs.
    Returns (filtered_ops, dropped_ops)."""
    if not verdicts:
        return ops, []
    filtered = []; dropped = []
    for op in ops:
        op_id = op.get("id", "")
        op_type = op.get("op", "")
        if op_type in ("noop", "update_overview", "add_participant"):
            filtered.append(op); continue
        verdict = verdicts.get(op_id)
        if not verdict:
            filtered.append(op); continue
        if verdict["verdict"] == "DROP":
            logger.info(f"Dropping {op_id} ({op_type})")
            dropped.append(op); continue
        if verdict["verdict"] == "RECLASSIFY":
            new_cat = verdict.get("reclassify_to")
            new_op = _RECLASSIFY_MAP.get(new_cat)
            if new_op:
                logger.info(
                    f"Reclassifying {op_id}: {op_type} → {new_op}")
                op = dict(op); op["op"] = new_op
            else:
                logger.warning(
                    f"Unknown reclassify target '{new_cat}' for {op_id}")
        filtered.append(op)
    return filtered, dropped


def _op_to_category(op_type, status=None):
    """Map op type to classifier category string."""
    mapping = {
        "add_decision": "DECISION", "supersede_decision": "DECISION",
        "add_fact": "KEY_FACT", "add_action_item": "ACTION_ITEM",
        "add_open_question": "OPEN_QUESTION",
        "add_topic": ("ARCHIVED_TOPIC" if status == "archived"
                      else "ACTIVE_TOPIC"),
        "add_pinned_memory": "KEY_FACT",
        "complete_action_item": "ACTION_ITEM",
        "close_open_question": "OPEN_QUESTION",
    }
    return mapping.get(op_type, "UNKNOWN")


def _build_existing_items(summary):
    """Extract existing items from summary for dedup comparison."""
    if not summary:
        return []
    items = []
    for d in summary.get("decisions", []):
        items.append({"id": d["id"], "category": "DECISION",
                      "text": d.get("decision", "")})
    for f in summary.get("key_facts", []):
        items.append({"id": f["id"], "category": "KEY_FACT",
                      "text": f.get("fact", "")})
    for a in summary.get("action_items", []):
        items.append({"id": a["id"], "category": "ACTION_ITEM",
                      "text": a.get("task", "")})
    for q in summary.get("open_questions", []):
        items.append({"id": q["id"], "category": "OPEN_QUESTION",
                      "text": q.get("question", "")})
    for t in summary.get("active_topics", []):
        items.append({"id": t["id"], "category": "ACTIVE_TOPIC",
                      "text": t.get("title", "")})
    return items
