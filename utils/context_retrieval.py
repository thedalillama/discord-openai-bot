# utils/context_retrieval.py
# Version 1.3.0
"""
Cluster-based semantic retrieval for context injection (SOW v5.6.0).

CHANGES v1.3.0: Citation numbering + citation_map in return value (SOW v5.9.0)
- MODIFIED: _retrieve_cluster_context() returns 4-tuple
  (context_text, tokens_used, cluster_receipt, citation_map)
  citation_map: {int: {"author", "content", "date"}} for each numbered message
- MODIFIED: Retrieved messages labeled [N] in context text for LLM citation
- Fallback path returns citation_map={} (fallback messages not numbered)

CHANGES v1.2.0: Return cluster receipt data for explainability (SOW v5.7.0)
CHANGES v1.1.0: Smart query embedding to prevent topic bleed-through (SOW v5.6.1)
CREATED v1.0.0: Extracted from context_manager.py v2.3.0 (SOW v5.6.0)

estimate_tokens imported lazily from context_manager to avoid circular import.
"""
from config import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, RETRIEVAL_MSG_FALLBACK
from utils.logging_utils import get_logger

logger = get_logger('context_retrieval')


def _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids):
    """Direct message embedding search when cluster retrieval returns empty.

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


def _retrieve_cluster_context(channel_id, conversation_msgs, token_budget):
    """Embed the latest user message, find relevant clusters, return formatted
    context string of their member messages plus a receipt dict.

    Returns:
        tuple: (context_text, tokens_used, cluster_receipt, citation_map)
        citation_map: {int: {"author", "content", "date"}} for numbered messages.
        Returns ("", 0, {}, {}) on any failure.
    """
    from utils.context_manager import estimate_tokens
    _empty = ("", 0, {}, {})
    try:
        from utils.embedding_context import embed_query_with_smart_context
        from utils.cluster_retrieval import find_relevant_clusters, get_cluster_messages

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

        all_clusters = find_relevant_clusters(query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
        clusters = [(cid, label, s) for cid, label, s in all_clusters
                    if s >= RETRIEVAL_MIN_SCORE]
        below_threshold = [{"label": label, "score": round(s, 3)}
                           for _, label, s in all_clusters if s < RETRIEVAL_MIN_SCORE]

        logger.debug(
            f"Clusters above threshold ch:{channel_id}: {len(clusters)}, "
            f"scores: {[(label[:30], round(s, 3)) for _, label, s in clusters]}")

        if not clusters:
            text, tokens, count = _fallback_msg_search(
                query_vec, channel_id, token_budget, recent_ids)
            receipt = {
                "query": query_text, "embedding_path": embedding_path,
                "retrieved_clusters": [], "clusters_below_threshold": below_threshold,
                "fallback_used": bool(text), "fallback_messages": count,
            }
            return text, tokens, receipt, {}

        lines, tokens_used, injected = [], 0, []
        citation_map, citation_num = {}, 1
        for cluster_id, label, score in clusters:
            msgs = get_cluster_messages(cluster_id, exclude_ids=recent_ids)
            if not msgs:
                logger.debug(
                    f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                    f"0 messages, skipping")
                continue
            # Build numbered lines and temp citation entries
            msg_lines, temp_cites = [], {}
            for _, author, content, created_at in msgs:
                temp_cites[citation_num] = {
                    "author": author, "content": content, "date": created_at or ""}
                msg_lines.append(
                    f"[{citation_num}] [{(created_at or '')[:10]}] {author}: {content}")
                citation_num += 1
            section = f"[Topic: {label}]\n" + "\n".join(msg_lines)
            section_tokens = estimate_tokens(section)
            if tokens_used + section_tokens > token_budget:
                citation_num -= len(msgs)  # revert counter
                logger.debug(
                    f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                    f"{len(msgs)} msgs, {section_tokens} tokens — exceeds budget")
                break
            citation_map.update(temp_cites)
            logger.debug(
                f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                f"{len(msgs)} messages, {section_tokens} tokens — injected")
            lines.append(section)
            tokens_used += section_tokens
            injected.append({
                "cluster_id": str(cluster_id), "label": label,
                "score": round(score, 3), "messages_injected": len(msgs),
                "tokens": section_tokens,
            })

        if not lines:
            text, tokens, count = _fallback_msg_search(
                query_vec, channel_id, token_budget, recent_ids)
            receipt = {
                "query": query_text, "embedding_path": embedding_path,
                "retrieved_clusters": [], "clusters_below_threshold": below_threshold,
                "fallback_used": bool(text), "fallback_messages": count,
            }
            return text, tokens, receipt, {}

        logger.debug(
            f"Retrieved {len(lines)} clusters ({tokens_used} tokens) "
            f"ch:{channel_id} query:{query_text[:50]!r}")
        receipt = {
            "query": query_text, "embedding_path": embedding_path,
            "retrieved_clusters": injected,
            "clusters_below_threshold": below_threshold,
            "fallback_used": False, "fallback_messages": 0,
        }
        return "\n\n".join(lines), tokens_used, receipt, citation_map

    except Exception as e:
        logger.warning(f"Cluster retrieval failed ch:{channel_id}: {e}")
        return _empty
