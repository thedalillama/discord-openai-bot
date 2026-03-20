# utils/context_manager.py
# Version 1.1.0
"""
Token-budget-aware context management and usage tracking.

CHANGES v1.1.0: M3 — Inject summary into system prompt
- MODIFIED: build_context_for_provider() loads channel summary and appends
  it to the system prompt as a single combined system message. The full
  summary (decisions, topics, facts, actions, questions) is included.
  If no summary exists, behavior is unchanged.
- ADDED: _load_summary_text() — loads and formats the channel summary

CHANGES v1.0.0: Initial implementation (SOW v2.23.0)
- estimate_tokens(), build_context_for_provider(), record_usage()
"""
import json
from collections import defaultdict
from config import CONTEXT_BUDGET_PERCENT
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


def _load_summary_text(channel_id):
    """Load and format the channel summary for system prompt injection.
    Returns formatted text string or empty string if no summary."""
    try:
        from utils.summary_store import get_channel_summary
        from utils.summary_display import format_summary_for_context
        raw, _ = get_channel_summary(channel_id)
        if not raw:
            return ""
        summary = json.loads(raw)
        return format_summary_for_context(summary)
    except Exception as e:
        logger.warning(f"Failed to load summary for context: {e}")
        return ""


def build_context_for_provider(channel_id, provider):
    """Build a token-budget-aware message list for an AI provider call.

    Loads the channel summary and appends it to the system prompt.
    Then trims oldest conversation messages to fit within budget.
    """
    all_messages = prepare_messages_for_api(channel_id)

    if not all_messages:
        logger.warning(f"No messages for channel {channel_id}")
        return all_messages

    context_window = provider.max_context_length
    max_output = provider.max_response_tokens
    budget = int(context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output

    if budget <= 0:
        logger.warning(f"Token budget non-positive ({budget}) for {provider.name}")
        return all_messages

    # Build combined system prompt with summary
    system_msg = all_messages[0]
    summary_text = _load_summary_text(channel_id)

    if summary_text:
        combined = (
            f"{system_msg['content']}\n\n"
            f"--- CONVERSATION CONTEXT ---\n"
            f"The following is a summary of this channel's conversation "
            f"history. Use it to inform your responses.\n\n"
            f"{summary_text}"
        )
        system_msg = {"role": "system", "content": combined}
        summary_tokens = estimate_tokens(summary_text)
        logger.debug(
            f"Summary injected: {summary_tokens} tokens for ch:{channel_id}")

    conversation_msgs = all_messages[1:]
    system_tokens = estimate_tokens(system_msg["content"]) + MSG_OVERHEAD
    remaining_budget = budget - system_tokens

    if remaining_budget <= 0:
        logger.warning(
            f"System prompt + summary ({system_tokens} tokens) exceeds "
            f"budget ({budget}) for {provider.name}")
        return [system_msg]

    selected = []
    tokens_used = 0
    for msg in reversed(conversation_msgs):
        msg_tokens = estimate_tokens(msg["content"]) + MSG_OVERHEAD
        if tokens_used + msg_tokens > remaining_budget:
            break
        selected.append(msg)
        tokens_used += msg_tokens
    selected.reverse()

    total_tokens = system_tokens + tokens_used
    dropped = len(conversation_msgs) - len(selected)

    logger.debug(
        f"Context for {provider.name}: {total_tokens} tokens, "
        f"{len(selected)}/{len(conversation_msgs)} msgs, "
        f"{dropped} dropped")

    if dropped > 0:
        logger.info(
            f"Token budget trim: dropped {dropped} oldest messages "
            f"for ch:{channel_id} ({provider.name})")

    return [system_msg] + selected
