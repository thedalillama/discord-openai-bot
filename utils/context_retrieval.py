# utils/context_retrieval.py
# Version 1.14.0
"""
Segment-based semantic retrieval for context injection (SOW v6.1.0–v7.0.0).

CHANGES v1.14.0: Proposition-level speaker filter — filter proposition signal by
  speaker before RRF; inject context note when no props match; remove message-level
  filter (speaker_pruned, synthesis suppression, message minimum check).
CHANGES v1.13.0: Speaker minimum — message-level <2 check (removed in v1.14.0)
CHANGES v1.12.0: Strip author prefix; skip synthesis when speaker finds no messages
CHANGES v1.11.0: speaker_pruned flag suppresses synthesis to prevent cross-speaker attribution
CHANGES v1.10.0: Speaker filter (detect_speaker_filter + _author_cache + receipt key)
CHANGES v1.9.0: exclude_ids for Layer 2 dedup; _cluster_rollback pass-through

CHANGES v1.8.0: Three-signal RRF — proposition + dense + BM25 (SOW v6.3.0)
- ADDED: find_relevant_propositions() call; collapses to segment IDs pre-RRF
- MODIFIED: rrf_fuse() now takes prop_ranked as first arg (variadic, backward-compat)
- MODIFIED: debug log includes prop signal count

CHANGES v1.7.0: Hybrid BM25 + dense retrieval via RRF (SOW v6.2.0)
CHANGES v1.6.0: Direct segment retrieval (SOW v6.1.0)
CHANGES v1.5.0: Segment-aware context injection (SOW v6.0.0)
CHANGES v1.4.0: Partial cluster injection when cluster exceeds token budget
CHANGES v1.3.0: Citation numbering + citation_map in return value (SOW v5.9.0)
CHANGES v1.2.0: Return cluster receipt data for explainability (SOW v5.7.0)
CHANGES v1.1.0: Smart query embedding to prevent topic bleed-through (SOW v5.6.1)
CREATED v1.0.0: Extracted from context_manager.py v2.3.0 (SOW v5.6.0)

estimate_tokens imported lazily from context_manager to avoid circular import.
"""
import sqlite3
from config import (RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, RETRIEVAL_MSG_FALLBACK,
                    RETRIEVAL_FLOOR, RETRIEVAL_SCORE_GAP, RRF_K, DATABASE_PATH)
from utils.logging_utils import get_logger

logger = get_logger('context_retrieval')

_author_cache = {}


def detect_speaker_filter(query_text, channel_id):
    """Return an author name if the query specifically names a channel participant.

    Loads distinct author names for the channel on first call (cached per channel).
    Matches names >= 3 chars found in the query (case-insensitive, strips Discord
    discriminators). Returns None if no participant name is detected.
    """
    if channel_id not in _author_cache:
        conn = sqlite3.connect(DATABASE_PATH)
        try:
            rows = conn.execute(
                "SELECT DISTINCT author_name FROM messages "
                "WHERE channel_id=? AND author_name IS NOT NULL",
                (channel_id,)).fetchall()
        finally:
            conn.close()
        _author_cache[channel_id] = [r[0] for r in rows if r[0]]
    query_lower = query_text.lower()
    for author in _author_cache[channel_id]:
        name = author.split('#')[0].strip().lower()
        if len(name) >= 3 and name in query_lower:
            return author
    return None


def _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids):
    """Direct message embedding search when retrieval returns empty.

    Returns (context_text, tokens_used, msg_count) or ("", 0, 0).
    """
    from utils.context_manager import estimate_tokens
    try:
        from utils.embedding_store import find_similar_messages
        msgs = find_similar_messages(
            query_vec, channel_id,
            top_n=RETRIEVAL_MSG_FALLBACK,
            exclude_ids=recent_ids)
        if not msgs:
            return "", 0, 0
        parts, used = [], 0
        for _, author, content, created_at in msgs:
            line = f"[{(created_at or '')[:10]}] {author}: {content}"
            lt = estimate_tokens(line) + 1
            if used + lt > token_budget:
                break
            parts.append(line)
            used += lt
        if not parts:
            return "", 0, 0
        section = "[Retrieved by message similarity]\n" + "\n".join(parts)
        logger.debug(f"Fallback: {len(parts)} msgs ({used} tokens) ch:{channel_id}")
        return section, used, len(parts)
    except Exception as e:
        logger.warning(f"Fallback search failed ch:{channel_id}: {e}")
        return "", 0, 0


