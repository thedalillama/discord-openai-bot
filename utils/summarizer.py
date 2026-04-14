# utils/summarizer.py
# Version 4.2.0
"""
Summarization pipeline router.

Routes !summary create and !summary update to the cluster-based pipeline.

CHANGES v4.2.0: Populate FTS5 index after segmentation (SOW v6.2.0)
- MODIFIED: summarize_channel() — calls populate_fts(channel_id) via
  asyncio.to_thread() after run_segmentation_phase() succeeds (seg_count > 0).
  FTS5 failure does not abort the pipeline — it degrades BM25 to empty list.

CHANGES v4.1.0: Segment pipeline integration (SOW v6.0.0)
- MODIFIED: summarize_channel() — runs segmentation phase before clustering:
  load messages → run_segmentation_phase() → run_segment_clustering() →
  run_cluster_pipeline(pre_run_stats=...). Falls back to message-based
  clustering if segmentation produces no segments or segment clustering fails.

CHANGES v4.0.0: Dead code removal (SOW v5.10.0)
- REMOVED: _incremental_loop() — v4.x batch-and-delegate loop (dead since v3.0.0)
- REMOVED: _process_response() — v4.x parse/classify/normalize/validate (dead since v3.0.0)
- REMOVED: _repair_call() — v4.x one-retry repair prompt (dead since v3.0.0)
- REMOVED: _get_unsummarized_messages() — v4.x message query (dead since v3.0.0)
- REMOVED: _partial() — v4.x result builder (dead since v3.0.0)
- REMOVED: import of estimate_tokens (no longer needed)
- All removed functions were retained for rollback safety during v5 development.
  The v5 cluster pipeline has been live since v5.3.0 through v5.9.0.
  Git history preserves all deleted code.

CHANGES v3.1.0: Add quick_update_channel() for !summary update (SOW v5.4.0)
CHANGES v3.0.0: Route to cluster-based pipeline (SOW v5.3.0)
CHANGES v2.2.0: Batched cold start
CHANGES v2.1.0: Incremental path uses three-pass pipeline
CHANGES v2.0.0: Migrate incremental path to anyOf schema
CHANGES v1.9.0: Two-pass authoring for cold starts
CHANGES v1.1.0-v1.8.0: Three-layer pipeline, batch loop, noise filters
CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('summarizer')


async def summarize_channel(channel_id, batch_size=None, progress_fn=None):
    """Generate or update the structured summary for a channel.

    Segment pipeline: load messages → segment+synthesize (Gemini) →
    embed syntheses → UMAP+HDBSCAN on segments → per-cluster summarization →
    overview → classify → dedup → save.

    Falls back to message-based clustering if segmentation fails.
    batch_size is accepted but ignored. Retained for API compatibility.
    """
    from utils.cluster_overview import run_cluster_pipeline
    from utils.segmenter import run_segmentation_phase
    from utils.segment_store import run_segment_clustering
    from utils.message_store import get_channel_messages
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    provider = get_provider(SUMMARIZER_PROVIDER)
    try:
        messages = await asyncio.to_thread(get_channel_messages, channel_id)
        seg_count = await run_segmentation_phase(
            channel_id, messages, provider, progress_fn)
        if seg_count == 0:
            logger.warning(
                f"No segments created ch:{channel_id} — falling back to "
                f"message-based clustering")
            return await run_cluster_pipeline(channel_id, provider,
                                              progress_fn=progress_fn)
        from utils.fts_search import populate_fts
        await asyncio.to_thread(populate_fts, channel_id)
        seg_stats = await asyncio.to_thread(run_segment_clustering, channel_id)
        if seg_stats is None:
            logger.warning(
                f"Segment clustering failed ch:{channel_id} — falling back")
            return await run_cluster_pipeline(channel_id, provider,
                                              progress_fn=progress_fn)
        return await run_cluster_pipeline(channel_id, provider,
                                          progress_fn=progress_fn,
                                          pre_run_stats=seg_stats)
    except Exception as e:
        logger.error(f"Cluster pipeline failed ch:{channel_id}: {e}")
        return {"error": str(e), "messages_processed": 0,
                "cluster_count": 0, "noise_count": 0,
                "overview_generated": False}


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
