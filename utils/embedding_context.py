# utils/embedding_context.py
# Version 1.5.0
"""
Context construction for context-prepended message embeddings (SOW v5.6.0).

CHANGES v1.5.0: Threshold rename and separation (SOW v5.12.0)
- REMOVED: module-level CONTEXT_SIMILARITY_THRESHOLD constant (now EMBEDDING_CONTEXT_MIN_SCORE in config.py)
- CHANGED: build_contextual_text() uses EMBEDDING_CONTEXT_MIN_SCORE from config
- CHANGED: embed_query_with_smart_context() uses QUERY_TOPIC_SHIFT_THRESHOLD from config
  instead of RETRIEVAL_MIN_SCORE — these control different decisions and can now be
  tuned independently. No behavioral change — values unchanged (0.3 and 0.5).
CHANGES v1.4.0: raw_vec + raw_vecs_cache params for bulk pre-batching (SOW v5.8.2)
- MODIFIED: build_contextual_text() accepts optional raw_vec (pre-computed vec
  for current msg) and raw_vecs_cache ({msg_id: vec} for prev msg lookups).
  Bulk callers pre-batch all raws and pass them in (0 per-msg API calls);
  single-message callers omit both params — behavior unchanged.
CHANGES v1.3.0: Topic-boundary-aware context filtering (SOW v5.8.0)
- ADDED: CONTEXT_SIMILARITY_THRESHOLD = 0.3; filters previous messages by
  cosine similarity; questions always included; fallback to unfiltered.
- MODIFIED: get_previous_messages() returns (message_id, author, content).
CHANGES v1.2.0: embed_query_with_smart_context() returns (vec, path_name).
CHANGES v1.1.0: is_question(), embed_query_with_smart_context().
CREATED v1.0.0: build_contextual_text(), get_previous_messages(), get_reply_context().

All DB functions are synchronous; wrap in asyncio.to_thread() at call sites.
Graceful degradation: on any error, build_contextual_text() returns raw content.
"""
import sqlite3
from config import DATABASE_PATH, EMBEDDING_CONTEXT_MIN_SCORE, QUERY_TOPIC_SHIFT_THRESHOLD
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
        (vector, path_name) tuple, or (None, "raw") on total failure.
    """
    from utils.embedding_store import embed_text, cosine_similarity, get_stored_embedding

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
            f"Query Path 2: sim={sim:.3f} vs threshold={QUERY_TOPIC_SHIFT_THRESHOLD} "
            f"ch:{channel_id}")
        if sim > QUERY_TOPIC_SHIFT_THRESHOLD:
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
                           reply_to_id=None, window=3,
                           raw_vec=None, raw_vecs_cache=None):
    """Build context-prepended text for embedding with topic-boundary filtering.

    raw_vec: pre-computed embedding for the current message. If None, calls
      embed_text() internally (single-message path).
    raw_vecs_cache: dict of {message_id: vec} for previous message lookups.
      If None, falls back to get_stored_embedding() (single-message path).
    Reply chains bypass the similarity check entirely.
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
            cur_vec = raw_vec if raw_vec is not None else embed_text(f"{author}: {content}")
            if cur_vec is None:
                raise ValueError("raw embed returned None")
            filtered = []
            for msg_id, prev_author, prev_content in previous:
                if is_question(prev_content):
                    filtered.append((prev_author, prev_content))
                    continue
                prev_vec = (raw_vecs_cache.get(msg_id) if raw_vecs_cache
                            else None) or get_stored_embedding(msg_id)
                if prev_vec is None:
                    continue
                if cosine_similarity(cur_vec, prev_vec) > EMBEDDING_CONTEXT_MIN_SCORE:
                    filtered.append((prev_author, prev_content))
            ctx_msgs = filtered
            logger.debug(f"Context filter: {len(filtered)}/{len(previous)} kept msg:{message_id}")
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
