# utils/query_router.py
# Version 1.0.1
"""
Route structured query planner intent to execution paths (SOW v7.5.0).

get_candidate_segments() composes metadata filters (author, time) into a
single SQL query returning a set of segment IDs. route_query() applies the
candidate set as segment_filter to _retrieve_segment_context(), ensuring
RRF never scores segments outside the pre-filtered set.

Execution modes:
- lookup/summary/attribution: candidate filter + RRF
- existence: BM25 zero-hit check first; zero hits → grounded "not found"
- Any mode with zero candidates → grounded "not found" (no hallucination)

The planner receipt key is added to the result receipt for !explain display.

CHANGES v1.0.1: Pass author_filter to _retrieve_segment_context() so only the
  target author's messages are injected from each retrieved segment.
CREATED v1.0.0: Router + pre-filter SQL + existence check (SOW v7.5.0)
"""
import sqlite3
from config import DATABASE_PATH
from utils.logging_utils import get_logger

logger = get_logger('query_router')


def get_candidate_segments(channel_id, authors=None, after=None, before=None):
    """Return set of segment IDs whose messages match the metadata filters.

    Composes author and time filters into one SQL query. Returns empty set
    if no messages match — caller treats this as grounded "not found."
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        sql = """
            SELECT DISTINCT sm.segment_id
            FROM segment_messages sm
            JOIN messages m ON sm.message_id = m.id
            WHERE m.channel_id = ?
        """
        params = [channel_id]
        if authors:
            ph = ",".join("?" * len(authors))
            sql += f" AND m.author_name IN ({ph})"
            params.extend(authors)
        if after:
            sql += " AND m.created_at >= ?"
            params.append(after)
        if before:
            sql += " AND m.created_at < ?"
            params.append(before)
        rows = conn.execute(sql, params).fetchall()
        return {r[0] for r in rows}
    except Exception as e:
        logger.warning(f"get_candidate_segments failed ch:{channel_id}: {e}")
        return set()
    finally:
        conn.close()


def _not_found_result(authors, after, before, query_text, mode, planner_ms):
    """Build grounded 'not found' response when pre-filter returns zero segments."""
    parts = []
    if authors:
        parts.append(f"from {', '.join(authors)}")
    if after or before:
        t = []
        if after:
            t.append(f"after {str(after)[:10]}")
        if before:
            t.append(f"before {str(before)[:10]}")
        parts.append("in the time range: " + ", ".join(t))
    suffix = f" {' '.join(parts)}" if parts else ""
    note = f"No messages found{suffix} for this query."
    receipt = {
        "query": query_text,
        "embedding_path": "none",
        "retrieved_segments": [],
        "score_gap_applied": False,
        "fallback_used": False,
        "fallback_messages": 0,
        "query_planner": {
            "used": True, "mode": mode,
            "author_filter": authors,
            "time_filter": {"after": after, "before": before},
            "candidates": 0,
            "planner_latency_ms": planner_ms,
            "note": note,
        },
    }
    return note, 0, receipt, {}


def route_query(intent, query_vec, channel_id, budget, exclude_ids,
                embedding_path, query_text, planner_ms=0):
    """Dispatch planner intent to retrieval path.

    Builds SQL candidate set from author/time filters, then calls
    _retrieve_segment_context() with segment_filter=candidates so all three
    RRF signals are restricted to the pre-filtered set.

    Returns (context_text, tokens_used, receipt, citation_map).
    """
    from utils.context_retrieval import _retrieve_segment_context

    author = intent.get("author") or []
    after = intent.get("after")
    before = intent.get("before")
    content = intent.get("content_query", "").strip()
    mode = intent.get("mode", "lookup")

    logger.debug(
        f"route_query ch:{channel_id} mode={mode} author={author} "
        f"time=[{after},{before}] content={content!r:.40} ({planner_ms}ms)")

    # ── Metadata pre-filter ──
    segment_filter = None
    if author or after or before:
        segment_filter = get_candidate_segments(
            channel_id, author or None, after, before)
        if not segment_filter:
            return _not_found_result(
                author, after, before, query_text, mode, planner_ms)

    # ── Existence: BM25 zero-hit check ──
    if mode == "existence":
        from utils.fts_search import fts_search
        search_text = content or query_text
        hits = fts_search(search_text, channel_id, top_n=5,
                          segment_filter=segment_filter)
        if not hits:
            return _not_found_result(
                author, after, before, query_text, mode, planner_ms)
        if not segment_filter:
            segment_filter = set(hits)
        else:
            segment_filter = segment_filter & set(hits)
            if not segment_filter:
                return _not_found_result(
                    author, after, before, query_text, mode, planner_ms)

    # ── Retrieval ──
    context_text, tokens, receipt, citation_map = _retrieve_segment_context(
        channel_id, None, budget,
        exclude_ids=exclude_ids,
        segment_filter=segment_filter,
        author_filter=set(author) if author else None,
        query_vec=query_vec,
        embedding_path=embedding_path,
        query_text=query_text)

    if isinstance(receipt, dict):
        receipt["query_planner"] = {
            "used": True, "mode": mode,
            "author_filter": author,
            "time_filter": {"after": after, "before": before},
            "content_query": content,
            "candidates": len(segment_filter) if segment_filter is not None else None,
            "planner_latency_ms": planner_ms,
        }
    return context_text, tokens, receipt, citation_map
