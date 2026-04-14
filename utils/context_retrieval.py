# utils/context_retrieval.py
# Version 1.6.0
"""
Segment-based semantic retrieval for context injection (SOW v6.1.0).

CHANGES v1.6.0: Direct segment retrieval (SOW v6.1.0)
- RENAMED: _retrieve_cluster_context → _retrieve_segment_context
- PRIMARY PATH: find_relevant_segments() scores query vs all segment embeddings;
  score-gap detection applied after top-K; receipt uses retrieved_segments key
- ROLLBACK: _cluster_rollback() fires when no segments exist (pre-v6 channels);
  uses cluster centroid retrieval + get_cluster_messages()

CHANGES v1.5.0: Segment-aware context injection (SOW v6.0.0)
CHANGES v1.4.0: Partial cluster injection when cluster exceeds token budget
CHANGES v1.3.0: Citation numbering + citation_map in return value (SOW v5.9.0)
CHANGES v1.2.0: Return cluster receipt data for explainability (SOW v5.7.0)
CHANGES v1.1.0: Smart query embedding to prevent topic bleed-through (SOW v5.6.1)
CREATED v1.0.0: Extracted from context_manager.py v2.3.0 (SOW v5.6.0)

estimate_tokens imported lazily from context_manager to avoid circular import.
"""
from config import (RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, RETRIEVAL_MSG_FALLBACK,
                    RETRIEVAL_FLOOR, RETRIEVAL_SCORE_GAP)
from utils.logging_utils import get_logger

logger = get_logger('context_retrieval')


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


