# utils/models.py
# Version 1.1.0
"""
Data models for the Discord bot persistence layer.

CREATED v1.0.0: SQLite message persistence (SOW v3.0.0)
- StoredMessage dataclass for lightweight message representation
- ~350 bytes per instance vs ~1,200 for discord.py Message objects
- Fields limited to what summarization needs: id, channel_id,
  author_id, author_name, content, created_at, message_type, is_deleted

CHANGES v1.1.0: Schema extension & enhanced capture (SOW v3.1.0)
- ADDED: reply_to_message_id — message ID of the message this replies to
- ADDED: thread_id — channel ID of the thread this message belongs to
- ADDED: edited_at — ISO 8601 timestamp of last edit (None if never edited)
- ADDED: deleted_at — ISO 8601 timestamp of deletion (None if not deleted)
- ADDED: attachments_metadata — JSON string of attachment info, or None
- All new fields default to None for backward compatibility with existing rows
"""
from dataclasses import dataclass, field


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
        reply_to_message_id: Snowflake ID of replied-to message, or None
        thread_id: Snowflake ID of thread channel, or None
        edited_at: ISO 8601 timestamp of last edit, or None
        deleted_at: ISO 8601 timestamp of deletion, or None
        attachments_metadata: JSON string of attachment info, or None
    """
    id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    created_at: str
    message_type: int = 0
    is_deleted: bool = False
    # v3.1.0 additions — all optional, default None
    reply_to_message_id: int | None = None
    thread_id: int | None = None
    edited_at: str | None = None
    deleted_at: str | None = None
    attachments_metadata: str | None = None
