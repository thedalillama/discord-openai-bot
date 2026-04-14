# utils/fts_search.py
# Version 1.0.0
"""
FTS5 full-text search helpers for hybrid BM25 + dense retrieval (SOW v6.2.0).

Functions:
- populate_fts(channel_id): clear and rebuild FTS5 index for a channel's segments
- clear_fts(channel_id): delete all FTS5 entries for a channel
- fts_search(query_text, channel_id, top_n=20): BM25 keyword search via FTS5
- rrf_fuse(dense_ranked, bm25_ranked, k=15, top_n=5): Reciprocal Rank Fusion

The searchable_text column contains segment synthesis + " --- " + raw source
message content. BM25 therefore matches both the resolved meaning (synthesis)
and the original words spoken (messages). The separator prevents phrase queries
from crossing the synthesis/message boundary.

FTS5 is populated during !summary create only (not incremental). A BM25 failure
degrades gracefully to dense-only — rrf_fuse returns the dense ranking unchanged
when bm25_ranked is empty.

CREATED v1.0.0: SQLite FTS5 hybrid search (SOW v6.2.0)
"""
import sqlite3
from config import DATABASE_PATH
from utils.logging_utils import get_logger

logger = get_logger('fts_search')


def populate_fts(channel_id):
    """Clear and rebuild FTS5 index for a channel's segments.

    Loads each segment's synthesis and source messages, concatenates them
    with a separator, and inserts into segments_fts. Called after
    run_segmentation_phase() completes in summarizer.py.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM segments_fts WHERE channel_id=?", (str(channel_id),))
        segments = conn.execute(
            "SELECT id, synthesis FROM segments WHERE channel_id=?",
            (channel_id,)).fetchall()
        for seg_id, synthesis in segments:
            msgs = conn.execute(
                "SELECT m.author_name, m.content "
                "FROM segment_messages sm "
                "JOIN messages m ON m.id=sm.message_id "
                "WHERE sm.segment_id=? ORDER BY sm.position",
                (seg_id,)).fetchall()
            msg_text = " ".join(
                f"{a}: {c}" for a, c in msgs if c and c.strip())
            searchable = f"{synthesis or ''} --- {msg_text}"
            conn.execute(
                "INSERT INTO segments_fts(segment_id, channel_id, searchable_text) "
                "VALUES (?, ?, ?)",
                (seg_id, str(channel_id), searchable))
        conn.commit()
        logger.info(f"FTS5 rebuilt: {len(segments)} segs ch:{channel_id}")
    except Exception as e:
        logger.error(f"FTS5 populate failed ch:{channel_id}: {e}")
    finally:
        conn.close()


def clear_fts(channel_id):
    """Delete all FTS5 entries for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM segments_fts WHERE channel_id=?", (str(channel_id),))
        conn.commit()
    except Exception as e:
        logger.warning(f"FTS5 clear failed ch:{channel_id}: {e}")
    finally:
        conn.close()


def fts_search(query_text, channel_id, top_n=20):
    """BM25 search via FTS5 MATCH. Returns ranked list of segment IDs.

    FTS5 rank is negative (more negative = more relevant), so ORDER BY rank
    returns best matches first. Returns [] on any failure or no match.

    query_text is sanitized before passing to MATCH: FTS5 special characters
    (?, *, ", :, ^, (, ), -) are stripped so raw user questions don't cause
    syntax errors. Each remaining token becomes an implicit OR term.

    Args:
        query_text: raw user query string
        channel_id: Discord channel ID
        top_n: max results to return

    Returns:
        list of segment_id integers, ranked by BM25 (best first)
    """
    import re
    # Strip FTS5 special chars; collapse whitespace into individual terms
    sanitized = re.sub(r'[?*":()\-^]', ' ', query_text)
    sanitized = ' '.join(sanitized.split())
    if not sanitized:
        return []
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT segment_id FROM segments_fts "
            "WHERE channel_id=? AND segments_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (str(channel_id), sanitized, top_n)).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning(f"FTS5 search failed ch:{channel_id}: {e}")
        return []
    finally:
        conn.close()


def rrf_fuse(dense_ranked, bm25_ranked, k=15, top_n=5):
    """Reciprocal Rank Fusion. Score-agnostic — operates on rank positions only.

    RRF formula: score[id] += 1 / (k + rank) for each list.
    No normalization needed — BM25 and cosine scores are never compared directly.

    Args:
        dense_ranked: segment_ids from dense retrieval, best first
        bm25_ranked: segment_ids from BM25 retrieval, best first
        k: RRF constant (k=15 tuned for small result sets; lower = more top-rank weight)
        top_n: max results to return

    Returns:
        list of segment_ids ranked by fused score (best first).
        If bm25_ranked is empty, returns dense_ranked[:top_n] unchanged.
    """
    scores = {}
    for rank, seg_id in enumerate(dense_ranked, 1):
        scores[seg_id] = scores.get(seg_id, 0) + 1 / (k + rank)
    for rank, seg_id in enumerate(bm25_ranked, 1):
        scores[seg_id] = scores.get(seg_id, 0) + 1 / (k + rank)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [seg_id for seg_id, _ in ranked[:top_n]]