def _cluster_rollback(query_vec, channel_id, query_text, embedding_path,
                      token_budget, recent_ids):
    """Cluster centroid retrieval for pre-v6 channels with no segment data.

    Uses cluster_messages junction table (v5.x path). Returns the same
    4-tuple as _retrieve_segment_context.
    """
    from utils.context_manager import estimate_tokens
    from utils.cluster_retrieval import find_relevant_clusters, get_cluster_messages
    _empty = ("", 0, {}, {})
    try:
        all_clusters = find_relevant_clusters(
            query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
        clusters = [(cid, lbl, s) for cid, lbl, s in all_clusters
                    if s >= RETRIEVAL_MIN_SCORE]
        below = [{"label": lbl, "score": round(s, 3)}
                 for _, lbl, s in all_clusters if s < RETRIEVAL_MIN_SCORE]

        if not clusters:
            text, tokens, count = _fallback_msg_search(
                query_vec, channel_id, token_budget, recent_ids)
            receipt = {"query": query_text, "embedding_path": embedding_path,
                       "retrieved_clusters": [], "clusters_below_threshold": below,
                       "fallback_used": bool(text), "fallback_messages": count}
            return text, tokens, receipt, {}

        lines, tokens_used, injected = [], 0, []
        citation_map, citation_num = {}, 1
        for cluster_id, label, score in clusters:
            msgs = get_cluster_messages(cluster_id, exclude_ids=recent_ids)
            if not msgs:
                continue
            temp_cites, msg_lines = {}, []
            for _, author, content, created_at in msgs:
                temp_cites[citation_num] = {
                    "author": author, "content": content, "date": created_at or ""}
                msg_lines.append(
                    f"[{citation_num}] [{(created_at or '')[:10]}] "
                    f"{author}: {content}")
                citation_num += 1
            section = f"[Topic: {label}]\n" + "\n".join(msg_lines)
            sec_tokens = estimate_tokens(section)
            if tokens_used + sec_tokens > token_budget:
                citation_num -= len(msgs)
                break
            citation_map.update(temp_cites)
            lines.append(section)
            tokens_used += sec_tokens
            injected.append({"cluster_id": str(cluster_id), "label": label,
                             "score": round(score, 3),
                             "messages_injected": len(msgs), "tokens": sec_tokens})

        if not lines:
            text, tokens, count = _fallback_msg_search(
                query_vec, channel_id, token_budget, recent_ids)
            receipt = {"query": query_text, "embedding_path": embedding_path,
                       "retrieved_clusters": [], "clusters_below_threshold": below,
                       "fallback_used": bool(text), "fallback_messages": count}
            return text, tokens, receipt, {}

        receipt = {"query": query_text, "embedding_path": embedding_path,
                   "retrieved_clusters": injected,
                   "clusters_below_threshold": below,
                   "fallback_used": False, "fallback_messages": 0}
        return "\n\n".join(lines), tokens_used, receipt, citation_map
    except Exception as e:
        logger.warning(f"Cluster rollback failed ch:{channel_id}: {e}")
        return _empty


def _retrieve_segment_context(channel_id, conversation_msgs, token_budget):
    """Embed the latest user message, find relevant segments, return formatted
    context string of their syntheses + source messages plus a receipt dict.

    Returns:
        tuple: (context_text, tokens_used, receipt, citation_map)
        citation_map: {int: {"author", "content", "date"}} for numbered messages.
        Returns ("", 0, {}, {}) on any failure.
    """
    from utils.context_manager import estimate_tokens
    _empty = ("", 0, {}, {})
    try:
        from utils.embedding_context import embed_query_with_smart_context
        from utils.cluster_retrieval import (
            find_relevant_segments, get_segment_with_messages, _apply_score_gap)

        query_text = None
        for msg in reversed(conversation_msgs):
            if msg.get("role") == "user" and msg.get("content", "").strip():
                query_text = msg["content"].strip()
                break
        if not query_text:
            return _empty

        query_vec, embedding_path = embed_query_with_smart_context(
            query_text, channel_id, conversation_msgs)
        if query_vec is None:
            return _empty

        recent_ids = {msg["_msg_id"] for msg in conversation_msgs if "_msg_id" in msg}

        segments = find_relevant_segments(
            query_vec, channel_id, top_k=RETRIEVAL_TOP_K, floor=RETRIEVAL_FLOOR)

        if not segments:
            # No segments in DB — fall back to cluster centroid retrieval
            logger.debug(f"No segments ch:{channel_id} — cluster rollback")
            return _cluster_rollback(
                query_vec, channel_id, query_text, embedding_path,
                token_budget, recent_ids)

        gap_applied = False
        if RETRIEVAL_SCORE_GAP > 0 and len(segments) > 1:
            pruned = _apply_score_gap(segments, RETRIEVAL_SCORE_GAP)
            gap_applied = len(pruned) < len(segments)
            segments = pruned

        logger.debug(
            f"Segments ch:{channel_id}: {len(segments)}, gap={gap_applied}, "
            f"scores: {[(s[1][:25], round(s[3], 3)) for s in segments]}")

        lines, tokens_used, injected = [], 0, []
        citation_map, citation_num = {}, 1
        for seg_id, topic_label, synthesis, score in segments:
            seg_data = get_segment_with_messages(seg_id, exclude_ids=recent_ids)
            if not seg_data:
                continue
            s_lines = [f"[Topic: {topic_label or 'General'}]",
                       f"Summary: {synthesis}", "\nSource messages:"]
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
                    "segment_id": seg_id, "topic_label": topic_label,
                    "score": round(score, 3),
                    "message_count": len(seg_data["messages"]),
                    "tokens": sec_tokens,
                })
            else:
                citation_num = start_cite
                synth = f"[Topic: {topic_label or 'General'}]\n{synthesis}"
                synth_tokens = estimate_tokens(synth)
                if tokens_used + synth_tokens <= token_budget:
                    lines.append(synth)
                    tokens_used += synth_tokens
                    injected.append({
                        "segment_id": seg_id, "topic_label": topic_label,
                        "score": round(score, 3), "message_count": 0,
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
            }
            return text, tokens, receipt, {}

        logger.debug(
            f"Retrieved {len(lines)} segments ({tokens_used} tok) "
            f"ch:{channel_id} q:{query_text[:50]!r}")
        receipt = {
            "query": query_text, "embedding_path": embedding_path,
            "retrieved_segments": injected,
            "score_gap_applied": gap_applied,
            "fallback_used": False, "fallback_messages": 0,
        }
        return "\n\n".join(lines), tokens_used, receipt, citation_map

    except Exception as e:
        logger.warning(f"Segment retrieval failed ch:{channel_id}: {e}")
        return _empty
