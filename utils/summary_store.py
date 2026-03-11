# utils/summary_store.py
# Version 1.0.0
"""
SQLite read/write operations for the channel_summaries table.

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
- ADDED: save_channel_summary() — upsert summary for a channel
- ADDED: get_channel_summary() — retrieve (summary_json, last_message_id) tuple

Note: Placed here rather than in message_store.py (as the SOW specifies) to
keep message_store.py under the mandatory 250-line limit. message_store.py is
already at 246 lines; adding two functions would exceed the limit.
"""
from datetime import datetime, timezone
from utils.logging_utils import get_logger

logger = get_logger('summary_store')


def save_channel_summary(channel_id, summary_json, message_count, last_message_id):
    """
    Insert or update the summary for a channel in channel_summaries.

    Args:
        channel_id:       Discord channel ID
        summary_json:     Serialized summary JSON string
        message_count:    Total number of messages summarized
        last_message_id:  Snowflake ID of the last message included
    """
    from utils.message_store import _get_conn
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO channel_summaries
               (channel_id, summary_json, updated_at, message_count, last_message_id)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(channel_id) DO UPDATE SET
               summary_json    = excluded.summary_json,
               updated_at      = excluded.updated_at,
               message_count   = excluded.message_count,
               last_message_id = excluded.last_message_id""",
        (str(channel_id), summary_json, now, message_count, last_message_id),
    )
    conn.commit()
    logger.debug(
        f"Saved summary for channel {channel_id}: "
        f"{message_count} messages, last_id={last_message_id}"
    )


def get_channel_summary(channel_id):
    """
    Retrieve the stored summary for a channel.

    Args:
        channel_id: Discord channel ID

    Returns:
        tuple: (summary_json: str, last_message_id: int) or (None, None)
    """
    from utils.message_store import _get_conn
    conn = _get_conn()
    row = conn.execute(
        "SELECT summary_json, last_message_id FROM channel_summaries WHERE channel_id = ?",
        (str(channel_id),),
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)
