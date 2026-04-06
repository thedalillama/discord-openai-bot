# utils/embedding_context.py
# Version 1.3.0
"""
Context construction for context-prepended message embeddings (SOW v5.6.0).

CHANGES v1.3.0: Topic-boundary-aware context filtering in build_contextual_text()
  (SOW v5.8.0)
- ADDED: CONTEXT_SIMILARITY_THRESHOLD = 0.3 constant
- MODIFIED: build_contextual_text() now filters previous messages by cosine
  similarity before prepending. Only same-topic predecessors are included.
  Questions are always included regardless of similarity (likely a response).
  Falls back to unfiltered context on any similarity-check failure.
- MODIFIED: get_previous_messages() returns (message_id, author, content)
  3-tuples so build_contextual_text() can look up stored embeddings.
  Reply chain path (reply_to_id) is unchanged — bypasses similarity check.

CHANGES v1.2.0: embed_query_with_smart_context() returns (vec, path_name) (SOW v5.7.0)
- MODIFIED: all return sites now return (vector, path_name) tuple so callers can
  record which embedding path was taken for context receipts
- Path names: "raw", "question_context", "similarity_context"

CHANGES v1.1.0: Smart query embedding to prevent topic bleed-through (SOW v5.6.1)
- ADDED: is_question() — heuristic question detection (no LLM)
- ADDED: embed_query_with_smart_context() — two-path query embedding

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

# Minimum cosine similarity for a previous message to be included as context.
# Lower than RETRIEVAL_MIN_SCORE (0.45) — more inclusive for context prepending.
CONTEXT_SIMILARITY_THRESHOLD = 0.3

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
        (vector, path_name) tuple, or (None, "raw") on total failure.
    """
    from utils.embedding_store import embed_text, cosine_similarity, get_stored_embedding
    from config import RETRIEVAL_MIN_SCORE

    try:
        if not conversation_msgs:
            return embed_text(query_text), "raw"

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
            return raw_vec, "raw"

        sim = cosine_similarity(raw_vec, prev_vec)
        logger.debug(
            f"Query Path 2: sim={sim:.3f} vs threshold={RETRIEVAL_MIN_SCORE} "
            f"ch:{channel_id}")
        if sim > RETRIEVAL_MIN_SCORE:
            ctx = f"[Context: {prev_label}: {prev_content[:200]}]"
            logger.debug(f"Same topic (sim={sim:.3f}), re-embedding with context")
            return embed_text(f"{ctx}\n{query_text}"), "similarity_context"
        else:
            logger.debug(f"Topic shift (sim={sim:.3f}), using raw query embedding")
            return raw_vec, "raw"

    except Exception as e:
        logger.warning(f"embed_query_with_smart_context failed: {e}")
        return embed_text(query_text), "raw"


def get_previous_messages(channel_id, message_id, n=3):
    """Return up to N messages before message_id in channel, oldest first.

    Skips noise/commands. Returns list of (message_id, author_name, content).
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, author_name, content FROM messages "
            "WHERE channel_id=? AND id < ? AND is_deleted=0 "
            "  AND content != '' AND content NOT LIKE '!%' "
            "  AND content NOT LIKE '\u2139\ufe0f%' "
            "  AND content NOT LIKE '\u2699\ufe0f%' "
            "ORDER BY created_at DESC LIMIT ?",
            (channel_id, message_id, n)
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in reversed(rows)]
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
    """Build context-prepended text for embedding with topic-boundary filtering.

    Reply chains always use replied-to message as context (no similarity check).
    For regular messages, previous messages are filtered by cosine similarity —
    only same-topic predecessors are included. Questions are always included.
    Falls back to unfiltered context if similarity check fails.

    Returns:
        str: Context-prepended text, or raw content on any error.
    """
    if not content:
        return content
    try:
        if reply_to_id:
            ctx_msgs = get_reply_context(channel_id, reply_to_id, n=window - 1)
            if not ctx_msgs:
                return f"{author}: {content}"
            ctx_parts = " | ".join(f"{a}: {c[:120]}" for a, c in ctx_msgs if c.strip())
            return f"[Context: {ctx_parts}]\n{author}: {content}" if ctx_parts \
                else f"{author}: {content}"

        previous = get_previous_messages(channel_id, message_id, n=window)
        if not previous:
            return f"{author}: {content}"

        # Similarity filter — fall back to unfiltered on any failure
        try:
            from utils.embedding_store import (
                embed_text, cosine_similarity, get_stored_embedding)
            raw_vec = embed_text(f"{author}: {content}")
            if raw_vec is None:
                raise ValueError("raw embed returned None")
            filtered = []
            for msg_id, prev_author, prev_content in previous:
                if is_question(prev_content):
                    filtered.append((prev_author, prev_content))
                    continue
                prev_vec = get_stored_embedding(msg_id)
                if prev_vec is None:
                    continue
                if cosine_similarity(raw_vec, prev_vec) > CONTEXT_SIMILARITY_THRESHOLD:
                    filtered.append((prev_author, prev_content))
            ctx_msgs = filtered
            logger.debug(
                f"Context filter: {len(filtered)}/{len(previous)} msgs kept "
                f"for msg:{message_id}")
        except Exception as e:
            logger.warning(f"Similarity filter failed, using unfiltered: {e}")
            ctx_msgs = [(a, c) for _, a, c in previous]

        if not ctx_msgs:
            return f"{author}: {content}"
        ctx_parts = " | ".join(f"{a}: {c[:120]}" for a, c in ctx_msgs if c.strip())
        return f"[Context: {ctx_parts}]\n{author}: {content}" if ctx_parts \
            else f"{author}: {content}"

    except Exception as e:
        logger.warning(f"build_contextual_text failed msg {message_id}: {e}")
        return content
