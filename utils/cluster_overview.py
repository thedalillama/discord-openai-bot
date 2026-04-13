# utils/cluster_overview.py
# Version 2.3.0
"""
Cross-cluster overview generation and full pipeline orchestrator.

CHANGES v2.3.0: Add pre_run_stats=None to run_cluster_pipeline(); skips
run_clustering() and passes use_segments=True for segment path (SOW v6.0.0).
CHANGES v2.2.0: Replace qa_pass with embedding dedup + answered-Q check
- MODIFIED: run_cluster_pipeline() replaces single qa_pass() call with
  deduplicate_summary() then remove_answered_questions() from cluster_qa;
  embedding dedup handles "Use PostgreSQL" × 3; targeted GPT-4o-mini
  handles questions answered by facts/decisions in the same summary

CHANGES v2.1.0: QA pass added (step 8, DeepSeek Reasoner)
CHANGES v2.0.0: Classifier-before-overview restructure
CHANGES v1.0.x: progress_fn, classifier pass, prompt tuning
CREATED v1.0.0: SOW v5.3.0
"""
import json
import asyncio
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.cluster_store import get_clusters_for_channel

logger = get_logger('cluster_overview')

OVERVIEW_SYSTEM_PROMPT = """\
You are a conversation analyst. Given a list of topic clusters from a
Discord channel, write a brief channel-level overview and identify all
human participants mentioned across the clusters.

- overview: 2-3 sentences describing what this channel is used for and
  what the main topics of discussion have been.
- participants: All human participants mentioned across the clusters.

Return a JSON object with the specified schema.
"""

_PARTICIPANT = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "display_name": {"type": "string"}},
    "required": ["id", "display_name"],
}

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overview":     {"type": "string"},
        "participants": {"type": "array", "items": _PARTICIPANT},
    },
    "required": ["overview", "participants"],
}


def _format_cluster_input(clusters):
    """Format cluster labels and summary texts for the overview prompt."""
    lines = []
    for i, c in enumerate(clusters, 1):
        label = c["label"] or f"Cluster {i}"
        blob_raw = c.get("summary", "") or ""
        summary_text = ""
        if blob_raw:
            try:
                summary_text = json.loads(blob_raw).get("text", "")
            except Exception:
                pass
        entry = f"Cluster {i} — \"{label}\" ({c['message_count']} msgs, {c['status'] or 'unknown'})"
        if summary_text:
            entry += f" — {summary_text}"
        lines.append(entry)
    return "\n".join(lines)


def _collect_structured_items(clusters):
    """Aggregate decisions/facts/actions/questions from all cluster blobs.

    Items are re-indexed with fresh IDs (D1…, KF1…, A1…, Q1…).
    """
    decisions, key_facts, action_items, open_questions = [], [], [], []
    nd = nkf = nai = nq = 0
    for c in clusters:
        blob_raw = c.get("summary", "") or ""
        if not blob_raw:
            continue
        try:
            blob = json.loads(blob_raw)
        except Exception:
            continue
        for d in blob.get("decisions", []):
            nd += 1
            decisions.append({"id": f"D{nd}", "text": d.get("text", "")})
        for kf in blob.get("key_facts", []):
            nkf += 1
            key_facts.append({"id": f"KF{nkf}", "text": kf.get("text", "")})
        for ai in blob.get("action_items", []):
            nai += 1
            action_items.append({
                "id": f"A{nai}", "text": ai.get("text", ""),
                "owner": ai.get("owner", ""), "status": ai.get("status", "open"),
            })
        for oq in blob.get("open_questions", []):
            nq += 1
            open_questions.append({"id": f"Q{nq}", "text": oq.get("text", "")})
    return {
        "decisions": decisions, "key_facts": key_facts,
        "action_items": action_items, "open_questions": open_questions,
    }


