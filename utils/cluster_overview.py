# utils/cluster_overview.py
# Version 1.0.0
"""
Cross-cluster overview generation and full pipeline orchestrator (v5.3.0).

CREATED v1.0.0: Cross-cluster overview + pipeline wiring (SOW v5.3.0)
- _format_cluster_input(): format stored cluster summaries for Gemini
- generate_overview(): single Gemini call → channel-level overview
- translate_to_channel_summary(): map v5.2.0 field names to v4.x format
  expected by format_always_on_context() and format_summary_for_context()
- run_cluster_pipeline(): full v5 pipeline entry point:
  cluster → per-cluster summarize → overview → translate → save
"""
import json
import asyncio
from datetime import datetime, timezone
from utils.logging_utils import get_logger
from utils.cluster_store import get_clusters_for_channel

logger = get_logger('cluster_overview')

OVERVIEW_SYSTEM_PROMPT = """\
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
"""

_ITEM = {
    "type": "object",
    "properties": {
        "id":   {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["id", "text"],
}

_ACTION_ITEM = {
    "type": "object",
    "properties": {
        "id":     {"type": "string"},
        "text":   {"type": "string"},
        "owner":  {"type": "string"},
        "status": {"type": "string", "enum": ["open", "completed"]},
    },
    "required": ["id", "text"],
}

_PARTICIPANT = {
    "type": "object",
    "properties": {
        "id":           {"type": "string"},
        "display_name": {"type": "string"},
    },
    "required": ["id", "display_name"],
}

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overview":       {"type": "string"},
        "key_facts":      {"type": "array", "items": _ITEM},
        "decisions":      {"type": "array", "items": _ITEM},
        "action_items":   {"type": "array", "items": _ACTION_ITEM},
        "open_questions": {"type": "array", "items": _ITEM},
        "participants":   {"type": "array", "items": _PARTICIPANT},
    },
    "required": ["overview", "key_facts", "decisions",
                 "action_items", "open_questions", "participants"],
}


def _format_cluster_input(clusters):
    """Format stored cluster summaries as text for the overview prompt."""
    lines = []
    for i, c in enumerate(clusters, 1):
        label = c["label"] or f"Cluster {i}"
        status = c["status"] or "unknown"
        lines.append(
            f"Cluster {i} — \"{label}\" ({status}, {c['message_count']} msgs):")
        blob_raw = c.get("summary", "") or ""
        if blob_raw:
            try:
                blob = json.loads(blob_raw)
                text = blob.get("text", "")
                if text:
                    lines.append(f"  Summary: {text}")
                for d in blob.get("decisions", []):
                    lines.append(f"  Decision: {d.get('text', '')}")
                for kf in blob.get("key_facts", []):
                    lines.append(f"  Key fact: {kf.get('text', '')}")
                for ai in blob.get("action_items", []):
                    owner = f" (owner: {ai['owner']})" if ai.get("owner") else ""
                    lines.append(f"  Open item: {ai.get('text', '')}{owner}")
                for oq in blob.get("open_questions", []):
                    lines.append(f"  Open question: {oq.get('text', '')}")
            except Exception:
                lines.append("  (no parsed summary)")
        lines.append("")
    return "\n".join(lines)


async def generate_overview(channel_id, provider):
    """Generate channel-level overview from stored cluster summaries.

    Returns parsed overview dict or None on failure.
    """
    clusters = await asyncio.to_thread(get_clusters_for_channel, channel_id)
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
                max_tokens=4096,
                temperature=0.3,
                channel_id=channel_id,
                response_mime_type="application/json",
                response_json_schema=OVERVIEW_SCHEMA,
                use_json_schema=True,
            )
            result = json.loads(response) if isinstance(response, str) else response
            logger.info(
                f"Overview generated ch:{channel_id}: "
                f"{len(result.get('key_facts', []))} facts, "
                f"{len(result.get('decisions', []))} decisions")
            return result
        except Exception as e:
            logger.warning(f"generate_overview attempt {attempt+1} failed: {e}")
    return None


def translate_to_channel_summary(overview_result, cluster_count, noise_count):
    """Translate overview output to channel_summaries format.

    Maps v5.2.0 'text' field names to v4.x names expected by
    format_always_on_context() — zero changes required to display layer.
    """
    return {
        "schema_version": "2.0",
        "overview": overview_result.get("overview", ""),
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
            "summarized_at": datetime.now(timezone.utc).isoformat(),
        }
    }


async def run_cluster_pipeline(channel_id, provider):
    """Full v5 pipeline: cluster → per-cluster summarize → overview → store.

    Returns:
        {cluster_count, noise_count, messages_processed,
         overview_generated, error}
    """
    from utils.cluster_store import run_clustering
    from utils.cluster_summarizer import summarize_all_clusters
    from utils.summary_store import save_channel_summary
    from utils.message_store import get_channel_messages

    logger.info(f"Cluster pipeline start ch:{channel_id}")

    # Step 1: UMAP + HDBSCAN clustering
    stats = await asyncio.to_thread(run_clustering, channel_id)
    if stats is None:
        return {"error": "Not enough embeddings — run !debug backfill first",
                "messages_processed": 0, "cluster_count": 0,
                "noise_count": 0, "overview_generated": False}

    cluster_count = stats["cluster_count"]
    noise_count   = stats["noise_count"]
    total         = stats["total_messages"]

    # Step 2: Per-cluster summarization
    sum_result = await summarize_all_clusters(channel_id, provider)
    logger.info(
        f"Per-cluster summarization: {sum_result['processed']} ok, "
        f"{sum_result['failed']} failed")

    # Step 3: Cross-cluster overview
    overview_result = await generate_overview(channel_id, provider)
    if overview_result is None:
        logger.error(f"Overview generation failed ch:{channel_id}")
        return {"error": "Overview generation failed",
                "messages_processed": total, "cluster_count": cluster_count,
                "noise_count": noise_count, "overview_generated": False}

    # Step 4: Translate field names + save to channel_summaries
    channel_summary = translate_to_channel_summary(
        overview_result, cluster_count, noise_count)
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
