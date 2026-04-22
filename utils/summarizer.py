# utils/summarizer.py
# Version 4.7.0
"""
Summarization pipeline router.

Routes !summary create and !summary update to the cluster-based pipeline.

CHANGES v4.7.0: Pipeline lock for !summary create (SOW v7.3.0 M3)
- MODIFIED: summarize_channel() — acquires pipeline lock before running.
  force=True polls every 2s (up to 30s) waiting for worker to release.
  Returns error dict if lock cannot be acquired.
CHANGES v4.6.0: Set segment status after each pipeline stage (SOW v7.1.0 M2)
CHANGES v4.5.0: Use ProcessPoolExecutor for run_segment_clustering() (GIL-free UMAP)
CHANGES v4.4.0: Save pipeline_state after successful !summary create (SOW v7.0.0)
CHANGES v4.3.0: Run proposition decomposition phase after FTS5 (SOW v6.3.0)
CHANGES v4.2.0: Populate FTS5 index after segmentation (SOW v6.2.0)
CHANGES v4.1.0: Segment pipeline integration (SOW v6.0.0)
CHANGES v4.0.0: Dead code removal (SOW v5.10.0)
CHANGES v3.1.0: Add quick_update_channel() for !summary update (SOW v5.4.0)
CHANGES v3.0.0: Route to cluster-based pipeline (SOW v5.3.0)
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('summarizer')


async def summarize_channel(channel_id, batch_size=None, progress_fn=None,
                            force=False):
    """Generate or update the structured summary for a channel.

    Acquires the pipeline lock before running. If force=True, waits up to 30s
    for the worker to release. batch_size is accepted but ignored.
    """
    from utils.pipeline_worker import (
        acquire_pipeline_lock, release_pipeline_lock, get_pipeline_lock_holder)
    if not force:
        if not acquire_pipeline_lock(channel_id, "summary"):
            holder = get_pipeline_lock_holder(channel_id)
            return {"error": (
                f"Pipeline is processing (locked by {holder}). "
                "Use `!summary create force` to override."
            ), "messages_processed": 0, "cluster_count": 0,
               "noise_count": 0, "overview_generated": False}
    else:
        deadline = asyncio.get_event_loop().time() + 30
        while True:
            if acquire_pipeline_lock(channel_id, "summary"):
                break
            if asyncio.get_event_loop().time() >= deadline:
                return {"error": "Timed out waiting for pipeline lock (30s).",
                        "messages_processed": 0, "cluster_count": 0,
                        "noise_count": 0, "overview_generated": False}
            await asyncio.sleep(2)
    try:
        from utils.cluster_overview import run_cluster_pipeline
        from utils.segmenter import run_segmentation_phase
        from utils.segment_store import run_segment_clustering
        from utils.message_store import get_channel_messages
        from ai_providers import get_provider
        from config import SUMMARIZER_PROVIDER
        provider = get_provider(SUMMARIZER_PROVIDER)
        messages = await asyncio.to_thread(get_channel_messages, channel_id)
        max_msg_id = messages[-1].id if messages else 0
        seg_count = await run_segmentation_phase(
            channel_id, messages, provider, progress_fn)
        if seg_count == 0:
            logger.warning(
                f"No segments created ch:{channel_id} — falling back to "
                f"message-based clustering")
            result = await run_cluster_pipeline(channel_id, provider,
                                               progress_fn=progress_fn)
        else:
            from utils.fts_search import populate_fts
            from utils.proposition_decomposer import run_proposition_phase
            from utils.segment_store import update_channel_segment_status
            await asyncio.to_thread(
                update_channel_segment_status, channel_id, 'created', 'embedded')
            await asyncio.to_thread(populate_fts, channel_id)
            prop_count = await run_proposition_phase(channel_id, progress_fn)
            if prop_count == 0:
                logger.warning(
                    f"Proposition phase produced 0 props ch:{channel_id} "
                    f"— retrieval degrades to dense+BM25")
            await asyncio.to_thread(
                update_channel_segment_status, channel_id, 'embedded', 'propositioned')
            await asyncio.to_thread(
                update_channel_segment_status, channel_id, 'propositioned', 'indexed')
            from utils.cluster_engine import _cluster_pool
            seg_stats = await asyncio.get_running_loop().run_in_executor(
                _cluster_pool, run_segment_clustering, channel_id)
            if seg_stats is None:
                logger.warning(
                    f"Segment clustering failed ch:{channel_id} — falling back")
                result = await run_cluster_pipeline(channel_id, provider,
                                                   progress_fn=progress_fn)
            else:
                result = await run_cluster_pipeline(channel_id, provider,
                                                    progress_fn=progress_fn,
                                                    pre_run_stats=seg_stats)
        if not result.get("error") and max_msg_id:
            from utils.pipeline_state import save_pipeline_state
            from datetime import datetime, timezone
            await asyncio.to_thread(
                save_pipeline_state, channel_id, max_msg_id,
                datetime.now(timezone.utc).isoformat())
            logger.info(
                f"Pipeline state updated ch:{channel_id} pointer={max_msg_id}")
        return result
    except Exception as e:
        logger.error(f"Cluster pipeline failed ch:{channel_id}: {e}")
        return {"error": str(e), "messages_processed": 0,
                "cluster_count": 0, "noise_count": 0,
                "overview_generated": False}
    finally:
        release_pipeline_lock(channel_id)


async def quick_update_channel(channel_id, progress_fn=None):
    """Re-summarize dirty clusters only. Called by !summary update."""
    from utils.cluster_update import run_quick_update
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    provider = get_provider(SUMMARIZER_PROVIDER)
    try:
        return await run_quick_update(channel_id, provider,
                                      progress_fn=progress_fn)
    except Exception as e:
        logger.error(f"Quick update failed ch:{channel_id}: {e}")
        return {"updated_count": 0, "unassigned_count": 0,
                "overview_generated": False, "error": str(e), "message": "Failed"}
