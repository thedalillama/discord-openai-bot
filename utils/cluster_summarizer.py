# utils/cluster_summarizer.py
# Version 1.2.0
"""
Per-cluster LLM summarization pipeline for v5.2.0.

Calls Gemini once per cluster to extract label, summary, decisions,
key_facts, action_items, and open_questions. Results stored in the
clusters table summary column as a JSON blob.

CHANGES v1.2.0: Log segment count instead of stale message_count in v6 path
CHANGES v1.1.0: Segment-aware summarization (SOW v6.0.0)
- MODIFIED: summarize_cluster() — add use_segments=False parameter.
  When True, loads segment syntheses via get_cluster_segment_ids() +
  get_segments_by_ids(). M-label format: "M1 [Topic]: synthesis text..."
- MODIFIED: summarize_all_clusters() — pass use_segments through.

CREATED v1.0.0: Per-cluster Gemini summarization (SOW v5.2.0)
- summarize_cluster(): single Gemini call for one cluster
- summarize_all_clusters(): sequential loop over all channel clusters
"""
import json
import asyncio
from utils.logging_utils import get_logger
from utils.cluster_store import (
    get_cluster_message_ids, get_clusters_for_channel,
    get_messages_by_ids, update_cluster_label_summary)

logger = get_logger('cluster_summarizer')

MAX_MESSAGES_PER_CLUSTER = 50

CLUSTER_SYSTEM_PROMPT = """\
You are a conversation summarizer. You will receive a group of related
messages from a Discord channel. These messages are about the same
general topic (grouped by semantic similarity). Your job is to extract
durable information.

Return a JSON object with the specified schema.

FIELD DEFINITIONS:
- summary: 1-3 sentence summary of what was discussed and any conclusions
  reached. Write this FIRST.
- label: A concise topic title (3-8 words). Examples: "Database Selection
  and Hosting", "Animal Evolution Discussion", "Sprint Planning for Q2".
- decisions: Explicit agreements on courses of action. NOT factual lookups,
  casual preferences, or hypothetical discussions.
- key_facts: Durable facts, constraints, metrics, or reference information
  established in the discussion.
- action_items: Tasks someone committed to or was assigned. Include owner
  if identifiable.
- open_questions: Unresolved questions requiring future answers. NOT
  rhetorical, trivia, or already-answered questions.
- status: "active" if the topic is ongoing or has open items; "archived"
  if the discussion concluded with no pending work.
- source_message_ids: Use the M-labels (M1, M2, etc.) provided with each
  message.

RULES:
- If a field has no items, return an empty array.
- Ignore bot self-descriptions, capability statements, and filler.
- Focus on human-generated content; bot responses provide context only.
- Be concise. Each field captures the essence, not every message.
"""

_ITEM = {
    "type": "object",
    "properties": {
        "id":                 {"type": "string"},
        "text":               {"type": "string"},
        "source_message_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "text"],
}

_ACTION_ITEM = {
    "type": "object",
    "properties": {
        "id":                 {"type": "string"},
        "text":               {"type": "string"},
        "owner":              {"type": "string"},
        "status":             {"type": "string", "enum": ["open", "completed"]},
        "source_message_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "text"],
}

CLUSTER_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary":        {"type": "string"},
        "label":          {"type": "string"},
        "status":         {"type": "string", "enum": ["active", "archived"]},
        "decisions":      {"type": "array", "items": _ITEM},
        "key_facts":      {"type": "array", "items": _ITEM},
        "action_items":   {"type": "array", "items": _ACTION_ITEM},
        "open_questions": {"type": "array", "items": _ITEM},
    },
    "required": ["summary", "label", "status", "decisions",
                 "key_facts", "action_items", "open_questions"],
}


