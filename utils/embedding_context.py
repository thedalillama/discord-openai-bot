# utils/embedding_context.py
# Version 1.2.0
"""
Context construction for context-prepended message embeddings (SOW v5.6.0).

CHANGES v1.2.0: embed_query_with_smart_context() returns (vec, path_name) (SOW v5.7.0)
- MODIFIED: all return sites now return (vector, path_name) tuple so callers can
  record which embedding path was taken for context receipts
- Path names: "raw", "question_context", "similarity_context"

CHANGES v1.1.0: Smart query embedding to prevent topic bleed-through (SOW v5.6.1)
- ADDED: is_question() — heuristic question detection (no LLM)
- ADDED: embed_query_with_smart_context() — two-path query embedding:
    Path 1: previous message was a question → embed with question as context
    Path 2: check cosine similarity to previous stored embedding; if similar
    (same topic) re-embed with context, if dissimilar (topic shift) use raw

CREATED v1.0.0: Context-prepended embeddings (SOW v5.6.0)
- build_contextual_text() — prepend N prior messages before embedding
- get_previous_messages() — fetch N messages before a given message_id
- get_reply_context() — fetch replied-to message + N before it

All DB functions are synchronous; wrap in asyncio.to_thread() at call sites.
Graceful degradation: on any error, build_contextual_text() returns raw content.
"""
import sqlite3
from config import DATABASE_PATH
from utils.logging_utils import get_logger

logger = get_logger('embedding_context')

_QUESTION_STARTERS = (
    'who ', 'what ', 'where ', 'when ', 'why ', 'how ',
    'is ', 'are ', 'do ', 'does ', 'can ', 'could ',
    'should ', 'would ', 'will ', 'did ', 'has ', 'have ',
)


def is_question(text):
    """Detect if a message is a question. Simple heuristic, no LLM."""
    text = text.strip()
    if text.endswith('?'):
        return True
    lower = text.lower()
    return any(lower.startswith(q) for q in _QUESTION_STARTERS)


def embed_query_with_smart_context(query_text, channel_id, conversation_msgs):
    """Embed a query with context-aware logic to prevent topic bleed-through.

    Path 1 — previous message was a question: the current message is likely a
    response. Include the question as context (1 API call).

    Path 2 — otherwise: embed raw, then check cosine similarity to the previous
    message's stored embedding. If similar (same topic), re-embed with context.
    If dissimilar (topic shift), use the raw embedding already computed.

    Falls back to raw embed_text() on any failure.

    Args:
        query_text: The current user message text.
        channel_id: Discord channel ID (for logging).
        conversation_msgs: In-memory history dicts with role/content/_msg_id.

    Returns:
        list: Embedding vector, or None on total failure.
    """
    from utils.embedding_store import embed_text, cosine_similarity, get_stored_embedding
    from config import RETRIEVAL_MIN_SCORE

    try:
        if not conversation_msgs:
            return embed_text(query_text), "raw"

        # Find the previous user/assistant message
        prev = None
        for msg in reversed(conversation_msgs):
            if msg.get("role") in ("user", "assistant") and msg.get("content", "").strip():
                prev = msg
                break
        if prev is None:
            return embed_text(query_text), "raw"

        prev_content = prev.get("content", "")
        prev_label = prev.get("role", "user")
        prev_msg_id = prev.get("_msg_id")

        # Path 1: previous message was a question — current is likely a response
        if is_question(prev_content):
            ctx = f"[Context: {prev_label}: {prev_content[:200]}]"
            logger.debug(f"Query Path 1 (question context) ch:{channel_id}")
            return embed_text(f"{ctx}\n{query_text}"), "question_context"

        # Path 2: cosine similarity check to detect topic shift
        raw_vec = embed_text(query_text)
        if raw_vec is None:
            return None, "raw"

        prev_vec = get_stored_embedding(prev_msg_id)
        if prev_vec is None:
            return raw_vec, "raw"  # no stored embedding to compare, use raw

        sim = cosine_similarity(raw_vec, prev_vec)
        logger.debug(
            f"Query Path 2: sim={sim:.3f} vs threshold={RETRIEVAL_MIN_SCORE} "
            f"ch:{channel_id}")
        if sim > RETRIEVAL_MIN_SCORE:
            # Same topic — re-embed with context
            ctx = f"[Context: {prev_label}: {prev_content[:200]}]"
            logger.debug(f"Same topic (sim={sim:.3f}), re-embedding with context")
            return embed_text(f"{ctx}\n{query_text}"), "similarity_context"
        else:
            # Topic shift — use raw embedding already computed
            logger.debug(f"Topic shift (sim={sim:.3f}), using raw query embedding")
            return raw_vec, "raw"

    except Exception as e:
        logger.warning(f"embed_query_with_smart_context failed: {e}")
        return embed_text(query_text), "raw"


