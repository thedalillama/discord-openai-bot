# utils/context_manager.py
# Version 2.3.0
"""
Token-budget-aware context management and usage tracking.

CHANGES v2.3.0: Extract retrieval to context_retrieval.py (SOW v5.6.0)
- REMOVED: _fallback_msg_search(), _retrieve_cluster_context() — moved to
  utils/context_retrieval.py; imported here for use in build_context_for_provider()
- UNCHANGED: estimate_tokens(), record_usage(), get_channel_usage(),
  build_context_for_provider() — public API intact

CHANGES v2.2.0: Cluster-based retrieval replaces topic-based (SOW v5.5.0)
CHANGES v2.1.5: Inject today's date into context block
CHANGES v2.1.4: Prepend [YYYY-MM-DD] to retrieved message lines
CHANGES v2.1.3: Restore always-on context injection
CHANGES v2.1.2: Full summary fallback logs WARNING instead of DEBUG
CHANGES v2.1.1: Richer retrieval debug logging
CHANGES v2.1.0: Direct message embedding fallback (SOW v4.1.0)
CHANGES v2.0.0: Semantic retrieval replaces full summary injection (SOW v4.0.0)
CREATED v1.0.0: Initial implementation (SOW v2.23.0)
"""
import json
from collections import defaultdict
from datetime import date
from config import (CONTEXT_BUDGET_PERCENT, MAX_RECENT_MESSAGES)
from utils.history.message_processing import prepare_messages_for_api
from utils.logging_utils import get_logger

logger = get_logger('context_manager')

_tiktoken_encoding = None
_tiktoken_available = None
MSG_OVERHEAD = 4
_channel_usage = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})


def _get_encoding():
    """Lazy-load and cache tiktoken cl100k_base encoding."""
    global _tiktoken_encoding, _tiktoken_available
    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
        except ImportError:
            _tiktoken_available = False
            logger.warning("tiktoken not installed — using character estimate")
    return _tiktoken_encoding


def estimate_tokens(text):
    """Estimate token count. Uses tiktoken if available, else len/3.2."""
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    return int(len(text) / 3.2)


def record_usage(channel_id, provider_name, input_tokens, output_tokens):
    """Record token usage from an API call and log at INFO level."""
    total = input_tokens + output_tokens
    logger.info(
        f"Token usage [{provider_name}] ch:{channel_id}: "
        f"{input_tokens} in + {output_tokens} out = {total} total"
    )
    if channel_id is not None:
        usage = _channel_usage[channel_id]
        usage["input"] += input_tokens
        usage["output"] += output_tokens
        usage["calls"] += 1


def get_channel_usage(channel_id):
    """Return accumulated usage dict for a channel."""
    return dict(_channel_usage.get(
        channel_id, {"input": 0, "output": 0, "calls": 0}))


def _load_summary(channel_id):
    """Load channel summary dict. Returns None if not found."""
    try:
        from utils.summary_store import get_channel_summary
        raw, _ = get_channel_summary(channel_id)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Failed to load summary for ch:{channel_id}: {e}")
        return None


def build_context_for_provider(channel_id, provider):
    """Build a token-budget-aware message list for an AI provider call.

    Injects always-on context (overview, facts, actions, questions) plus
    semantically retrieved cluster messages. Falls back to full summary
    injection if retrieval is unavailable.
    """
    from utils.context_retrieval import _retrieve_cluster_context

    all_messages = prepare_messages_for_api(channel_id)

    if not all_messages:
        logger.warning(f"No messages for channel {channel_id}")
        return all_messages

    context_window = provider.max_context_length
    max_output = provider.max_response_tokens
    budget = int(context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output

    if budget <= 0:
        logger.warning(
            f"Token budget non-positive ({budget}) for {provider.name}")
        return all_messages

    system_msg = all_messages[0]
    conversation_msgs = all_messages[1:]
    summary = _load_summary(channel_id)

    if summary:
        from utils.summary_display import (
            format_always_on_context, format_summary_for_context)

        always_on = format_always_on_context(summary)
        always_on_tokens = estimate_tokens(always_on)

        system_base_tokens = estimate_tokens(system_msg["content"]) + MSG_OVERHEAD
        retrieval_budget = max(0, budget - system_base_tokens - always_on_tokens)

        retrieved, retrieved_tokens = _retrieve_cluster_context(
            channel_id, conversation_msgs, retrieval_budget)

        today = date.today().isoformat()
        if retrieved:
            context_block = (
                f"--- CONVERSATION CONTEXT ---\n"
                f"Today's date: {today}\n\n{always_on}\n\n"
                f"--- PAST MESSAGES FROM THIS CHANNEL (retrieved by topic relevance) ---\n"
                f"The following are real messages previously sent in this channel, "
                f"retrieved because they are relevant to the current query. "
                f"They ARE part of this conversation's history.\n\n{retrieved}"
            )
            logger.debug(
                f"Semantic context: {always_on_tokens} always-on + "
                f"{retrieved_tokens} retrieved tokens for ch:{channel_id}")
        else:
            full = format_summary_for_context(summary)
            context_block = (
                f"--- CONVERSATION CONTEXT ---\n"
                f"Today's date: {today}\n\n"
                f"The following is a summary of this channel's conversation "
                f"history. Use it to inform your responses.\n\n{full}"
            )
            logger.warning(
                f"Retrieval fully degraded for ch:{channel_id} — "
                f"no clusters and no message embeddings found.")

        logger.debug(f"Context block injected (first 2000 chars):\n{context_block[:2000]}")
        combined = f"{system_msg['content']}\n\n{context_block}"
        system_msg = {"role": "system", "content": combined}

    system_tokens = estimate_tokens(system_msg["content"]) + MSG_OVERHEAD
    remaining_budget = budget - system_tokens

    if remaining_budget <= 0:
        logger.warning(
            f"System prompt ({system_tokens} tokens) exceeds "
            f"budget ({budget}) for {provider.name}")
        return [system_msg]

    selected = []
    tokens_used = 0
    for msg in reversed(conversation_msgs):
        if len(selected) >= MAX_RECENT_MESSAGES:
            break
        msg_tokens = estimate_tokens(msg["content"]) + MSG_OVERHEAD
        if tokens_used + msg_tokens > remaining_budget:
            break
        selected.append(msg)
        tokens_used += msg_tokens
    selected.reverse()

    total_tokens = system_tokens + tokens_used
    dropped = len(conversation_msgs) - len(selected)

    if dropped > 0:
        logger.info(
            f"Token budget trim: dropped {dropped} oldest messages "
            f"for ch:{channel_id} ({provider.name})")
    else:
        logger.debug(
            f"Context for {provider.name}: {total_tokens} tokens, "
            f"{len(selected)} msgs")

    return [system_msg] + selected
