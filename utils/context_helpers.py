# utils/context_helpers.py
# Version 1.0.0
"""
Helper functions for context assembly (SOW v7.0.0 M1).
Extracted from context_manager.py to respect the 250-line limit.

CREATED v1.0.0:
- _load_summary() — load channel summary dict
- read_control_file() — mtime-cached control file injection
- _merge_dedup_sort() — merge + dedup two message lists by id
- _trim_to_budget() — trim oldest messages to fit token budget
- _format_as_turn() — format DB message dict as API turn
"""
import os
from config import CONTROL_FILE_PATH
from utils.logging_utils import get_logger

logger = get_logger('context_helpers')

_control_cache = {}


def _load_summary(channel_id):
    """Load channel summary dict. Returns None if not found."""
    import json
    try:
        from utils.summary_store import get_channel_summary
        raw, _ = get_channel_summary(channel_id)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Failed to load summary ch:{channel_id}: {e}")
        return None


def read_control_file():
    """Read control file, return contents or empty string.
    Cached with mtime check — re-read only when file changes.
    """
    path = CONTROL_FILE_PATH
    if not os.path.exists(path):
        return ""
    try:
        mtime = os.path.getmtime(path)
        if mtime == _control_cache.get("mtime"):
            return _control_cache["content"]
        with open(path) as f:
            content = f.read().strip()
        _control_cache["mtime"] = mtime
        _control_cache["content"] = content
        return content
    except Exception as e:
        logger.warning(f"Control file read failed: {e}")
        return ""


def _merge_dedup_sort(a, b):
    """Merge two message lists, dedup by id, sort chronologically."""
    seen, result = set(), []
    for msg in sorted(a + b, key=lambda m: m.get("created_at") or ""):
        if msg["id"] not in seen:
            seen.add(msg["id"])
            result.append(msg)
    return result


def _trim_to_budget(msgs, max_tokens):
    """Trim oldest messages to fit within max_tokens.
    Returns (block, tokens_used).
    """
    from utils.context_manager import estimate_tokens, MSG_OVERHEAD
    block, used = [], 0
    for msg in reversed(msgs):
        t = estimate_tokens(msg["content"]) + MSG_OVERHEAD
        if used + t > max_tokens:
            break
        block.append(msg)
        used += t
    block.reverse()
    return block, used


def _format_as_turn(msg):
    """Format a DB message dict as an API message turn."""
    role = "assistant" if msg.get("is_bot") else "user"
    date_str = (msg.get("created_at") or "")[:10]
    content = f"[{date_str}] {msg['author']}: {msg['content']}"
    return {"role": role, "content": content, "_msg_id": msg["id"]}
