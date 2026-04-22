# utils/pipeline_worker.py
# Version 1.0.0
"""
Background pipeline worker for incremental segment processing (SOW v7.3.0 M3).

Polls all active channels every PIPELINE_POLL_INTERVAL seconds. For each:
  Stage 1 (segment): fires when idle gap or EMERGENCY_SEGMENT_THRESHOLD reached
  Stage 2 (embed): advances created → embedded
  Stage 3 (propositions): advances embedded → propositioned
  Stage 4 (fts index): advances propositioned → indexed

Per-channel lock prevents concurrent worker + !summary create. Worker is
controlled via _worker_stopped flag — toggled by !pipeline stop/start.

CREATED v1.0.0: Background pipeline worker (SOW v7.3.0 M3)
"""
import asyncio
import sqlite3
from config import DATABASE_PATH, PIPELINE_POLL_INTERVAL
from utils.logging_utils import get_logger

logger = get_logger('pipeline_worker')

_worker_stopped = False
_pipeline_locks = {}   # {channel_id: caller_str or None}
_worker_task = None    # asyncio.Task handle


def start_worker():
    """Spawn supervised pipeline task. Stores handle in _worker_task."""
    global _worker_task, _worker_stopped
    _worker_stopped = False
    _worker_task = asyncio.create_task(supervised_pipeline())
    logger.info("Pipeline worker started")
    return _worker_task


async def supervised_pipeline():
    """Crash-recovery wrapper. Restarts pipeline_worker on exception."""
    global _worker_stopped
    while not _worker_stopped:
        try:
            await pipeline_worker()
        except Exception as e:
            logger.error(f"Pipeline worker crashed: {e}")
            if not _worker_stopped:
                await asyncio.sleep(10)
    logger.info("Pipeline worker stopped")


async def pipeline_worker():
    """Main poll loop. Runs all four stages for each active channel."""
    while not _worker_stopped:
        for channel_id in get_active_channels():
            if not acquire_pipeline_lock(channel_id, "worker"):
                continue
            try:
                if should_segment(channel_id):
                    await _segment_channel(channel_id)
                await embed_segments(channel_id)
                await decompose_propositions(channel_id)
                await index_fts(channel_id)
            except Exception as e:
                logger.error(f"Worker error ch:{channel_id}: {e}")
            finally:
                release_pipeline_lock(channel_id)
        await asyncio.sleep(PIPELINE_POLL_INTERVAL)


def should_segment(channel_id):
    """Return True if segmentation should run for this channel."""
    from utils.pipeline_state import get_pipeline_state, get_unsegmented_count
    from config import MIN_SEGMENT_BATCH, EMERGENCY_SEGMENT_THRESHOLD, SEGMENT_GAP_MINUTES
    pipeline = get_pipeline_state(channel_id)
    unseg_count = get_unsegmented_count(channel_id)
    if unseg_count < MIN_SEGMENT_BATCH:
        return False
    last_msg_time = _get_latest_message_time(channel_id)
    if last_msg_time and pipeline["last_pipeline_run"]:
        if pipeline["last_pipeline_run"] >= last_msg_time:
            return False
    if unseg_count >= EMERGENCY_SEGMENT_THRESHOLD:
        return True
    if last_msg_time and _minutes_since(last_msg_time) > SEGMENT_GAP_MINUTES:
        return True
    return False


def acquire_pipeline_lock(channel_id, caller="worker"):
    """Acquire per-channel lock. Returns True on success."""
    if _pipeline_locks.get(channel_id) is not None:
        return False
    _pipeline_locks[channel_id] = caller
    return True


def release_pipeline_lock(channel_id):
    _pipeline_locks[channel_id] = None


def get_pipeline_lock_holder(channel_id):
    """Return current lock holder string or None."""
    return _pipeline_locks.get(channel_id)


def get_active_channels():
    """Return channel IDs that have a pipeline_state row."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute("SELECT channel_id FROM pipeline_state").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


async def _segment_channel(channel_id):
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    from utils.incremental_segmenter import incremental_segment
    provider = get_provider(SUMMARIZER_PROVIDER)
    count = await incremental_segment(channel_id, provider)
    if count:
        logger.info(f"Incremental segmentation: {count} new segs ch:{channel_id}")


async def embed_segments(channel_id):
    """Stage 2: embed syntheses for status='created' segments."""
    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute(
        "SELECT id, synthesis FROM segments WHERE channel_id=? AND status='created'",
        (channel_id,)).fetchall()
    conn.close()
    if not rows:
        return
    from utils.embedding_store import embed_texts_batch
    from utils.segment_store import store_segment_embedding, update_segment_status
    texts = [r[1] or "" for r in rows]
    results = await asyncio.to_thread(embed_texts_batch, texts, 1000)
    for idx, vec in results:
        if idx < len(rows):
            seg_id = rows[idx][0]
            await asyncio.to_thread(store_segment_embedding, seg_id, vec)
            await asyncio.to_thread(update_segment_status, seg_id, 'embedded')
    logger.info(f"Embedded {len(results)} segs ch:{channel_id}")


async def decompose_propositions(channel_id):
    """Stage 3: decompose status='embedded' segments into propositions."""
    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute(
        "SELECT id, synthesis FROM segments WHERE channel_id=? AND status='embedded'",
        (channel_id,)).fetchall()
    conn.close()
    if not rows:
        return
    from utils.proposition_decomposer import decompose_syntheses
    from utils.proposition_store import store_propositions, store_proposition_embedding
    from utils.embedding_store import embed_texts_batch
    from utils.segment_store import update_segment_status
    from config import PROPOSITION_BATCH_SIZE
    conn2 = sqlite3.connect(DATABASE_PATH)
    for seg_id, _ in rows:
        conn2.execute("DELETE FROM propositions WHERE segment_id=?", (seg_id,))
    conn2.commit()
    conn2.close()
    decomposed = await decompose_syntheses(rows, batch_size=PROPOSITION_BATCH_SIZE)
    prop_texts, prop_ids = [], []
    for seg_id, props in decomposed:
        new_ids = store_propositions(channel_id, seg_id, props)
        prop_ids.extend(new_ids)
        prop_texts.extend(props)
    if prop_texts:
        emb = await asyncio.to_thread(embed_texts_batch, prop_texts, 1000)
        for idx, vec in emb:
            if idx < len(prop_ids):
                await asyncio.to_thread(
                    store_proposition_embedding, prop_ids[idx], vec)
    for seg_id, _ in rows:
        await asyncio.to_thread(update_segment_status, seg_id, 'propositioned')
    logger.info(f"Propositioned {len(rows)} segs ch:{channel_id}")


async def index_fts(channel_id):
    """Stage 4: rebuild FTS5 index for status='propositioned' segments."""
    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute(
        "SELECT id FROM segments WHERE channel_id=? AND status='propositioned'",
        (channel_id,)).fetchall()
    conn.close()
    if not rows:
        return
    from utils.fts_search import populate_fts
    from utils.segment_store import update_segment_status
    await asyncio.to_thread(populate_fts, channel_id)
    for (seg_id,) in rows:
        await asyncio.to_thread(update_segment_status, seg_id, 'indexed')
    logger.info(f"FTS-indexed {len(rows)} segs ch:{channel_id}")


def _get_latest_message_time(channel_id):
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT MAX(created_at) FROM messages WHERE channel_id=? AND is_deleted=0",
            (channel_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _minutes_since(timestamp_str):
    if not timestamp_str:
        return 0
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        if not t.tzinfo:
            t = t.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - t).total_seconds() / 60
    except Exception:
        return 0
