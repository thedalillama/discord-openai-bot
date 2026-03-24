# utils/summary_classifier.py
# Version 1.1.0
"""
GPT-5.4 nano classification pass for summary ops quality control.

CHANGES v1.1.0: Classifier respects Secretary judgment — organize, don't filter
- REWRITTEN: Classifier prompt now treats Secretary output as authoritative.
  Only drops duplicates and individual bot responses repackaged as topics.
  Everything the Secretary included should appear in the final summary.

CHANGES v1.0.2: Return dropped items for audit trail
CHANGES v1.0.1: Add deduplication rules
CREATED v1.0.0: Post-Structurer classification filter
- ADDED: classify_ops() — sends ops to GPT-5.4 nano for KEEP/DROP/RECLASSIFY
- ADDED: filter_ops() — removes DROP ops and applies reclassifications
- Runs after Structurer (cold start) or delta ops (incremental)
- Cost: ~$0.001 per run

The classifier validates whether each item is correctly categorized and
worth retaining. Catches misclassifications that Gemini produces:
- Scientific facts classified as decisions
- Individual bot responses stored as topics
- Transient queries stored as archived topics
"""
import json
import os
from utils.logging_utils import get_logger

logger = get_logger('summary_classifier')

CLASSIFIER_PROMPT = """\
You are a summary quality classifier. The Secretary has already decided \
what content matters. Your job is to organize and deduplicate, not to \
remove content the Secretary included.

For each item, decide:
- KEEP: correctly classified, retain as-is
- DROP: duplicate of another item, or an individual bot response \
repackaged as a topic (e.g. "User asking about X", "Bot provided Y")
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
- DEDUPLICATION: If two items cover the same subject, DROP the less \
specific one. If an archived topic duplicates an active topic, DROP \
the archived one
- Individual bot responses repackaged as topics are DROP \
(e.g. "User asking about the moon phase", "Bot provided gold prices")
- Category-level archived topics are KEEP \
(e.g. "Bot interaction and testing", "Mathematical calculations")

Respond ONLY with a JSON array. Each element:
{"id":"item-id","verdict":"KEEP|DROP|RECLASSIFY",\
"reclassify_to":"new_category or null"}"""

# Map reclassify_to values to op types
_RECLASSIFY_MAP = {
    "DECISION": "add_decision",
    "KEY_FACT": "add_fact",
    "ACTION_ITEM": "add_action_item",
    "OPEN_QUESTION": "add_open_question",
    "ACTIVE_TOPIC": "add_topic",
    "ARCHIVED_TOPIC": "add_topic",
}


async def classify_ops(ops):
    """Send ops to GPT-5.4 nano for classification.

    Args:
        ops: list of delta ops dicts from Structurer/incremental

    Returns:
        dict mapping op id → {"verdict": "KEEP|DROP|RECLASSIFY",
                               "reclassify_to": str|None}
        Returns empty dict on failure (all ops kept by default).
    """
    if not ops or all(op.get("op") == "noop" for op in ops):
        return {}

    # Build items for classification
    items = []
    for op in ops:
        op_type = op.get("op", "")
        op_id = op.get("id", "")
        if op_type in ("noop", "update_overview", "add_participant"):
            continue  # Always keep these
        text = op.get("text", "") or op.get("title", "")
        category = _op_to_category(op_type, op.get("status"))
        items.append({
            "id": op_id, "category": category,
            "status": op.get("status", ""), "text": text,
        })

    if not items:
        return {}

    items_json = json.dumps(items)
    logger.debug(f"Classifying {len(items)} items ({len(items_json)} chars)")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": items_json},
            ],
            temperature=0,
        )
        result_text = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        logger.info(
            f"Classifier: {tokens_in}+{tokens_out} tokens, "
            f"${(tokens_in * 0.03 + tokens_out * 0.15) / 1_000_000:.6f}")
    except Exception as e:
        logger.warning(f"Classifier call failed, keeping all ops: {e}")
        return {}

    # Parse response
    try:
        clean = result_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        results = json.loads(clean)
    except (json.JSONDecodeError, IndexError):
        logger.warning(f"Classifier JSON parse failed, keeping all ops")
        return {}

    verdicts = {}
    for r in results:
        verdicts[r.get("id", "")] = {
            "verdict": r.get("verdict", "KEEP"),
            "reclassify_to": r.get("reclassify_to"),
        }

    kept = sum(1 for v in verdicts.values() if v["verdict"] == "KEEP")
    dropped = sum(1 for v in verdicts.values() if v["verdict"] == "DROP")
    reclass = sum(1 for v in verdicts.values() if v["verdict"] == "RECLASSIFY")
    logger.info(f"Classifier: {kept} keep, {dropped} drop, {reclass} reclassify")

    return verdicts


def filter_ops(ops, verdicts):
    """Filter ops based on classifier verdicts.

    - DROP: remove the op, add to dropped list
    - RECLASSIFY: change the op type
    - KEEP or not in verdicts: leave unchanged

    Returns:
        tuple: (filtered_ops, dropped_ops)
    """
    if not verdicts:
        return ops, []

    filtered = []
    dropped = []
    for op in ops:
        op_id = op.get("id", "")
        verdict = verdicts.get(op_id)

        if verdict is None:
            filtered.append(op)
            continue

        if verdict["verdict"] == "DROP":
            logger.info(f"Dropping: {op.get('op')} id={op_id} "
                        f"text={op.get('text', op.get('title', ''))[:60]}")
            dropped.append(op)
            continue

        if verdict["verdict"] == "RECLASSIFY":
            new_cat = verdict.get("reclassify_to")
            new_op = _RECLASSIFY_MAP.get(new_cat)
            if new_op:
                logger.info(
                    f"Reclassifying {op_id}: {op.get('op')} → {new_op}")
                op = dict(op)
                op["op"] = new_op
            else:
                logger.warning(
                    f"Unknown reclassify target '{new_cat}' for {op_id}")

        filtered.append(op)

    return filtered, dropped


def _op_to_category(op_type, status=None):
    """Map op type to classifier category string."""
    mapping = {
        "add_decision": "DECISION",
        "supersede_decision": "DECISION",
        "add_fact": "KEY_FACT",
        "add_action_item": "ACTION_ITEM",
        "add_open_question": "OPEN_QUESTION",
        "add_topic": "ARCHIVED_TOPIC" if status == "archived"
                     else "ACTIVE_TOPIC",
        "add_pinned_memory": "KEY_FACT",
        "complete_action_item": "ACTION_ITEM",
        "close_open_question": "OPEN_QUESTION",
    }
    return mapping.get(op_type, "UNKNOWN")
