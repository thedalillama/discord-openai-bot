# utils/context_manager.py
# Version 1.0.0
"""
Token-budget-aware context management and usage tracking for AI provider API calls.

CHANGES v1.0.0: Initial implementation (SOW v2.23.0)
- ADDED: estimate_tokens() using tiktoken cl100k_base for all providers
- ADDED: build_context_for_provider() — budget-aware message list builder
- ADDED: record_usage() / get_channel_usage() — per-channel token accumulator
- DESIGN: Calls prepare_messages_for_api() internally for noise filtering,
  then applies token budget on the filtered result
- DESIGN: Uses percentage-based budget (CONTEXT_BUDGET_PERCENT) to absorb
  cross-provider tokenizer variance (tiktoken is approximate for Anthropic)
- DESIGN: tiktoken loaded lazily on first use, cached after first load
- FALLBACK: len(text) / 3.2 if tiktoken unavailable

This module sits between bot.py and the AI provider call pipeline. It ensures
every API call fits within the active provider's context window regardless of
message content size. The message-count trim (MAX_HISTORY) in bot.py remains
as a coarse memory bound; the token budget here is the precise API safety layer.

The usage accumulator tracks per-channel token consumption for cost analysis.
Each provider calls record_usage() after every API call. Totals reset on restart.
"""
from collections import defaultdict
from config import CONTEXT_BUDGET_PERCENT
from utils.history.message_processing import prepare_messages_for_api
from utils.logging_utils import get_logger

logger = get_logger('context_manager')

# --- Module-level tiktoken state — lazy loaded, cached after first use ---

_tiktoken_encoding = None
_tiktoken_available = None

# Per-message overhead for role/formatting tokens (OpenAI documents ~4 tokens
# per message for role, delimiters, and formatting metadata)
MSG_OVERHEAD = 4

# --- Token usage accumulator — resets on restart ---

_channel_usage = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})


def _get_encoding():
    """
    Lazy-load and cache tiktoken cl100k_base encoding.

    Returns:
        tiktoken.Encoding or None: Cached encoding, or None if unavailable
    """
    global _tiktoken_encoding, _tiktoken_available

    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
            logger.debug("tiktoken cl100k_base encoding loaded successfully")
        except ImportError:
            _tiktoken_available = False
            logger.warning(
                "tiktoken not installed — using character-based token estimation. "
                "Install tiktoken for accurate counting: pip install tiktoken"
            )

    return _tiktoken_encoding


def estimate_tokens(text):
    """
    Estimate token count for a text string.

    Uses tiktoken cl100k_base encoding for all providers. This is exact for
    OpenAI, near-exact for DeepSeek (~95-99%), and approximate for Anthropic
    (~10-15% variance). Falls back to len(text) / 3.2 if tiktoken unavailable.

    Args:
        text: String to count tokens for

    Returns:
        int: Estimated token count
    """
    if not text:
        return 0

    encoding = _get_encoding()
    if encoding is not None:
        return len(encoding.encode(text))

    return int(len(text) / 3.2)


def record_usage(channel_id, provider_name, input_tokens, output_tokens):
    """
    Record token usage from an API call and log at INFO level.

    Called by each provider after a successful API response. Accumulates
    per-channel totals for cost analysis. Totals reset on bot restart.

    Args:
        channel_id: Discord channel ID (may be None for non-channel calls)
        provider_name: Provider name string for log identification
        input_tokens: Prompt/input token count from API response
        output_tokens: Completion/output token count from API response
    """
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
        logger.debug(
            f"Cumulative [{provider_name}] ch:{channel_id}: "
            f"{usage['input']} in + {usage['output']} out ({usage['calls']} calls)"
        )


def get_channel_usage(channel_id):
    """
    Return accumulated usage dict for a channel.

    Returns:
        dict: {"input": int, "output": int, "calls": int} or zeros if no usage
    """
    return dict(_channel_usage.get(channel_id, {"input": 0, "output": 0, "calls": 0}))


def build_context_for_provider(channel_id, provider):
    """
    Build a token-budget-aware message list for an AI provider call.

    Calls prepare_messages_for_api() to get the noise-filtered message list,
    then trims from the oldest non-system messages until the total fits
    within the provider's input token budget.

    Budget formula:
        input_budget = (context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output

    Args:
        channel_id: Discord channel ID
        provider: AIProvider instance with max_context_length,
                  max_response_tokens, and name attributes

    Returns:
        list: Messages fitting within provider's token budget
    """
    all_messages = prepare_messages_for_api(channel_id)

    if not all_messages:
        logger.warning(f"No messages from prepare_messages_for_api for channel {channel_id}")
        return all_messages

    context_window = provider.max_context_length
    max_output = provider.max_response_tokens
    budget = int(context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output

    if budget <= 0:
        logger.warning(
            f"Token budget is non-positive ({budget} tokens) for {provider.name}. "
            f"Check CONTEXT_BUDGET_PERCENT ({CONTEXT_BUDGET_PERCENT}) and "
            f"provider limits. Returning all messages."
        )
        return all_messages

    system_msg = all_messages[0]
    conversation_msgs = all_messages[1:]

    system_tokens = estimate_tokens(system_msg["content"]) + MSG_OVERHEAD
    remaining_budget = budget - system_tokens

    if remaining_budget <= 0:
        logger.warning(
            f"System prompt alone ({system_tokens} tokens) exceeds input budget "
            f"({budget} tokens) for {provider.name}. Sending system prompt only."
        )
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
        f"Context budget for {provider.name}: {budget} tokens "
        f"(window={context_window}, {CONTEXT_BUDGET_PERCENT}% budget, "
        f"output_reserve={max_output})"
    )
    logger.debug(
        f"Context built: {total_tokens} tokens used, "
        f"{len(selected)}/{len(conversation_msgs)} messages included, "
        f"{dropped} dropped"
    )

    if dropped > 0:
        logger.info(
            f"Token budget trim: dropped {dropped} oldest messages "
            f"for channel {channel_id} ({provider.name})"
        )

    return [system_msg] + selected
