# utils/cluster_fallback.py
# Version 1.0.0
"""
Cluster-centroid retrieval fallback for pre-v6 channels (SOW v7.0.0 M1).
Extracted from context_retrieval.py to respect the 250-line limit.

CREATED v1.0.0:
- _cluster_rollback() — v5.x cluster_messages path; used when no segments exist
"""
from config import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE
from utils.logging_utils import get_logger

logger = get_logger('cluster_fallback')


def _cluster_rollback(query_vec, channel_id, query_text, embedding_path,
                      token_budget, recent_ids, exclude_ids=None):
    """Cluster centroid retrieval for pre-v6 channels.
    Uses cluster_messages junction table (v5.x path).
    """
    from utils.context_manager import estimate_tokens
    from utils.cluster_retrieval import find_relevant_clusters, get_cluster_messages
    from utils.context_retrieval import _fallback_msg_search
    _empty = ("", 0, {}, {})
    if exclude_ids:
        recent_ids = recent_ids | set(exclude_ids)
    try:
        all_clusters = find_relevant_clusters(
            query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
        clusters = [(cid, lbl, s) for cid, lbl, s in all_clusters
                    if s >= RETRIEVAL_MIN_SCORE]
        below = [{"label": lbl, "score": round(s, 3)}
                 for _, lbl, s in all_clusters if s < RETRIEVAL_MIN_SCORE]

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
