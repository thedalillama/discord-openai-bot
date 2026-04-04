# utils/cluster_update.py
# Version 1.0.0
"""
Quick update pipeline: re-summarize dirty clusters + regenerate overview.

Selectively re-summarizes only clusters marked needs_resummarize=1, then
re-runs classify → overview → dedup → answered-Q → save.
Does NOT re-cluster — cluster membership is preserved.

Called from summarizer.quick_update_channel() for !summary update.

CREATED v1.0.0: Selective re-summarization for incremental updates (SOW v5.4.0)
"""
import asyncio
import json
from utils.logging_utils import get_logger
from utils.cluster_store import (
    get_dirty_clusters, mark_clusters_clean,
    get_unassigned_message_count, get_clusters_for_channel,
)
from utils.cluster_summarizer import summarize_cluster
from utils.cluster_overview import (
    _collect_structured_items, generate_overview, translate_to_channel_summary,
)
from utils.cluster_classifier import classify_overview_items
from utils.cluster_qa import deduplicate_summary, remove_answered_questions
from utils.summary_store import get_channel_summary, save_channel_summary
from utils.message_store import get_channel_messages

logger = get_logger('cluster_update')


async def run_quick_update(channel_id, provider, progress_fn=None):
    """Re-summarize dirty clusters and regenerate the channel overview.

    Returns dict: updated_count, unassigned_count, overview_generated,
    error, message.
    """
    async def _p(msg):
        logger.info(f"[quick_update ch:{channel_id}] {msg}")
        if progress_fn:
            await progress_fn(msg)

    try:
        dirty = await asyncio.to_thread(get_dirty_clusters, channel_id)
        if not dirty:
            unassigned = await asyncio.to_thread(
                get_unassigned_message_count, channel_id)
            return {
                "updated_count": 0, "unassigned_count": unassigned,
                "overview_generated": False,
                "error": None, "message": "No dirty clusters",
            }

        await _p(f"Re-summarizing {len(dirty)} updated cluster(s)...")
        processed = failed = 0
        for cluster in dirty:
            result = await summarize_cluster(cluster["id"], channel_id, provider)
            if result:
                processed += 1
            else:
                failed += 1
                logger.warning(f"Re-summarize failed: {cluster['id']}")
        logger.info(f"Re-summarized {processed} ok, {failed} failed")

        await asyncio.to_thread(mark_clusters_clean, [c["id"] for c in dirty])

        all_clusters = await asyncio.to_thread(get_clusters_for_channel, channel_id)

        await _p("Classifying structured items...")
        aggregated = _collect_structured_items(all_clusters)
        filtered = await classify_overview_items(aggregated)

        await _p("Generating channel overview...")
        overview_result = await generate_overview(channel_id, provider, all_clusters)
        if overview_result is None:
            overview_result = {
                "overview": "Channel overview unavailable.", "participants": []
            }

        # Preserve cluster_count + noise_message_count — we didn't re-cluster
        existing_json, _ = await asyncio.to_thread(get_channel_summary, channel_id)
        existing = json.loads(existing_json) if existing_json else {}
        cluster_count = existing.get("cluster_count", len(all_clusters))
        noise_count = existing.get("noise_message_count", 0)

        merged = {
            "overview":       overview_result.get("overview", ""),
            "participants":   overview_result.get("participants", []),
            "decisions":      filtered.get("decisions", []),
            "key_facts":      filtered.get("key_facts", []),
            "action_items":   filtered.get("action_items", []),
            "open_questions": filtered.get("open_questions", []),
        }
        channel_summary = translate_to_channel_summary(
            merged, cluster_count, noise_count)

        await _p("Deduplicating and checking answered questions...")
        channel_summary = await deduplicate_summary(channel_summary)
        channel_summary = await remove_answered_questions(channel_summary)

        all_msgs = await asyncio.to_thread(get_channel_messages, channel_id)
        last_id = max((m.id for m in all_msgs), default=0)
        await asyncio.to_thread(
            save_channel_summary, channel_id,
            json.dumps(channel_summary), len(all_msgs), last_id)

        unassigned = await asyncio.to_thread(
            get_unassigned_message_count, channel_id)

        logger.info(
            f"Quick update complete ch:{channel_id}: "
            f"{len(dirty)} clusters updated, {unassigned} unassigned")
        return {
            "updated_count": len(dirty), "unassigned_count": unassigned,
            "overview_generated": True, "error": None, "message": "OK",
        }

    except Exception as e:
        logger.error(f"Quick update failed ch:{channel_id}: {e}")
        return {
            "updated_count": 0, "unassigned_count": 0,
            "overview_generated": False, "error": str(e), "message": "Failed",
        }