async def summarize_cluster(cluster_id, channel_id, provider, use_segments=False):
    """Summarize a single cluster with one Gemini call.

    Returns dict with label, summary, decisions, key_facts, action_items,
    open_questions, status — or None on failure.
    When use_segments=True, loads segment syntheses instead of raw messages.
    """
    if use_segments:
        from utils.segment_store import get_cluster_segment_ids, get_segments_by_ids
        seg_ids = await asyncio.to_thread(get_cluster_segment_ids, cluster_id)
        if not seg_ids:
            logger.warning(f"No segments for cluster {cluster_id}")
            return None
        segs = await asyncio.to_thread(get_segments_by_ids, seg_ids)
        if not segs:
            return None
        truncated = len(segs) > MAX_MESSAGES_PER_CLUSTER
        if truncated:
            segs = segs[-MAX_MESSAGES_PER_CLUSTER:]
        lines = []
        if truncated:
            lines.append(f"NOTE: Showing last {MAX_MESSAGES_PER_CLUSTER} segments.\n")
        for i, seg in enumerate(segs, 1):
            lbl = seg.get("topic_label") or f"Segment {i}"
            lines.append(f"M{i} [{lbl}]: {seg['synthesis']}")
    else:
        message_ids = await asyncio.to_thread(get_cluster_message_ids, cluster_id)
        if not message_ids:
            logger.warning(f"No messages for cluster {cluster_id}")
            return None
        messages = await asyncio.to_thread(get_messages_by_ids, message_ids)
        if not messages:
            logger.warning(f"Could not fetch messages for cluster {cluster_id}")
            return None
        truncated = len(messages) > MAX_MESSAGES_PER_CLUSTER
        if truncated:
            messages = messages[-MAX_MESSAGES_PER_CLUSTER:]
        lines = []
        if truncated:
            lines.append(
                f"NOTE: This cluster contains {len(message_ids)} messages. "
                f"The {MAX_MESSAGES_PER_CLUSTER} most recent are shown. "
                f"Earlier messages covered similar topics.\n")
        for i, (_, author, content, created_at) in enumerate(messages, 1):
            date = (created_at or "")[:10]
            lines.append(f"M{i} [{date}] {author}: {content}")
    formatted = "\n".join(lines)

    for attempt in range(2):
        try:
            response = await provider.generate_ai_response(
                messages=[
                    {"role": "system", "content": CLUSTER_SYSTEM_PROMPT},
                    {"role": "user",   "content": formatted},
                ],
                max_tokens=2048,
                temperature=0.3,
                channel_id=channel_id,
                response_mime_type="application/json",
                response_json_schema=CLUSTER_SUMMARY_SCHEMA,
                use_json_schema=True,
            )
            result = json.loads(response) if isinstance(response, str) else response
            summary_json = json.dumps({
                "text":           result.get("summary", ""),
                "decisions":      result.get("decisions", []),
                "key_facts":      result.get("key_facts", []),
                "action_items":   result.get("action_items", []),
                "open_questions": result.get("open_questions", []),
            })
            await asyncio.to_thread(
                update_cluster_label_summary,
                cluster_id,
                result.get("label", ""),
                summary_json,
                result.get("status", "active"))
            if use_segments:
                result["segment_count"] = len(seg_ids)
            return result
        except Exception as e:
            logger.warning(
                f"summarize_cluster {cluster_id} attempt {attempt+1} failed: {e}")
    return None


async def summarize_all_clusters(channel_id, provider, progress_fn=None,
                                use_segments=False):
    """Summarize all clusters for a channel sequentially.

    Returns dict: processed, failed counts.
    """
    clusters = await asyncio.to_thread(get_clusters_for_channel, channel_id)
    if not clusters:
        return {"processed": 0, "failed": 0}
    total = len(clusters)
    processed = failed = 0
    for i, cluster in enumerate(clusters):
        result = await summarize_cluster(
            cluster["id"], channel_id, provider, use_segments=use_segments)
        if result:
            processed += 1
            count_str = (f"{result.get('segment_count')} segs"
                         if result.get('segment_count') is not None
                         else f"{cluster['message_count']} msgs")
            logger.info(
                f"Cluster {i+1}/{total}: '{result.get('label', '?')}' ({count_str})")
        else:
            failed += 1
            logger.warning(f"Cluster {i+1}/{total}: failed")
        if progress_fn and (i + 1) % 10 == 0:
            await progress_fn(f"Summarized {i+1}/{total} clusters...")
    logger.info(
        f"summarize_all_clusters ch:{channel_id}: "
        f"{processed} ok, {failed} failed")
    return {"processed": processed, "failed": failed}
