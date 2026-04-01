# utils/cluster_qa.py
# Version 1.0.0
"""
Post-classifier QA for channel summaries.

Two-step pipeline applied after translate_to_channel_summary():
  1. deduplicate_summary() — embedding cosine similarity dedup (Python, no LLM)
  2. remove_answered_questions() — GPT-4o-mini YES/NO classification

Both are fail-safe: return original on any error.

CREATED v1.0.0: Replaces DeepSeek Reasoner qa_pass() (SOW v5.4.0)
- deduplicate_summary(): embeds each item, drops items >0.85 cosine
  similarity to any already-kept item; applied to all four arrays
- remove_answered_questions(): GPT-4o-mini checks each open question
  against decisions + key facts; removes YES answers; defaults to NO
"""
import os
import asyncio
from utils.logging_utils import get_logger
from utils.embedding_store import embed_text, cosine_similarity

logger = get_logger('cluster_qa')

_DEDUP_THRESHOLD = 0.85

ANSWERED_Q_PROMPT = """\
For each open question, determine if it is answered by the provided
decisions or key facts. Respond with the question ID followed by YES
(answered, should be removed) or NO (genuinely unanswered).
"""


def _item_text(item):
    """Extract display text from a v4.x summary item."""
    return (item.get("fact") or item.get("decision")
            or item.get("task") or item.get("question")
            or item.get("text") or "")


def _dedup_items(items):
    """Greedy dedup: drop any item >_DEDUP_THRESHOLD similar to an already-kept item.

    Iterates in order. Items that can't be embedded are kept by default.
    """
    kept = []
    kept_vecs = []
    for item in items:
        vec = embed_text(_item_text(item))
        if vec is None:
            kept.append(item)
            continue
        if any(cosine_similarity(vec, kv) > _DEDUP_THRESHOLD for kv in kept_vecs):
            continue
        kept.append(item)
        kept_vecs.append(vec)
    return kept


def _dedup_all_fields(summary_dict):
    """Run _dedup_items on all four arrays. Synchronous — call via to_thread."""
    result = dict(summary_dict)
    for field in ("decisions", "key_facts", "action_items", "open_questions"):
        items = summary_dict.get(field, [])
        if len(items) > 1:
            result[field] = _dedup_items(items)
    return result


def _build_answered_q_prompt(decisions, key_facts, questions):
    """Build user prompt for the answered-question check."""
    lines = []
    if decisions:
        lines.append("[DECISIONS]")
        for d in decisions:
            lines.append(f"{d['id']}: {d.get('decision', '')}")
        lines.append("")
    if key_facts:
        lines.append("[KEY_FACTS]")
        for kf in key_facts:
            lines.append(f"{kf['id']}: {kf.get('fact', '')}")
        lines.append("")
    lines.append("[OPEN_QUESTIONS]")
    for q in questions:
        lines.append(f"{q['id']}: {q.get('question', '')}")
    lines.append("")
    lines.append("Is each question answered by the decisions or key facts above?")
    return "\n".join(lines)


def _call_answered_q_check(prompt):
    """Synchronous GPT-4o-mini answered-question classification."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ANSWERED_Q_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0,
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""


async def deduplicate_summary(summary_dict):
    """Remove near-duplicate items from all four arrays via embedding similarity.

    Threshold: 0.85 cosine similarity. Greedy: keeps first occurrence in
    cluster order. Fail-safe: returns original on any error.
    """
    try:
        before = sum(len(summary_dict.get(f, []))
                     for f in ("decisions", "key_facts", "action_items", "open_questions"))
        result = await asyncio.to_thread(_dedup_all_fields, summary_dict)
        after = sum(len(result.get(f, []))
                    for f in ("decisions", "key_facts", "action_items", "open_questions"))
        logger.info(
            f"Dedup: {before} items → {after} items "
            f"({before - after} duplicates removed)")
        return result
    except Exception as e:
        logger.warning(f"Dedup failed, using original: {e}")
        return summary_dict


async def remove_answered_questions(summary_dict):
    """Remove open questions that are answered by decisions or key facts.

    GPT-4o-mini YES/NO classification. Default NO (keep) on missing verdict.
    Fail-safe: returns original on any error.
    """
    questions = summary_dict.get("open_questions", [])
    if not questions:
        return summary_dict
    prompt = _build_answered_q_prompt(
        summary_dict.get("decisions", []),
        summary_dict.get("key_facts", []),
        questions,
    )
    try:
        text = await asyncio.to_thread(_call_answered_q_check, prompt)
        verdicts = {}
        for line in text.splitlines():
            line = line.strip()
            if ": " in line:
                qid, verdict = line.split(": ", 1)
                verdicts[qid.strip()] = verdict.strip().upper()
        kept = [q for q in questions if verdicts.get(q["id"], "NO") != "YES"]
        removed = len(questions) - len(kept)
        logger.info(f"Answered-Q check: {removed} questions removed, {len(kept)} kept")
        result = dict(summary_dict)
        result["open_questions"] = kept
        return result
    except Exception as e:
        logger.warning(f"Answered-Q check failed, using original: {e}")
        return summary_dict
