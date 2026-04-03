# utils/context_retrieval.py
# Version 1.0.0
"""
Cluster-based semantic retrieval for context injection (SOW v5.6.0).

CREATED v1.0.0: Extracted from context_manager.py v2.3.0 (SOW v5.6.0)
- _fallback_msg_search() — direct message embedding search when no clusters pass
- _retrieve_cluster_context() — embed query, score clusters, return member messages

Query embedding uses in-memory conversation context (last 3 messages) so the
query vector is in the same contextual space as stored embeddings (v5.6.0).
estimate_tokens imported lazily from context_manager to avoid circular import.
"""
from config import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, RETRIEVAL_MSG_FALLBACK
from utils.logging_utils import get_logger

logger = get_logger('context_retrieval')


def _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids):
    """Direct message embedding search when cluster retrieval returns empty.

    Returns (context_text, tokens_used) or ("", 0).
    """
    from utils.context_manager import estimate_tokens
    try:
        from utils.embedding_store import find_similar_messages
        msgs = find_similar_messages(
            query_vec, channel_id,
            top_n=RETRIEVAL_MSG_FALLBACK,
            exclude_ids=recent_ids)
        if not msgs:
            return "", 0
        parts, used = [], 0
        for _, author, content, created_at in msgs:
            line = f"[{(created_at or '')[:10]}] {author}: {content}"
            lt = estimate_tokens(line) + 1
            if used + lt > token_budget:
                break
            parts.append(line)
            used += lt
        if not parts:
            return "", 0
        section = "[Retrieved by message similarity]\n" + "\n".join(parts)
        logger.debug(f"Fallback: {len(parts)} msgs ({used} tokens) ch:{channel_id}")
        return section, used
    except Exception as e:
        logger.warning(f"Fallback search failed ch:{channel_id}: {e}")
        return "", 0


def _retrieve_cluster_context(channel_id, conversation_msgs, token_budget):
    """Embed the latest user message, find relevant clusters, return formatted
    context string of their member messages.

    Query is embedded with the last 3 in-memory messages as context so it sits
    in the same contextual vector space as stored embeddings (v5.6.0).
    Falls back to direct message embedding search if no clusters pass threshold.

    Returns (context_text, tokens_used). Returns ("", 0) on any failure.
    """
    from utils.context_manager import estimate_tokens
    try:
        from utils.embedding_store import embed_text
        from utils.cluster_retrieval import find_relevant_clusters, get_cluster_messages

        query_text = None
        for msg in reversed(conversation_msgs):
            if msg.get("role") == "user" and msg.get("content", "").strip():
                query_text = msg["content"].strip()
                break
        if not query_text:
            return "", 0

        # Embed query with in-memory context (same space as stored contextual embeddings)
        ctx_msgs = [m for m in conversation_msgs
                    if m.get("role") in ("user", "assistant")
                    and m.get("content", "").strip()][-4:]
        if len(ctx_msgs) > 1:
            ctx_str = " | ".join(
                f"{m['role']}: {m['content'][:100]}" for m in ctx_msgs[:-1])
            contextual_query = f"[Context: {ctx_str}]\n{query_text}"
        else:
            contextual_query = query_text

        query_vec = embed_text(contextual_query)
        if query_vec is None:
            return "", 0

        recent_ids = {msg["_msg_id"] for msg in conversation_msgs if "_msg_id" in msg}

        clusters = find_relevant_clusters(query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
        clusters = [(cid, label, s) for cid, label, s in clusters if s >= RETRIEVAL_MIN_SCORE]
        logger.debug(
            f"Clusters above threshold ch:{channel_id}: {len(clusters)}, "
            f"scores: {[(label[:30], round(s, 3)) for _, label, s in clusters]}")

        if not clusters:
            return _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids)

        lines, tokens_used = [], 0
        for cluster_id, label, score in clusters:
            msgs = get_cluster_messages(cluster_id, exclude_ids=recent_ids)
            if not msgs:
                logger.debug(
                    f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                    f"0 messages, skipping")
                continue
            section = f"[Topic: {label}]\n" + "\n".join(
                f"[{(created_at or '')[:10]}] {author}: {content}"
                for _, author, content, created_at in msgs)
            section_tokens = estimate_tokens(section)
            if tokens_used + section_tokens > token_budget:
                logger.debug(
                    f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                    f"{len(msgs)} msgs, {section_tokens} tokens — exceeds budget")
                break
            logger.debug(
                f"Cluster '{label[:40]}' (score {round(score, 3)}): "
                f"{len(msgs)} messages, {section_tokens} tokens — injected")
            lines.append(section)
            tokens_used += section_tokens

        if not lines:
            return _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids)

        logger.debug(
            f"Retrieved {len(lines)} clusters ({tokens_used} tokens) "
            f"ch:{channel_id} query:{query_text[:50]!r}")
        return "\n\n".join(lines), tokens_used

    except Exception as e:
        logger.warning(f"Cluster retrieval failed ch:{channel_id}: {e}")
        return "", 0
