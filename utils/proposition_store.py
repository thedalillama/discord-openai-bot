# utils/proposition_store.py
# Version 1.0.0
"""
Proposition CRUD and embedding storage (SOW v6.3.0).

Propositions are atomic, self-contained claims decomposed from segment
syntheses by GPT-4o-mini. Each proposition gets its own embedding for
precise query-time matching. At retrieval, propositions are scored against
the query and collapsed to max-score-per-segment before entering RRF fusion.

Functions:
- store_propositions(channel_id, segment_id, props) — bulk insert
- clear_channel_propositions(channel_id) — delete all for a channel
- get_proposition_embeddings(channel_id) — (prop_id, seg_id, content, vec)
- store_proposition_embedding(prop_id, embedding) — upsert blob
- get_proposition_count(channel_id) — count for diagnostics

CREATED v1.0.0: Proposition decomposition pipeline (SOW v6.3.0)
"""
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH
from utils.embedding_store import pack_embedding, unpack_embedding
from utils.logging_utils import get_logger

logger = get_logger('proposition_store')


def store_propositions(channel_id, segment_id, props):
    """Bulk insert propositions for a segment. IDs: prop-{segment_id}-{seq}.

    Args:
        channel_id: Discord channel ID
        segment_id: parent segment ID
        props: list of proposition strings

    Returns: list of generated proposition IDs.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    created_at = datetime.now(timezone.utc).isoformat()
    prop_ids = []
    try:
        for seq, content in enumerate(props):
            prop_id = f"prop-{segment_id}-{seq}"
            conn.execute(
                "INSERT OR REPLACE INTO propositions "
                "(id, segment_id, channel_id, content, created_at) "
                "VALUES (?,?,?,?,?)",
                (prop_id, segment_id, channel_id, content, created_at))
            prop_ids.append(prop_id)
        conn.commit()
        return prop_ids
    except Exception as e:
        logger.warning(f"store_propositions failed seg:{segment_id}: {e}")
        return []
    finally:
        conn.close()


def clear_channel_propositions(channel_id):
    """Delete all propositions for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM propositions WHERE channel_id=?", (channel_id,))
        conn.commit()
        logger.info(f"Cleared propositions for ch:{channel_id}")
    except Exception as e:
        logger.warning(f"Failed to clear propositions ch:{channel_id}: {e}")
    finally:
        conn.close()


def get_proposition_embeddings(channel_id):
    """Return (prop_id, segment_id, content, vector) for all embedded props.

    Called at query time by find_relevant_propositions(). Loads all
    proposition embeddings into memory — ~3-4MB for 500-750 propositions.
    Returns [] on failure so callers degrade gracefully.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, segment_id, content, embedding FROM propositions "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
        return [(r[0], r[1], r[2], unpack_embedding(r[3])) for r in rows]
    except Exception as e:
        logger.warning(f"get_proposition_embeddings failed ch:{channel_id}: {e}")
        return []
    finally:
        conn.close()


def store_proposition_embedding(prop_id, embedding):
    """Upsert a proposition embedding blob."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "UPDATE propositions SET embedding=? WHERE id=?",
            (pack_embedding(embedding), prop_id))
        conn.commit()
    except Exception as e:
        logger.warning(f"store_proposition_embedding failed {prop_id}: {e}")
    finally:
        conn.close()


def get_proposition_count(channel_id):
    """Return count of propositions (embedded + pending) for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM propositions WHERE channel_id=?",
            (channel_id,)).fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.warning(f"get_proposition_count failed ch:{channel_id}: {e}")
        return 0
    finally:
        conn.close()