def _retrieve_segment_context(channel_id, conversation_msgs, token_budget,
                              exclude_ids=None):
    """Embed latest user message; fuse BM25+dense segments; return context.
    Returns (context_text, tokens_used, receipt, citation_map).
    ("", 0, {}, {}) on failure.
    exclude_ids: message IDs already in Layer 2 continuity — not duplicated here.
    """
    from utils.context_manager import estimate_tokens
    _empty = ("", 0, {}, {})
    try:
        from utils.embedding_context import embed_query_with_smart_context
        from utils.cluster_retrieval import (
            find_relevant_segments, get_segment_with_messages,
            _apply_score_gap, find_relevant_propositions)
        from utils.fts_search import fts_search, rrf_fuse

        query_text = None
        for msg in reversed(conversation_msgs):
            if msg.get("role") == "user" and msg.get("content", "").strip():
                query_text = msg["content"].strip()
                break
        if not query_text:
            return _empty

        detect_text = query_text.split(': ', 1)[1] if ': ' in query_text else query_text
        speaker = detect_speaker_filter(detect_text, channel_id)

        query_vec, embedding_path = embed_query_with_smart_context(
            query_text, channel_id, conversation_msgs)
        if query_vec is None:
            return _empty

        recent_ids = {msg["_msg_id"] for msg in conversation_msgs if "_msg_id" in msg}
        if exclude_ids:
            recent_ids = recent_ids | set(exclude_ids)

        segments = find_relevant_segments(
            query_vec, channel_id, top_k=RETRIEVAL_TOP_K * 2, floor=RETRIEVAL_FLOOR)

        if not segments:
            logger.debug(f"No segments ch:{channel_id} — cluster rollback")
            from utils.cluster_fallback import _cluster_rollback
            return _cluster_rollback(
                query_vec, channel_id, query_text, embedding_path,
                token_budget, recent_ids, exclude_ids=exclude_ids)

        gap_applied = False
        if RETRIEVAL_SCORE_GAP > 0 and len(segments) > 1:
            pruned = _apply_score_gap(segments, RETRIEVAL_SCORE_GAP)
            gap_applied = len(pruned) < len(segments)
            segments = pruned

        # Three-signal RRF: propositions + dense + BM25
        dense_ranked = [s[0] for s in segments]
        prop_results = find_relevant_propositions(
            query_vec, channel_id, speaker_filter=speaker)
        prop_ranked = [sid for sid, _ in prop_results]
        context_prefix = (f"Note: No recorded statements from {speaker} were "
                          f"found on this topic.\n\n") if speaker and not prop_ranked else ""
        bm25_ranked = fts_search(query_text, channel_id, top_n=20)
        fused_pairs = rrf_fuse(
            prop_ranked, dense_ranked, bm25_ranked, k=RRF_K, top_n=RETRIEVAL_TOP_K)
        dense_map = {s[0]: s for s in segments}
        segments = [(sid, dense_map[sid][1], dense_map[sid][2], rs)
                    if sid in dense_map else (sid, None, None, rs)
                    for sid, rs in fused_pairs]
        logger.debug(
            f"Hybrid ch:{channel_id}: prop={len(prop_ranked)} "
            f"dense={len(dense_ranked)} bm25={len(bm25_ranked)} "
            f"fused={len(segments)} gap={gap_applied}")

        lines, tokens_used, injected = [], 0, []
        citation_map, citation_num = {}, 1
        for seg_id, topic_label, synthesis, score in segments:
            seg_data = get_segment_with_messages(seg_id, exclude_ids=recent_ids)
            if not seg_data:
                continue
            tl = topic_label or seg_data.get("topic_label") or "General"
            syn = synthesis or seg_data.get("synthesis") or ""
            s_lines = [f"[Topic: {tl}]", f"Summary: {syn}", "\nSource messages:"]
            temp_cites, start_cite = {}, citation_num
            for mid, author, content, created_at in seg_data["messages"]:
                temp_cites[citation_num] = {
                    "author": author, "content": content, "date": created_at or ""}
                s_lines.append(
                    f"[{citation_num}] [{(created_at or '')[:10]}] "
                    f"{author}: {content}")
                citation_num += 1
            section = "\n".join(s_lines)
            sec_tokens = estimate_tokens(section)

            if tokens_used + sec_tokens <= token_budget:
                citation_map.update(temp_cites)
                lines.append(section)
                tokens_used += sec_tokens
                injected.append({
                    "segment_id": seg_id, "topic_label": tl,
                    "score": round(score, 3) if score is not None else None,
                    "message_count": len(seg_data["messages"]),
                    "tokens": sec_tokens,
                })
            else:
                citation_num = start_cite
                synth = f"[Topic: {tl}]\n{syn}"
                synth_tokens = estimate_tokens(synth)
                if tokens_used + synth_tokens <= token_budget:
                    lines.append(synth)
                    tokens_used += synth_tokens
                    injected.append({
                        "segment_id": seg_id, "topic_label": tl,
                        "score": round(score, 3) if score is not None else None,
                        "message_count": 0,
                        "tokens": synth_tokens, "synthesis_only": True,
                    })
                break

        if not lines:
            text, tokens, count = _fallback_msg_search(
                query_vec, channel_id, token_budget, recent_ids)
            receipt = {
                "query": query_text, "embedding_path": embedding_path,
                "retrieved_segments": [], "score_gap_applied": gap_applied,
                "fallback_used": bool(text), "fallback_messages": count,
                "speaker_filter": speaker,
            }
            return context_prefix + text, tokens + estimate_tokens(context_prefix), receipt, {}

        logger.debug(
            f"Retrieved {len(lines)} segments ({tokens_used} tok) "
            f"ch:{channel_id} q:{query_text[:50]!r}"
            + (f" speaker_filter={speaker!r}" if speaker else ""))
        receipt = {
            "query": query_text, "embedding_path": embedding_path,
            "retrieved_segments": injected,
            "score_gap_applied": gap_applied,
            "fallback_used": False, "fallback_messages": 0,
            "speaker_filter": speaker,
        }
        return context_prefix + "\n\n".join(lines), tokens_used, receipt, citation_map

    except Exception as e:
        logger.warning(f"Segment retrieval failed ch:{channel_id}: {e}")
        return _empty
