# utils/poison_filter.py
# Version 1.0.0
"""
DB helpers for identifying and soft-deleting known-bad bot responses.
Used by !debug poison command (POISON_CLEANUP_HANDOFF).

Known-bad categories:
  qc_fail   — "ℹ️ I was unable to produce a verified response..."
  api_error — "I'm sorry an API error occurred..."
"""
import sqlite3
from config import DATABASE_PATH


def _classify_poison(content):
    """Return poison category string, or None if not known-bad."""
    if not content:
        return None
    s = content.strip()
    if s.startswith('ℹ️') and 'unable to produce a verified' in s:
        return 'qc_fail'
    if "I'm sorry an API error occurred" in s:
        return 'api_error'
    return None


def find_poison_candidates(channel_id):
    """Return list of (message_id, content, reason) for known-bad bot messages."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, content FROM messages "
            "WHERE channel_id=? AND is_bot_author=1 AND is_deleted=0 "
            "ORDER BY id DESC",
            (channel_id,)).fetchall()
    finally:
        conn.close()
    results = []
    for mid, content in rows:
        reason = _classify_poison(content)
        if reason:
            results.append((mid, content, reason))
    return results


def soft_delete_messages(channel_id, message_ids):
    """Soft-delete messages by setting is_deleted=1. Returns row count affected."""
    if not message_ids:
        return 0
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        ph = ",".join("?" * len(message_ids))
        cur = conn.execute(
            f"UPDATE messages SET is_deleted=1 "
            f"WHERE channel_id=? AND id IN ({ph})",
            [channel_id] + list(message_ids))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
