# utils/message_store.py
# Version 1.2.0
"""
SQLite message persistence layer for the Discord bot.

CREATED v1.0.0: WAL-mode SQLite, insert/update/soft-delete, channel state tracking
CHANGES v1.1.0: Schema extension — reply_to_message_id, thread_id, attachments_metadata;
  init_database() runs migrations; update_message_content_and_edit_time()
CHANGES v1.2.0: is_bot_author column in insert and get_channel_messages()
"""
import sqlite3
import os
from datetime import datetime, timezone

from config import DATABASE_PATH
from utils.logging_utils import get_logger
from utils.models import StoredMessage

logger = get_logger('message_store')

# Module-level connection — initialized once via init_database()
_conn = None


def init_database():
    """
    Initialize the SQLite database connection and run migrations.

    Creates the data directory if needed, opens the database, enables
    WAL mode, and runs all pending schema migrations via db_migration.py.
    Must be called once at startup before any other operations.
    """
    global _conn

    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logger.info(f"Created database directory: {db_dir}")

    _conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode = WAL")
    _conn.execute("PRAGMA synchronous = NORMAL")

    from utils.db_migration import run_migrations
    run_migrations(_conn)

    logger.info(f"Database initialized at {DATABASE_PATH}")
    journal = _conn.execute("PRAGMA journal_mode").fetchone()[0]
    logger.info(f"Journal mode: {journal}")


def _get_conn():
    """Get the database connection, raising if not initialized."""
    if _conn is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _conn


def insert_message(msg):
    """
    Insert a message into the database. Ignores duplicates (same ID).

    Args:
        msg: StoredMessage instance
    """
    conn = _get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO messages
           (id, channel_id, author_id, author_name, content,
            created_at, message_type, is_deleted,
            reply_to_message_id, thread_id, attachments_metadata,
            is_bot_author)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg.id, msg.channel_id, msg.author_id, msg.author_name,
         msg.content, msg.created_at, msg.message_type, int(msg.is_deleted),
         msg.reply_to_message_id, msg.thread_id, msg.attachments_metadata,
         int(msg.is_bot_author))
    )
    conn.commit()


def insert_messages_batch(messages):
    """
    Insert multiple messages in a single transaction.

    Args:
        messages: List of StoredMessage instances
    """
    if not messages:
        return
    conn = _get_conn()
    conn.executemany(
        """INSERT OR IGNORE INTO messages
           (id, channel_id, author_id, author_name, content,
            created_at, message_type, is_deleted,
            reply_to_message_id, thread_id, attachments_metadata,
            is_bot_author)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(m.id, m.channel_id, m.author_id, m.author_name,
          m.content, m.created_at, m.message_type, int(m.is_deleted),
          m.reply_to_message_id, m.thread_id, m.attachments_metadata,
          int(m.is_bot_author))
         for m in messages]
    )
    conn.commit()
    logger.debug(f"Batch inserted {len(messages)} messages")


def update_message_content_and_edit_time(message_id, new_content):
    """
    Update message content and set edited_at timestamp (for edits).

    Args:
        message_id: Discord snowflake message ID
        new_content: Updated message text
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE messages SET content = ?, edited_at = ? WHERE id = ?",
        (new_content, now, message_id)
    )
    conn.commit()


def soft_delete_message(message_id):
    """
    Mark a message as deleted (soft delete). Never hard-deletes.

    Args:
        message_id: Discord snowflake message ID
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE messages SET is_deleted = 1, deleted_at = ? WHERE id = ?",
        (now, message_id)
    )
    conn.commit()


def get_channel_messages(channel_id, include_deleted=False):
    """
    Retrieve all messages for a channel, ordered by creation time.

    Args:
        channel_id: Discord channel ID
        include_deleted: If False (default), exclude soft-deleted messages

    Returns:
        list[StoredMessage]: Messages in chronological order
    """
    conn = _get_conn()
    if include_deleted:
        rows = conn.execute(
            "SELECT * FROM messages WHERE channel_id = ? ORDER BY created_at",
            (channel_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE channel_id = ? AND is_deleted = 0
               ORDER BY created_at""",
            (channel_id,)
        ).fetchall()

    return [StoredMessage(
        id=r[0], channel_id=r[1], author_id=r[2], author_name=r[3],
        content=r[4], created_at=r[5], message_type=r[6],
        is_deleted=bool(r[7]),
        reply_to_message_id=r[8], thread_id=r[9],
        edited_at=r[10], deleted_at=r[11], attachments_metadata=r[12],
        is_bot_author=bool(r[13]) if r[13] is not None else False,
    ) for r in rows]


def get_channel_message_count(channel_id):
    """Return the count of non-deleted messages for a channel."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE channel_id = ? AND is_deleted = 0",
        (channel_id,)
    ).fetchone()
    return row[0] if row else 0


def get_last_processed_id(channel_id):
    """
    Get the last processed message ID for a channel.

    Returns:
        int or None: The last processed message ID, or None if no state exists
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT last_processed_id FROM channel_state WHERE channel_id = ?",
        (channel_id,)
    ).fetchone()
    return row[0] if row else None


def update_last_processed_id(channel_id, message_id):
    """
    Update the last processed message ID for a channel.

    Args:
        channel_id: Discord channel ID
        message_id: Discord snowflake message ID
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO channel_state (channel_id, last_processed_id, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(channel_id) DO UPDATE SET
               last_processed_id = excluded.last_processed_id,
               updated_at = excluded.updated_at""",
        (channel_id, message_id, now)
    )
    conn.commit()


def get_database_stats():
    """
    Get summary statistics about the database.

    Returns:
        dict: message_count, channel_count, database_size_mb
    """
    conn = _get_conn()
    msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    ch_count = conn.execute(
        "SELECT COUNT(DISTINCT channel_id) FROM messages"
    ).fetchone()[0]
    size_mb = os.path.getsize(DATABASE_PATH) / (1024 * 1024)
    return {
        "message_count": msg_count,
        "channel_count": ch_count,
        "database_size_mb": round(size_mb, 2)
    }
