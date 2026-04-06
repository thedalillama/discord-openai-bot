# utils/receipt_store.py
# Version 1.0.0
"""
Context receipt storage for bot response explainability (SOW v5.7.0).

CREATED v1.0.0: Receipt persistence (SOW v5.7.0)
- save_receipt() — store context receipt for a bot response
- get_latest_receipt() — most recent receipt for a channel
- get_receipt_by_response() — receipt for a specific response message ID

Table response_context_receipts already exists (schema 002.sql, never populated).
All functions are synchronous; wrap in asyncio.to_thread() at call sites.
Fail-safe: save_receipt() raises on failure so the caller's try/except fires —
receipt errors must never block bot responses.
"""
import json
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH
from utils.logging_utils import get_logger

logger = get_logger('receipt_store')


def save_receipt(response_message_id, user_message_id, channel_id, receipt_dict):
    """Store a context receipt for a bot response.

    Args:
        response_message_id: Discord message ID of the bot's response
        user_message_id: Discord message ID of the user's message
        channel_id: Discord channel ID
        receipt_dict: Dict of context assembly details
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO response_context_receipts "
            "(response_message_id, user_message_id, channel_id, created_at, receipt_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (response_message_id, user_message_id, channel_id,
             now, json.dumps(receipt_dict)))
        conn.commit()
        logger.debug(
            f"Saved receipt for response {response_message_id} ch:{channel_id}")
    except Exception as e:
        logger.warning(f"save_receipt failed for {response_message_id}: {e}")
        raise
    finally:
        conn.close()


def get_latest_receipt(channel_id):
    """Get the most recent receipt for a channel.

    Returns:
        tuple: (response_message_id, receipt_dict) or (None, None)
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT response_message_id, receipt_json "
            "FROM response_context_receipts "
            "WHERE channel_id=? ORDER BY created_at DESC LIMIT 1",
            (channel_id,)).fetchone()
        if not row:
            return None, None
        return row[0], json.loads(row[1])
    except Exception as e:
        logger.warning(f"get_latest_receipt failed ch:{channel_id}: {e}")
        return None, None
    finally:
        conn.close()


def get_receipt_by_response(response_message_id):
    """Get receipt for a specific bot response message.

    Returns:
        dict: receipt_dict or None
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT receipt_json FROM response_context_receipts "
            "WHERE response_message_id=?",
            (response_message_id,)).fetchone()
        return json.loads(row[0]) if row else None
    except Exception as e:
        logger.warning(
            f"get_receipt_by_response failed for {response_message_id}: {e}")
        return None
    finally:
        conn.close()
