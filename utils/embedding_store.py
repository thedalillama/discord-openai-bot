# utils/embedding_store.py
# Version 1.8.0
"""
Embedding storage and semantic retrieval (SOW v4.0.0).

CHANGES v1.8.0: Extract topic functions + contextual embedding support (SOW v5.6.0)
- REMOVED: topic functions moved to utils/topic_store.py
- MODIFIED: get_messages_without_embeddings() returns (id, content, author, reply_to_id)
  and orders by created_at ASC (chronological, required for context building)
- ADDED: delete_channel_embeddings(channel_id) — wipe all embeddings for reembed

CHANGES v1.7.0: find_similar_messages() returns created_at instead of score
CHANGES v1.6.0: Add embed_texts_batch() for bulk backfill
CHANGES v1.5.0: Noise topic filter in find_relevant_topics() (Fix 1A)
CHANGES v1.4.0: clear_channel_topics() for Fix 2A (topic deduplication)
CHANGES v1.3.0: Add find_similar_messages() for direct fallback retrieval
CHANGES v1.2.0: Replace TOPIC_MSG_LIMIT count cap with TOPIC_LINK_MIN_SCORE threshold
CHANGES v1.1.0: Switch embedding provider to OpenAI text-embedding-3-small
CREATED v1.0.0: Topic-based semantic retrieval
"""
import math, struct, sqlite3
from config import DATABASE_PATH, EMBEDDING_MODEL
from utils.logging_utils import get_logger

logger = get_logger('embedding_store')


def pack_embedding(vector):
    return struct.pack(f'{len(vector)}f', *vector)

def unpack_embedding(blob):
    n = len(blob) // 4
    return list(struct.unpack(f'{n}f', blob))

def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_text(text):
    """Embed a single text string. Returns vector list or None on failure."""
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"embed_text failed: {e}")
        return None


def embed_texts_batch(texts, batch_size=1000):
    """Embed multiple texts in batches. Returns list of (index, vector) pairs."""
    try:
        from openai import OpenAI
        client = OpenAI()
        results = []
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start:batch_start + batch_size]
            try:
                resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                for item in resp.data:
                    results.append((batch_start + item.index, item.embedding))
            except Exception as e:
                logger.warning(
                    f"embed_texts_batch: batch {batch_start}–"
                    f"{batch_start + len(batch) - 1} failed: {e}")
        return results
    except Exception as e:
        logger.error(f"embed_texts_batch failed: {e}")
        return []


def embed_and_store_message(message_id, text):
    """Embed text and store the vector for a message. Idempotent."""
    vec = embed_text(text)
    if vec is None:
        return
    store_message_embedding(message_id, vec)


def store_message_embedding(message_id, embedding):
    """Upsert a message embedding blob."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT INTO message_embeddings(message_id, embedding) "
            "VALUES(?,?) ON CONFLICT(message_id) DO UPDATE SET "
            "embedding=excluded.embedding",
            (message_id, pack_embedding(embedding)))
        conn.commit()
    finally:
        conn.close()


def get_message_embeddings(channel_id):
    """Return (message_id, embedding_vector) for all embedded messages in channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT me.message_id, me.embedding "
            "FROM message_embeddings me JOIN messages m ON m.id=me.message_id "
            "WHERE m.channel_id=? AND m.is_deleted=0",
            (channel_id,)).fetchall()
        return [(r[0], unpack_embedding(r[1])) for r in rows]
    finally:
        conn.close()


def find_similar_messages(query_vec, channel_id, top_n=15,
                          min_score=0.0, exclude_ids=None):
    """Search message_embeddings directly for messages similar to query vector.

    Used as fallback when cluster retrieval returns empty. Filters out
    noise/command messages. Returns list of (message_id, author_name, content,
    created_at) sorted by score descending.
    """
    exclude_ids = set(exclude_ids or [])
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT me.message_id, m.author_name, m.content, m.created_at, me.embedding "
            "FROM message_embeddings me JOIN messages m ON m.id=me.message_id "
            "WHERE m.channel_id=? AND m.is_deleted=0 AND m.content!='' "
            "  AND m.content NOT LIKE '!%' "
            "  AND m.content NOT LIKE '\u2139\ufe0f%' "
            "  AND m.content NOT LIKE '\u2699\ufe0f%'",
            (channel_id,)).fetchall()
    finally:
        conn.close()
    scored = []
    for mid, author, content, created_at, blob in rows:
        if mid in exclude_ids:
            continue
        score = cosine_similarity(query_vec, unpack_embedding(blob))
        if score >= min_score:
            scored.append((mid, author, content, created_at, score))
    scored.sort(key=lambda x: x[4], reverse=True)
    return [(mid, author, content, created_at)
            for mid, author, content, created_at, _ in scored[:top_n]]


def get_messages_without_embeddings(channel_id, limit=500):
    """Return messages lacking embeddings as (id, content, author_name, reply_to_id).

    Ordered chronologically (ASC) so context is available for later messages
    during backfill. Skips noise and command messages.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT m.id, m.content, m.author_name, m.reply_to_message_id "
            "FROM messages m "
            "LEFT JOIN message_embeddings me ON m.id=me.message_id "
            "WHERE m.channel_id=? AND me.message_id IS NULL "
            "  AND m.is_deleted=0 AND m.content!='' "
            "  AND m.content NOT LIKE '!%' "
            "  AND m.content NOT LIKE '\u2139\ufe0f%' "
            "  AND m.content NOT LIKE '\u2699\ufe0f%' "
            "ORDER BY m.created_at ASC LIMIT ?",
            (channel_id, limit)).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]
    finally:
        conn.close()


def delete_channel_embeddings(channel_id):
    """Delete all message embeddings for a channel. Returns count deleted."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.execute(
            "DELETE FROM message_embeddings WHERE message_id IN "
            "(SELECT id FROM messages WHERE channel_id=?)",
            (channel_id,))
        conn.commit()
        logger.info(f"Deleted {cursor.rowcount} embeddings for ch:{channel_id}")
        return cursor.rowcount
    finally:
        conn.close()
