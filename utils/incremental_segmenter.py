# utils/incremental_segmenter.py
# Version 1.0.0
"""
Incremental segmentation for the background pipeline worker (SOW v7.3.0 M3).

Segments only new messages (after last_segmented_message_id). Passes last 5
existing segments to Gemini for continuity — supports extends_existing to
append new messages to the most recent segment rather than starting a new one.

Note: get_recent_segments lives here (not segment_store.py) — 250-line limit.
CREATED v1.0.0: Incremental segmentation pipeline (SOW v7.3.0 M3)
"""
import json
import asyncio
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH, SEGMENT_GAP_MINUTES
from utils.logging_utils import get_logger

logger = get_logger('incremental_segmenter')

INCREMENTAL_SYSTEM_PROMPT = """\
You are segmenting new Discord messages. You will receive:
1. RECENT SEGMENTS — last few existing segments (context only, do not re-segment)
2. NEW MESSAGES — unsegmented messages to process, indexed [0], [1], ...

RULES:
- Group consecutive new messages about the same topic into segments.
- Short acknowledgments (yes, ok, agreed) belong to the topic they respond to.
- If the FIRST new messages clearly continue the most recent existing segment,
  set extends_existing=true and extends_segment_id to that segment's ID.
- For each segment: topic_label (3-8 words), synthesis (2-4 sentences resolving
  all implicit references — "yes" → what was agreed, pronouns → names).
- Use start_index and end_index into the NEW MESSAGES array (0-based).

Return a JSON array of segment objects.
"""

INCREMENTAL_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "start_index":        {"type": "integer"},
            "end_index":          {"type": "integer"},
            "topic_label":        {"type": "string"},
            "synthesis":          {"type": "string"},
            "extends_existing":   {"type": "boolean"},
            "extends_segment_id": {"type": "string"},
        },
        "required": ["start_index", "end_index", "topic_label", "synthesis"],
    },
}


def get_unsegmented_messages_for_pipeline(channel_id, pointer):
    """All messages after pointer not yet assigned to any segment."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, author_name, content, created_at FROM messages "
            "WHERE channel_id=? AND id > ? AND is_deleted=0 "
            "AND id NOT IN (SELECT message_id FROM segment_messages) "
            "ORDER BY id ASC",
            (channel_id, pointer)).fetchall()
        return [{"id": r[0], "author": r[1], "content": r[2], "created_at": r[3]}
                for r in rows if r[2] and r[2].strip()]
    finally:
        conn.close()


def get_recent_segments(channel_id, limit=5):
    """Return last N segments for continuity context, newest-first."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, topic_label, synthesis FROM segments "
            "WHERE channel_id=? ORDER BY last_message_at DESC LIMIT ?",
            (channel_id, limit)).fetchall()
        return [{"id": r[0], "topic_label": r[1], "synthesis": r[2]} for r in rows]
    finally:
        conn.close()


def validate_segments(segments, messages):
    """Check indices are in-range and non-overlapping."""
    if not segments:
        return False
    n = len(messages)
    seen = set()
    for seg in segments:
        s, e = seg.get("start_index", -1), seg.get("end_index", -1)
        if s < 0 or e < s or e >= n:
            return False
        for i in range(s, e + 1):
            if i in seen:
                return False
            seen.add(i)
    return True