async def generate_overview(channel_id, provider, clusters):
    """Generate overview + participants from cluster labels/summaries.

    Returns dict with overview + participants, or None on failure.
    """
    if not clusters:
        logger.warning(f"generate_overview: no clusters for ch:{channel_id}")
        return None
    formatted = _format_cluster_input(clusters)
    for attempt in range(2):
        try:
            response = await provider.generate_ai_response(
                messages=[
                    {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
                    {"role": "user",   "content": formatted},
                ],
                max_tokens=1024, temperature=0.3, channel_id=channel_id,
                response_mime_type="application/json",
                response_json_schema=OVERVIEW_SCHEMA, use_json_schema=True,
            )
            result = json.loads(response) if isinstance(response, str) else response
            logger.info(
                f"Overview generated ch:{channel_id}: "
                f"{len(result.get('participants', []))} participants")
            return result
        except Exception as e:
            logger.warning(f"generate_overview attempt {attempt+1} failed: {e}")
    return None


def translate_to_channel_summary(overview_result, cluster_count, noise_count):
    """Map merged pipeline output to v4.x field names for the display layer."""
    return {
        "schema_version": "2.0",
        "overview":       overview_result.get("overview", ""),
        "participants":   overview_result.get("participants", []),
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
             "owner": a.get("owner", "unassigned"), "status": a.get("status", "open")}
            for a in overview_result.get("action_items", [])
        ],
        "open_questions": [
            {"id": q["id"], "question": q["text"], "status": "open"}
            for q in overview_result.get("open_questions", [])
        ],
        "cluster_count":       cluster_count,
        "noise_message_count": noise_count,
        "meta": {
            "pipeline":      "cluster-v5",
            "summarized_at": datetime.now(timezone.utc).isoformat(),
        }
    }


async def run_cluster_pipeline(channel_id, provider, progress_fn=None, pre_run_stats=None):
    """Full pipeline: cluster → summarize → classify → overview → dedup → save.
    pre_run_stats: if provided, skips run_clustering() (segment path).
    """
    from utils.cluster_store import run_clustering
    from utils.cluster_summarizer import summarize_all_clusters
    from utils.cluster_classifier import classify_overview_items
    from utils.cluster_qa import deduplicate_summary, remove_answered_questions
    from utils.summary_store import save_channel_summary
    from utils.message_store import get_channel_messages

    async def _p(msg):
        if progress_fn:
            await progress_fn(msg)

    logger.info(f"Cluster pipeline start ch:{channel_id}")
    use_segments = pre_run_stats is not None
    if not use_segments:
        stats = await asyncio.to_thread(run_clustering, channel_id)
        if stats is None:
            return {"error": "Not enough embeddings — run !debug backfill first",
                    "messages_processed": 0, "cluster_count": 0,
                    "noise_count": 0, "overview_generated": False}
    else:
        stats = pre_run_stats
    cluster_count = stats["cluster_count"]
    noise_count, total = stats["noise_count"], stats["total_messages"]
    await _p(f"Clustering complete — {cluster_count} clusters, {noise_count} noise messages")

    await _p(f"Summarizing {cluster_count} clusters (this takes a few minutes)...")
    sum_result = await summarize_all_clusters(
        channel_id, provider, progress_fn=progress_fn, use_segments=use_segments)
    logger.info(
        f"Per-cluster summarization: {sum_result['processed']} ok, "
        f"{sum_result['failed']} failed")

    clusters = await asyncio.to_thread(get_clusters_for_channel, channel_id)
    aggregated = _collect_structured_items(clusters)
    logger.info(
        f"Aggregated ch:{channel_id}: {len(aggregated['decisions'])} decisions, "
        f"{len(aggregated['key_facts'])} facts, {len(aggregated['action_items'])} actions, "
        f"{len(aggregated['open_questions'])} questions")

    await _p("Classifying structured items...")
    filtered = await classify_overview_items(aggregated)

    await _p("Generating channel overview...")
    overview_result = await generate_overview(channel_id, provider, clusters)
    if overview_result is None:
        logger.warning(f"Overview generation failed, using generic text ch:{channel_id}")
        overview_result = {"overview": "Channel overview unavailable.", "participants": []}

    merged = {
        "overview":       overview_result.get("overview", ""),
        "participants":   overview_result.get("participants", []),
        "decisions":      filtered.get("decisions", []),
        "key_facts":      filtered.get("key_facts", []),
        "action_items":   filtered.get("action_items", []),
        "open_questions": filtered.get("open_questions", []),
    }

    channel_summary = translate_to_channel_summary(merged, cluster_count, noise_count)

    await _p("Deduplicating and checking answered questions...")
    channel_summary = await deduplicate_summary(channel_summary)
    channel_summary = await remove_answered_questions(channel_summary)

    all_msgs = await asyncio.to_thread(get_channel_messages, channel_id)
    last_id = max((m.id for m in all_msgs), default=0)
    await asyncio.to_thread(
        save_channel_summary, channel_id,
        json.dumps(channel_summary), total, last_id)

    logger.info(
        f"Cluster pipeline complete ch:{channel_id}: "
        f"{cluster_count} clusters, {noise_count} noise, overview stored")
    return {"cluster_count": cluster_count, "noise_count": noise_count,
            "messages_processed": total, "overview_generated": True,
            "error": None}
