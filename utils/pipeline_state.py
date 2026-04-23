# utils/pipeline_state.py
# Version 1.3.0
"""
Pipeline state CRUD for v7.0.0 incremental pipeline (SOW v7.0.0 M1).

Tracks per-channel segmentation progress via the pipeline_state table.
Provides session bridge and unsummarized message queries for Layer 2
context injection.

CHANGES v1.3.0: Fix Layer 2 drainage by background worker
- MODIFIED: get_unsummarized_messages() — boundary is now the max message ID
  from clustered/unclustered segments (last !summary create run), not
  last_segmented_message_id. Worker indexing no longer drains the pool.
- MODIFIED: get_session_bridge_messages() — only exclude clustered/unclustered
  segments (already in always-on summary). Indexed segments stay in bridge.
CHANGES v1.2.0: Exclude indexed/clustered segments from session bridge (too aggressive — reverted)
CHANGES v1.1.0: Filter noise messages from Layer 2 injection

CREATED v1.0.0:
- get_pipeline_state() — auto-initializing CRUD for pipeline_state table
- save_pipeline_state() — upsert last_segmented_message_id + last_pipeline_run
- get_unsegmented_count() — COUNT(*) WHERE id > pointer (no counter drift)
- get_unsummarized_messages() — messages after segmentation pointer
- get_session_bridge_messages() — raw msgs from most recent session's segments
"""
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH, SESSION_GAP_MINUTES
from utils.logging_utils import get_logger

logger = get_logger('pipeline_state')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _minutes_between(t1_str, t2_str):
    """Minutes between two ISO timestamp strings. Returns 0 on parse failure."""
    if not t1_str or not t2_str:
        return 0
    try:
        t1 = datetime.fromisoformat(t1_str.replace('Z', '+00:00'))
        t2 = datetime.fromisoformat(t2_str.replace('Z', '+00:00'))
        if t1.tzinfo and not t2.tzinfo:
            t2 = t2.replace(tzinfo=t1.tzinfo)
        elif t2.tzinfo and not t1.tzinfo:
            t1 = t1.replace(tzinfo=t2.tzinfo)
        return abs((t2 - t1).total_seconds()) / 60
    except Exception:
        return 0


def get_pipeline_state(channel_id):
    """Return pipeline state dict, auto-initializing if missing.

    If no row exists, derives last_segmented_message_id from the max
    last_message_id in the segments table (handles existing v6 channels).
    Falls back to 0 if no segments exist.

    Returns dict with keys: last_segmented_message_id, last_pipeline_run,
    created_at.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT last_segmented_message_id, last_pipeline_run, created_at "
            "FROM pipeline_state WHERE channel_id=?",
            (channel_id,)).fetchone()
        if row:
            return {
                "last_segmented_message_id": row[0] or 0,
                "last_pipeline_run": row[1],
                "created_at": row[2],
            }
        # Auto-initialize from existing segments (v6 channel migration)
        max_row = conn.execute(
            "SELECT MAX(last_message_id) FROM segments WHERE channel_id=?",
            (channel_id,)).fetchone()
        pointer = (max_row[0] or 0) if max_row else 0
        created_at = _now()
        conn.execute(
            "INSERT OR IGNORE INTO pipeline_state "
            "(channel_id, last_segmented_message_id, last_pipeline_run, created_at) "
            "VALUES (?,?,NULL,?)",
            (channel_id, pointer, created_at))
        conn.commit()
        logger.info(
            f"Initialized pipeline_state ch:{channel_id} pointer={pointer}")
        return {
            "last_segmented_message_id": pointer,
            "last_pipeline_run": None,
            "created_at": created_at,
        }
    finally:
        conn.close()


def save_pipeline_state(channel_id, last_segmented_message_id,
                        last_pipeline_run=None):
    """Upsert pipeline state for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT INTO pipeline_state "
            "(channel_id, last_segmented_message_id, last_pipeline_run, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET "
            "  last_segmented_message_id=excluded.last_segmented_message_id, "
            "  last_pipeline_run=excluded.last_pipeline_run",
            (channel_id, last_segmented_message_id, last_pipeline_run, _now()))
        conn.commit()
    finally:
        conn.close()


def get_unsegmented_count(channel_id):
    """Count messages after last_segmented_message_id. Always from DB."""
    state = get_pipeline_state(channel_id)
    pointer = state["last_segmented_message_id"]
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM messages "
            "WHERE channel_id=? AND id > ? AND is_deleted=0",
            (channel_id, pointer)).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _is_layer2_noise(content, is_bot):
    """Return True if a message should be excluded from Layer 2 injection.
    Matches the same logic as _seed_history_from_db() in discord_loader.py.
    """
    if not content:
        return True
    if content.startswith('!'):
        return True
    if content.startswith('ℹ️') or content.startswith('⚙️'):
        return True
    return False


def get_unsummarized_messages(channel_id):
    """Messages after the last !summary create run, chronological.

    Boundary = max message ID in any clustered/unclustered segment. This
    prevents the background worker (which advances last_segmented_message_id)
    from draining the unsummarized pool. Only !summary create, which produces
    clustered segments, moves this boundary.

    Filters ℹ️/⚙️ bot output and !commands.
    Returns list of dicts: id, author, content, created_at, is_bot.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT MAX(m.id) FROM segment_messages sm "
            "JOIN messages m ON m.id=sm.message_id "
            "JOIN segments s ON s.id=sm.segment_id "
            "WHERE s.channel_id=? AND s.status IN ('clustered','unclustered')",
            (channel_id,)).fetchone()
        pointer = row[0] if row and row[0] else 0
        rows = conn.execute(
            "SELECT id, author_name, content, created_at, is_bot_author "
            "FROM messages WHERE channel_id=? AND id > ? AND is_deleted=0 "
            "ORDER BY id ASC",
            (channel_id, pointer)).fetchall()
        return [
            {"id": r[0], "author": r[1], "content": r[2],
             "created_at": r[3], "is_bot": bool(r[4])}
            for r in rows
            if not _is_layer2_noise(r[2], bool(r[4]))
        ]
    finally:
        conn.close()


def get_session_bridge_messages(channel_id):
    """Raw messages from the most recent conversation session's segments.

    Walks backward from the most recent segment until a gap exceeding
    SESSION_GAP_MINUTES is found. Returns source messages for all segments
    in that session, chronological.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        segments = conn.execute(
            "SELECT id, first_message_at, last_message_at FROM segments "
            "WHERE channel_id=? "
            "AND status NOT IN ('clustered', 'unclustered') "
            "ORDER BY first_message_at ASC",
            (channel_id,)).fetchall()
        if not segments:
            return []
        session = [segments[-1]]
        for i in range(len(segments) - 2, -1, -1):
            gap = _minutes_between(
                segments[i][2], segments[i + 1][1])
            if gap > SESSION_GAP_MINUTES:
                break
            session.append(segments[i])
        session.reverse()
        seg_ids = [s[0] for s in session]
        messages = []
        for seg_id in seg_ids:
            rows = conn.execute(
                "SELECT m.id, m.author_name, m.content, m.created_at, "
                "       m.is_bot_author "
                "FROM segment_messages sm "
                "JOIN messages m ON m.id=sm.message_id "
                "WHERE sm.segment_id=? ORDER BY sm.position ASC",
                (seg_id,)).fetchall()
            for r in rows:
                if not _is_layer2_noise(r[2], bool(r[4])):
                    messages.append({
                        "id": r[0], "author": r[1], "content": r[2],
                        "created_at": r[3], "is_bot": bool(r[4]),
                    })
        return messages
    finally:
        conn.close()
