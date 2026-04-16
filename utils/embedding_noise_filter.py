# utils/embedding_noise_filter.py
# Version 1.0.0
"""
Embedding noise filter — single authoritative gate for what gets embedded.

CREATED v1.0.0: Extracted from raw_events.py (SOW v5.13.0)
- should_skip_embedding(): replaces _looks_like_diagnostic() + inline prefix
  checks in raw_events.py; also applied in embedding_store.py backfill path.
- Messages returning True are stored in SQLite but not embedded or assigned.

Skip criteria:
  1. Empty or whitespace-only
  2. Commands (! prefix) or bot output (ℹ️/⚙️ prefix)
  3. Bot diagnostic output (prefix/substring guards)
  4. Known non-conversational content (deleted message placeholders)
  5. Fewer than MIN_EMBED_WORDS words, unless message ends with '?'
"""

# Minimum word count for embedding. Messages below this threshold are too
# thin to carry semantic meaning even with context prepending. Questions
# (ending with ?) are exempt — even short questions have retrieval value.
MIN_EMBED_WORDS = 4

# Content strings that indicate non-conversational messages (lowercased).
_SKIP_CONTENT = {
    "[original message deleted]",
}

# Diagnostic output prefixes — checked for bot-authored messages only.
_DIAGNOSTIC_PREFIXES = (
    'Cluster ', 'Parameters:', 'Processed:',
    '**Cluster Analysis', '**Cluster Summariz', '**Overview**',
)

# Substrings that identify discord.py built-in command output (e.g. !help).
_DIAGNOSTIC_SUBSTRINGS = (
    'Type !help command for more info',
)


def should_skip_embedding(content, is_bot_author):
    """Return True if a message should be excluded from embedding.

    Messages are always stored in SQLite regardless of this filter.
    Only the embedding and cluster-assignment pipeline is affected.

    Args:
        content: Message text (may be empty or None).
        is_bot_author: True if the message was sent by a bot account.

    Returns:
        True to skip embedding; False to embed normally.
    """
    if not content or not content.strip():
        return True

    if content.startswith(('!', 'ℹ️', '⚙️')):
        return True

    if is_bot_author:
        if (any(content.startswith(p) for p in _DIAGNOSTIC_PREFIXES) or
                any(s in content for s in _DIAGNOSTIC_SUBSTRINGS)):
            return True

    if content.strip().lower() in _SKIP_CONTENT:
        return True

    words = content.split()
    if len(words) < MIN_EMBED_WORDS and not content.rstrip().endswith('?'):
        return True

    return False
