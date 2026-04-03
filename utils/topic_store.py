# utils/topic_store.py
# Version 1.0.0
"""
Topic storage and semantic linking (v4.x pipeline, retained for rollback).

CREATED v1.0.0: Extracted from embedding_store.py v1.8.0 (SOW v5.6.0)
- store_topic(), store_topic_embedding() — topic upsert and embedding write
- clear_channel_topics() — delete all topics + links for a channel
- get_topic_embeddings() — fetch topics with embeddings for scoring
- link_topic_to_messages() — embed topic, link messages above threshold
- _is_noise_topic() — filter bot-generated topic noise
- find_relevant_topics() — top-K cosine similarity against topic embeddings
- get_topic_messages() — messages linked to a topic via topic_messages table

These functions are no longer called on the main response path (replaced by
cluster-based retrieval in v5.5.0). Retained for rollback and !debug backfill.
"""
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH, TOPIC_LINK_MIN_SCORE
from utils.logging_utils import get_logger

logger = get_logger('topic_store')

_NOISE_PATTERNS = (
    "bot self-",
    "bot capability",
    "bot responses to",
    "initial bot",
    "bot communication",
)


def store_topic(channel_id, topic_id, title, summary, status):
    """Upsert a topic record (no embedding yet)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT INTO topics(id,channel_id,title,summary,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "title=excluded.title,summary=excluded.summary,"
            "status=excluded.status,updated_at=excluded.updated_at",
            (topic_id, channel_id, title, summary, status, now, now))
        conn.commit()
    finally:
        conn.close()


def store_topic_embedding(topic_id, embedding):
    """Store embedding blob for a topic."""
    from utils.embedding_store import pack_embedding
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("UPDATE topics SET embedding=? WHERE id=?",
                     (pack_embedding(embedding), topic_id))
        conn.commit()
    finally:
        conn.close()


def clear_channel_topics(channel_id):
    """Delete all topics and their message links for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM topic_messages WHERE topic_id IN "
            "(SELECT id FROM topics WHERE channel_id=?)", (channel_id,))
        conn.execute("DELETE FROM topics WHERE channel_id=?", (channel_id,))
        conn.commit()
        logger.debug(f"Cleared topics for ch:{channel_id}")
    finally:
        conn.close()


def get_topic_embeddings(channel_id):
    """Return (topic_id, title, embedding) for topics with embeddings."""
    from utils.embedding_store import unpack_embedding
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id,title,embedding FROM topics "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
        return [(r[0], r[1], unpack_embedding(r[2])) for r in rows]
    finally:
        conn.close()


def _is_noise_topic(title):
    t = title.lower()
    return any(t.startswith(p) or p in t for p in _NOISE_PATTERNS)


def find_relevant_topics(query_embedding, channel_id, top_k=5):
    """Return top-K (topic_id, title, score) by cosine similarity.

    Noise topics (bot self-descriptions, capability tests) are excluded
    before scoring so they cannot consume retrieval budget.
    """
    from utils.embedding_store import cosine_similarity
    all_candidates = get_topic_embeddings(channel_id)
    if not all_candidates:
        return []
    candidates, noise = [], []
    for item in all_candidates:
        (noise if _is_noise_topic(item[1]) else candidates).append(item)
    if noise:
        logger.debug(
            f"Noise topics filtered ch:{channel_id}: {[t for _, t, _ in noise]}")
    scored = sorted(
        ((tid, title, cosine_similarity(query_embedding, vec))
         for tid, title, vec in candidates),
        key=lambda x: x[2], reverse=True)
    return scored[:top_k]


def get_topic_messages(topic_id, exclude_ids=None):
    """Return (message_id, author_name, content, created_at) for linked messages."""
    exclude_ids = set(exclude_ids or [])
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT m.id,m.author_name,m.content,m.created_at "
            "FROM messages m JOIN topic_messages tm ON m.id=tm.message_id "
            "WHERE tm.topic_id=? ORDER BY m.created_at ASC",
            (topic_id,)).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows if r[0] not in exclude_ids]
    finally:
        conn.close()


def link_topic_to_messages(topic_id, channel_id):
    """Embed topic, link all messages above similarity threshold."""
    from utils.embedding_store import (
        embed_text, get_message_embeddings, cosine_similarity, pack_embedding)
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT title,summary FROM topics WHERE id=?", (topic_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        logger.warning(f"link_topic_to_messages: topic {topic_id} not found")
        return
    topic_text = row[0] + (" " + row[1] if row[1] else "")
    topic_vec = embed_text(topic_text)
    if topic_vec is None:
        logger.warning(f"link_topic_to_messages: embed failed for {topic_id}")
        return
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("UPDATE topics SET embedding=? WHERE id=?",
                     (pack_embedding(topic_vec), topic_id))
        conn.commit()
    finally:
        conn.close()
    msg_embeddings = get_message_embeddings(channel_id)
    if not msg_embeddings:
        return
    scored = [(mid, cosine_similarity(topic_vec, vec)) for mid, vec in msg_embeddings]
    linked = [(mid, s) for mid, s in scored if s >= TOPIC_LINK_MIN_SCORE]
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("DELETE FROM topic_messages WHERE topic_id=?", (topic_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO topic_messages(topic_id,message_id) VALUES(?,?)",
            [(topic_id, mid) for mid, _ in linked])
        conn.commit()
        best = max((s for _, s in linked), default=0)
        logger.debug(
            f"Linked topic {topic_id} → {len(linked)} messages (best: {best:.3f})")
    finally:
        conn.close()