def fallback_time_gap(messages):
    """Segment by time gap when Gemini fails. Returns synthetic segments."""
    if not messages:
        return []
    segs, start = [], 0
    for i in range(1, len(messages)):
        t1, t2 = messages[i - 1]["created_at"], messages[i]["created_at"]
        try:
            d1 = datetime.fromisoformat(t1.replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(t2.replace("Z", "+00:00"))
            if not d1.tzinfo:
                d1 = d1.replace(tzinfo=timezone.utc)
            if not d2.tzinfo:
                d2 = d2.replace(tzinfo=timezone.utc)
            gap = (d2 - d1).total_seconds() / 60
        except Exception:
            gap = 0
        if gap > SEGMENT_GAP_MINUTES:
            segs.append({"start_index": start, "end_index": i - 1,
                         "topic_label": "Conversation", "synthesis": ""})
            start = i
    segs.append({"start_index": start, "end_index": len(messages) - 1,
                 "topic_label": "Conversation", "synthesis": ""})
    return segs


def create_new_segment(channel_id, seg, messages):
    """Store a new segment from incremental segmentation."""
    from utils.segment_store import store_segments
    msg_slice = messages[seg["start_index"]:seg["end_index"] + 1]
    if not msg_slice:
        return
    store_segments(channel_id, [{
        "topic_label":      seg.get("topic_label", ""),
        "synthesis":        seg.get("synthesis", ""),
        "message_ids":      [m["id"] for m in msg_slice],
        "first_message_at": msg_slice[0]["created_at"],
        "last_message_at":  msg_slice[-1]["created_at"],
    }])


def extend_existing_segment(channel_id, seg, messages):
    """Atomically extend a segment with new messages, reset status to 'created'."""
    seg_id = seg.get("extends_segment_id")
    if not seg_id:
        return
    new_msgs = messages[seg["start_index"]:seg["end_index"] + 1]
    if not new_msgs:
        return
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT MAX(position) FROM segment_messages WHERE segment_id=?",
            (seg_id,)).fetchone()
        pos = (row[0] or -1) + 1
        for m in new_msgs:
            conn.execute(
                "INSERT OR IGNORE INTO segment_messages"
                "(segment_id, message_id, position) VALUES(?,?,?)",
                (seg_id, m["id"], pos))
            pos += 1
        last_id, last_at = new_msgs[-1]["id"], new_msgs[-1]["created_at"]
        conn.execute(
            "UPDATE segments SET synthesis=?, status='created', "
            "last_message_id=?, last_message_at=?, "
            "message_count=(SELECT COUNT(*) FROM segment_messages WHERE segment_id=?) "
            "WHERE id=?",
            (seg.get("synthesis", ""), last_id, last_at, seg_id, seg_id))
        conn.execute("DELETE FROM propositions WHERE segment_id=?", (seg_id,))
        conn.execute("DELETE FROM segments_fts WHERE segment_id=?", (seg_id,))
        conn.commit()
        logger.info(f"Extended seg {seg_id} with {len(new_msgs)} msgs")
    except Exception as e:
        conn.rollback()
        logger.warning(f"extend_existing_segment failed {seg_id}: {e}")
    finally:
        conn.close()


async def segment_with_context(messages, context, channel_id, provider):
    """Call Gemini to segment messages with recent segment context."""
    lines = []
    if context:
        ctx_lines = "\n".join(
            f"  [{c['id']}] {c['topic_label']}: {(c['synthesis'] or '')[:200]}"
            for c in reversed(context))
        lines.append(f"RECENT SEGMENTS:\n{ctx_lines}\n")
        last_id = context[0]["id"] if context else ""
        lines.append(
            f"Most recent segment ID: {last_id} — use as extends_segment_id "
            f"if first messages continue it.\n")
    lines.append("NEW MESSAGES:")
    for i, m in enumerate(messages):
        ts = (m.get("created_at") or "")[:16].replace("T", " ")
        lines.append(f"[{i}] [{ts}] {m['author']}: {m['content']}")
    response = await provider.generate_ai_response(
        messages=[
            {"role": "system", "content": INCREMENTAL_SYSTEM_PROMPT},
            {"role": "user",   "content": "\n".join(lines)},
        ],
        max_tokens=4096, temperature=0.2, channel_id=channel_id,
        response_mime_type="application/json",
        response_json_schema=INCREMENTAL_SCHEMA,
        use_json_schema=True,
    )
    result = json.loads(response) if isinstance(response, str) else response
    return result if isinstance(result, list) else []


async def incremental_segment(channel_id, provider):
    """Segment new messages incrementally. Returns count of new segments created."""
    from utils.pipeline_state import get_pipeline_state, save_pipeline_state
    from config import MIN_SEGMENT_BATCH, MAX_SEGMENT_BATCH
    pipeline = get_pipeline_state(channel_id)
    pointer = pipeline["last_segmented_message_id"]
    unsegmented = get_unsegmented_messages_for_pipeline(channel_id, pointer)
    if len(unsegmented) < MIN_SEGMENT_BATCH:
        return 0
    to_segment = unsegmented[:MAX_SEGMENT_BATCH]
    context = get_recent_segments(channel_id, limit=5)
    result = None
    for attempt in range(2):
        try:
            result = await segment_with_context(to_segment, context, channel_id, provider)
            if result:
                break
        except Exception as e:
            logger.warning(f"incremental_segment attempt {attempt+1} ch:{channel_id}: {e}")
    if not result:
        result = fallback_time_gap(to_segment)
    if not validate_segments(result, to_segment):
        logger.warning(f"Segment validation failed ch:{channel_id} — skipping")
        return 0
    created = 0
    for seg in result:
        if seg.get("extends_existing") and seg.get("extends_segment_id"):
            extend_existing_segment(channel_id, seg, to_segment)
        else:
            create_new_segment(channel_id, seg, to_segment)
            created += 1
    save_pipeline_state(
        channel_id,
        last_segmented_message_id=to_segment[-1]["id"],
        last_pipeline_run=datetime.now(timezone.utc).isoformat())
    return created
