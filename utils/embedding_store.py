# utils/embedding_store.py
# Version 1.2.0
"""
Embedding storage and semantic retrieval (SOW v4.0.0).

CHANGES v1.2.0: Replace TOPIC_MSG_LIMIT count cap with TOPIC_LINK_MIN_SCORE threshold
- CHANGED: link_topic_to_messages links ALL messages above similarity threshold
  instead of top-N; token budget in context_manager handles injection limits
- REMOVED: TOPIC_MSG_LIMIT import

CHANGES v1.1.0: Switch embedding provider from Gemini to OpenAI
- CHANGED: embed_text() now uses openai.OpenAI client with text-embedding-3-small
- REMOVED: Gemini genai import and models/ prefix logic
- NOTE: existing Gemini vectors are incompatible — clear message_embeddings,
  topics.embedding, topic_messages and re-run backfill + summary create

CHANGES v1.0.1: Fix Gemini embedding API call
- FIXED: model name now uses "models/" prefix (models/gemini-embedding-001)
- FIXED: contents= is correct (not content=); reverted incorrect rename

CREATED v1.0.0: Topic-based semantic retrieval
- OpenAI text-embedding-3-small, 1536 dimensions (6KB/blob)
- pack/unpack: float list ↔ SQLite BLOB (struct, dynamic size)
- cosine_similarity: pure Python, no dependencies
- embed_and_store_message: embed + persist, idempotent
- store_topic / store_topic_embedding: upsert topic record
- link_topic_to_messages: embed topic, top-N message similarity → topic_messages
- find_relevant_topics: rank stored topics by query similarity
- get_topic_messages: fetch linked messages for retrieval injection
- get_messages_without_embeddings: backfill query
"""
import math, struct, sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH, EMBEDDING_MODEL, TOPIC_LINK_MIN_SCORE
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
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def embed_text(text):
    """Call OpenAI embedding API. Synchronous — wrap in to_thread(). Returns None on failure."""
    if not text or not text.strip():
        return None
    try:
        import os
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        logger.warning(f"embed_text failed: {e}")
        return None


def embed_and_store_message(message_id, text):
    """Embed text and persist vector. No-op if already stored."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        if conn.execute("SELECT 1 FROM message_embeddings WHERE message_id=?",
                        (message_id,)).fetchone():
            return
        vector = embed_text(text)
        if vector is None:
            return
        conn.execute("INSERT OR IGNORE INTO message_embeddings(message_id,embedding) VALUES(?,?)",
                     (message_id, pack_embedding(vector)))
        conn.commit()
    finally:
        conn.close()


def store_message_embedding(message_id, embedding):
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("INSERT OR REPLACE INTO message_embeddings(message_id,embedding) VALUES(?,?)",
                     (message_id, pack_embedding(embedding)))
        conn.commit()
    finally:
        conn.close()


def get_message_embeddings(channel_id):
    """Return list of (message_id, embedding) for all embedded messages in channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT me.message_id, me.embedding FROM message_embeddings me "
            "JOIN messages m ON m.id=me.message_id WHERE m.channel_id=?",
            (channel_id,)).fetchall()
        return [(r[0], unpack_embedding(r[1])) for r in rows]
    finally:
        conn.close()


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
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("UPDATE topics SET embedding=? WHERE id=?",
                     (pack_embedding(embedding), topic_id))
        conn.commit()
    finally:
        conn.close()


def get_topic_embeddings(channel_id):
    """Return list of (topic_id, title, embedding) for topics with embeddings."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id,title,embedding FROM topics "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
        return [(r[0], r[1], unpack_embedding(r[2])) for r in rows]
    finally:
        conn.close()


def link_topic_to_messages(topic_id, channel_id):
    """Embed topic, link all messages above similarity threshold, write to topic_messages."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute("SELECT title,summary FROM topics WHERE id=?",
                           (topic_id,)).fetchone()
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

    store_topic_embedding(topic_id, topic_vec)
    msg_embeddings = get_message_embeddings(channel_id)
    if not msg_embeddings:
        return

    scored = [(mid, cosine_similarity(topic_vec, vec)) for mid, vec in msg_embeddings]
    linked = [(mid, s) for mid, s in scored if s >= TOPIC_LINK_MIN_SCORE]

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("DELETE FROM topic_messages WHERE topic_id=?", (topic_id,))
        conn.executemany("INSERT OR IGNORE INTO topic_messages(topic_id,message_id) VALUES(?,?)",
                         [(topic_id, mid) for mid, _ in linked])
        conn.commit()
        best = max((s for _, s in linked), default=0)
        logger.debug(f"Linked topic {topic_id} → {len(linked)} messages (best: {best:.3f})")
    finally:
        conn.close()


def find_relevant_topics(query_embedding, channel_id, top_k=5):
    """Return top-K (topic_id, title, score) by cosine similarity."""
    candidates = get_topic_embeddings(channel_id)
    if not candidates:
        return []
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


def get_messages_without_embeddings(channel_id, limit=500):
    """Return (message_id, content) for messages lacking embeddings. Skips noise/commands."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT m.id,m.content FROM messages m "
            "LEFT JOIN message_embeddings me ON m.id=me.message_id "
            "WHERE m.channel_id=? AND me.message_id IS NULL "
            "  AND m.is_deleted=0 AND m.content!='' "
            "  AND m.content NOT LIKE '!%' "
            "  AND m.content NOT LIKE '\u2139\ufe0f%' "
            "  AND m.content NOT LIKE '\u2699\ufe0f%' "
            "LIMIT ?",
            (channel_id, limit)).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()