def get_previous_messages(channel_id, message_id, n=3):
    """Return up to N messages before message_id in channel, oldest first.

    Skips noise/commands. Returns list of (author_name, content) tuples.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT author_name, content FROM messages "
            "WHERE channel_id=? AND id < ? AND is_deleted=0 "
            "  AND content != '' AND content NOT LIKE '!%' "
            "  AND content NOT LIKE '\u2139\ufe0f%' "
            "  AND content NOT LIKE '\u2699\ufe0f%' "
            "ORDER BY created_at DESC LIMIT ?",
            (channel_id, message_id, n)
        ).fetchall()
        return [(r[0], r[1]) for r in reversed(rows)]
    except Exception as e:
        logger.warning(f"get_previous_messages failed msg {message_id}: {e}")
        return []
    finally:
        conn.close()


def get_reply_context(channel_id, reply_to_id, n=2):
    """Return replied-to message + up to N messages before it, oldest first.

    Returns list of (author_name, content) tuples.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT author_name, content, created_at FROM messages WHERE id=?",
            (reply_to_id,)
        ).fetchone()
        if not row:
            return []
        reply_author, reply_content, reply_ts = row
        before = conn.execute(
            "SELECT author_name, content FROM messages "
            "WHERE channel_id=? AND created_at < ? AND is_deleted=0 "
            "  AND content != '' AND content NOT LIKE '!%' "
            "  AND content NOT LIKE '\u2139\ufe0f%' "
            "  AND content NOT LIKE '\u2699\ufe0f%' "
            "ORDER BY created_at DESC LIMIT ?",
            (channel_id, reply_ts, n)
        ).fetchall()
        result = [(r[0], r[1]) for r in reversed(before)]
        result.append((reply_author, reply_content))
        return result
    except Exception as e:
        logger.warning(f"get_reply_context failed reply_to {reply_to_id}: {e}")
        return []
    finally:
        conn.close()


def build_contextual_text(channel_id, message_id, author, content,
                           reply_to_id=None, window=3):
    """Build context-prepended text for embedding.

    Prepends prior messages as [Context: a1: msg1 | a2: msg2] before the
    current message. Uses replied-to message as primary context when set.
    Falls back to raw content on any failure.

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID (used to fetch prior messages)
        author: Author name of the current message
        content: Message content to embed
        reply_to_id: Optional replied-to message ID (overrides window)
        window: Number of prior messages to use as context (default 3)

    Returns:
        str: Context-prepended text, or raw content on any error.
    """
    if not content:
        return content
    try:
        if reply_to_id:
            ctx_msgs = get_reply_context(channel_id, reply_to_id, n=window - 1)
        else:
            ctx_msgs = get_previous_messages(channel_id, message_id, n=window)
        if not ctx_msgs:
            return f"{author}: {content}"
        ctx_parts = " | ".join(
            f"{a}: {c[:120]}" for a, c in ctx_msgs if c.strip()
        )
        if not ctx_parts:
            return f"{author}: {content}"
        return f"[Context: {ctx_parts}]\n{author}: {content}"
    except Exception as e:
        logger.warning(f"build_contextual_text failed msg {message_id}: {e}")
        return content
