# utils/segmenter.py
# Version 1.0.2
"""
Conversation segmentation + synthesis via Gemini (SOW v6.0.0).

CHANGES v1.0.2: Relax coverage check (warn, not raise); truncate synthesis at 24000 chars before embed
CHANGES v1.0.1: Use GEMINI_MAX_TOKENS for segmentation call (was hardcoded 8192)
CREATED v1.0.0: Segmentation pipeline (SOW v6.0.0)
- SEGMENTATION_SYSTEM_PROMPT: Gemini prompt for combined segment+synthesize
- SEGMENTATION_SCHEMA: JSON schema for structured output
- segment_and_synthesize(): main entry — processes messages in batches,
  calls Gemini per batch with overlap handling, returns segment dicts
- run_segmentation_phase(): async orchestrator — segment, embed, store
- _build_segmentation_prompt(): format messages with local indices for Gemini
- _parse_segments(): validate Gemini output covers all indices
- _fallback_time_gap(): time-gap segmentation when LLM fails
- _is_segmentable(): filter for segmentation (lighter than embedding filter)
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('segmenter')

SEGMENTATION_SYSTEM_PROMPT = """\
You are analyzing a Discord conversation to identify topical segments and \
summarize each one.

SEGMENTATION RULES:
- A segment is a group of consecutive messages about the same topic.
- Short acknowledgments (yes, ok, agreed, thanks) belong to the topic they \
respond to — never a separate segment.
- Topic shifts happen when the conversation moves to a substantially different \
subject.
- Let the conversation determine natural segment sizes. A 2-message exchange \
and a 40-message thread are both valid segments.
- Messages from [BOT] authors are part of the conversation — include them in \
segments with the messages they respond to.

SYNTHESIS RULES:
- For each segment, write a 2-4 sentence summary that captures the COMPLETE \
meaning of the exchange.
- Resolve ALL implicit references: if someone says "yes", state what they \
agreed to. If someone says "that one", state which option.
- Include participant names and any decisions, facts, or commitments.
- The synthesis must be understandable WITHOUT reading the original messages.

