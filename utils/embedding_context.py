# utils/embedding_context.py
# Version 1.0.0
"""
Context construction for context-prepended message embeddings (SOW v5.6.0).

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
