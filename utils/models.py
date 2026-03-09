# utils/models.py
# Version 1.0.0
"""
Data models for the Discord bot persistence layer.

CREATED v1.0.0: SQLite message persistence (SOW v3.0.0)
- StoredMessage dataclass for lightweight message representation
- ~350 bytes per instance vs ~1,200 for discord.py Message objects
- Fields limited to what summarization needs: id, channel_id,
  author_id, author_name, content, created_at, message_type, is_deleted
"""
from dataclasses import dataclass


@dataclass(slots=True)
class StoredMessage:
    """
    Lightweight representation of a Discord message for SQLite storage.

    Uses __slots__ via slots=True for memory efficiency. Holds only the
    fields needed for summarization and context building — no references
    to Guild, Channel, User, or other discord.py objects.

    Attributes:
        id: Discord snowflake message ID (used as SQLite primary key)
        channel_id: Discord snowflake channel ID
        author_id: Discord snowflake user ID (permanent, never changes)
        author_name: Display name at time of message (can change)
        content: Message text content
        created_at: ISO 8601 timestamp string
        message_type: Discord message type enum (0=default, 19=reply, etc.)
        is_deleted: Soft delete flag (True if message was deleted in Discord)
    """
    id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    created_at: str
    message_type: int = 0
    is_deleted: bool = False