Return a JSON array of segments, ordered by start_index.\
"""

SEGMENTATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "start_index": {"type": "integer"},
            "end_index":   {"type": "integer"},
            "topic_label": {"type": "string"},
            "synthesis":   {"type": "string"},
        },
        "required": ["start_index", "end_index", "topic_label", "synthesis"],
    },
}


def _is_segmentable(msg):
    """True if message should be included in segmentation.

    Lighter than should_skip_embedding — short messages like "yes" are kept
    since they carry meaning when synthesized in context.
    """
    content = (msg.content or "").strip()
    if not content:
        return False
    if content.startswith(('!', 'ℹ️', '⚙️')):
        return False
    if content.lower() == "[original message deleted]":
        return False
    return not getattr(msg, 'is_deleted', False)


def _build_segmentation_prompt(indexed_msgs):
    """Format (local_index, msg) pairs for Gemini segmentation call."""
    lines = []
    for i, msg in indexed_msgs:
        ts = (msg.created_at or "")[:16].replace("T", " ")
        lines.append(f"[{i}] [{ts}] {msg.author_name}: {msg.content}")
    return "\n".join(lines)


def _parse_segments(response_data, n_messages):
    """Validate Gemini output covers local indices 0..n_messages-1.

    Returns parsed list or raises ValueError on invalid output.
    """
    import json
    data = json.loads(response_data) if isinstance(response_data, str) \
        else response_data
    if not isinstance(data, list) or not data:
        raise ValueError("Expected non-empty array from Gemini")
    covered = set()
    prev_end = -1
    for seg in data:
        s, e = seg.get("start_index"), seg.get("end_index")
        if not isinstance(s, int) or not isinstance(e, int):
            raise ValueError(f"Missing or non-integer start/end: {seg}")
        if s > e or s < 0 or e >= n_messages:
            raise ValueError(f"Index [{s},{e}] out of range (n={n_messages})")
        if s <= prev_end:
            raise ValueError(f"Overlapping or out-of-order at start_index={s}")
        covered.update(range(s, e + 1))
        prev_end = e
    if len(covered) != n_messages:
        logger.warning(
            f"Partial coverage: {len(covered)}/{n_messages} — using partial result")
    return data


def _fallback_time_gap(messages, gap_minutes=30):
    """Time-gap segmentation when LLM fails. No meaning resolution."""
    from datetime import datetime
    segs, current = [], [messages[0]]
    for msg in messages[1:]:
        try:
            prev_dt = datetime.fromisoformat(
                (current[-1].created_at or "").replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(
                (msg.created_at or "").replace("Z", "+00:00"))
            gap_mins = (curr_dt - prev_dt).total_seconds() / 60
        except Exception:
            gap_mins = 0
        if gap_mins > gap_minutes:
            segs.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        segs.append(current)
    result = []
    for seg in segs:
        synthesis = "\n".join(f"{m.author_name}: {m.content}" for m in seg)
        result.append({
            "topic_label":      "Time-gap segment",
            "synthesis":        synthesis,
            "message_ids":      [m.id for m in seg],
            "first_message_at": seg[0].created_at,
            "last_message_at":  seg[-1].created_at,
        })
    return result


async def segment_and_synthesize(messages, provider, batch_size=500, overlap=20):
    """Segment messages and synthesize each segment via Gemini.

    messages: list of StoredMessage objects (all channel messages).
    Returns list of segment dicts: {topic_label, synthesis, message_ids,
    first_message_at, last_message_at}.
    """
    from config import SEGMENT_GAP_MINUTES, GEMINI_MAX_TOKENS
    segmentable = [m for m in messages if _is_segmentable(m)]
    if not segmentable:
        return []

    all_segments = []
    stride = max(1, batch_size - overlap)
    batch_start = 0

    while batch_start < len(segmentable):
        batch = segmentable[batch_start:batch_start + batch_size]
        prompt = _build_segmentation_prompt(list(enumerate(batch)))

        parsed = None
        for attempt in range(2):
            try:
                raw = await provider.generate_ai_response(
                    messages=[
                        {"role": "system", "content": SEGMENTATION_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=GEMINI_MAX_TOKENS, temperature=0.2, channel_id=None,
                    response_mime_type="application/json",
                    response_json_schema=SEGMENTATION_SCHEMA,
                    use_json_schema=True,
                )
                parsed = _parse_segments(raw, len(batch))
                break
            except Exception as e:
                logger.warning(f"Segmentation attempt {attempt+1} failed: {e}")

        if parsed is None:
            logger.warning("Falling back to time-gap segmentation for batch")
            batch_segs = _fallback_time_gap(batch, SEGMENT_GAP_MINUTES)
        else:
            skip_before = overlap if batch_start > 0 else 0
            batch_segs = []
            for seg in parsed:
                if seg["start_index"] < skip_before:
                    continue
                seg_msgs = batch[seg["start_index"]:seg["end_index"] + 1]
                if not seg_msgs:
                    continue
                batch_segs.append({
                    "topic_label":      seg["topic_label"],
                    "synthesis":        seg["synthesis"],
                    "message_ids":      [m.id for m in seg_msgs],
                    "first_message_at": seg_msgs[0].created_at,
                    "last_message_at":  seg_msgs[-1].created_at,
                })
        all_segments.extend(batch_segs)
        batch_start += stride

    logger.info(f"segment_and_synthesize: {len(all_segments)} segs/{len(segmentable)} msgs")
    return all_segments


async def run_segmentation_phase(channel_id, messages, provider, progress_fn=None):
    """Orchestrate segmentation: segment → store → embed syntheses.

    Returns count of segments created.
    """
    from utils.segment_store import (
        clear_channel_segments, store_segments, store_segment_embedding)
    from utils.embedding_store import embed_texts_batch
    from config import SEGMENT_BATCH_SIZE, SEGMENT_OVERLAP

    async def _p(msg):
        if progress_fn:
            await progress_fn(msg)

    await _p("Segmenting conversation...")
    segments = await segment_and_synthesize(
        messages, provider,
        batch_size=SEGMENT_BATCH_SIZE, overlap=SEGMENT_OVERLAP)
    if not segments:
        logger.warning(f"No segments produced for ch:{channel_id}")
        return 0

    await _p(f"Storing {len(segments)} segments...")
    await asyncio.to_thread(clear_channel_segments, channel_id)
    seg_ids = await asyncio.to_thread(store_segments, channel_id, segments)

    await _p("Embedding segment syntheses...")
    syntheses = [s["synthesis"][:24000] for s in segments]
    embed_results = await asyncio.to_thread(embed_texts_batch, syntheses)
    for idx, vec in embed_results:
        if idx < len(seg_ids):
            await asyncio.to_thread(store_segment_embedding, seg_ids[idx], vec)

    logger.info(
        f"Segmentation phase complete: {len(seg_ids)} segments ch:{channel_id}")
    return len(seg_ids)
