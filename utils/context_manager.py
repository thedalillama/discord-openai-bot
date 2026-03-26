# utils/context_manager.py
# Version 2.0.2
"""
Token-budget-aware context management and usage tracking.

CHANGES v2.0.2: Fix retrieval budget — use full remaining budget not 40% slice
- CHANGED: retrieval_budget now = budget - system_base - always_on (was * 0.4)
  The 40% cap caused only ~586 tokens to be available for retrieval. Retrieved
  content lands in the system prompt, so system_tokens is recalculated after
  and the recent-message trimmer drops oldest messages to make room naturally.

CHANGES v2.0.1: Debug logging for retrieval fallback path
- ADDED: per-step DEBUG logs in _retrieve_topic_context() explaining why
  retrieval returns empty (no query, embed failed, no topics, budget exceeded,
  all msgs excluded)

CHANGES v2.0.0: Semantic retrieval replaces full summary injection (SOW v4.0.0)
- MODIFIED: build_context_for_provider() now injects:
    Part 1 (always-on): overview, key facts, open action items, open questions
    Part 2 (retrieved): messages from topics semantically similar to latest msg
- ADDED: _retrieve_topic_context() — embeds latest user message, finds top-K
  relevant topics, fetches their linked messages, deduplicates vs recent window
- FALLBACK: If embedding fails or no topics exist, falls back to full summary
  injection (v1.1.0 behavior). Bot never fails to respond due to retrieval.

CHANGES v1.1.0: M3 — Inject summary into system prompt
- MODIFIED: build_context_for_provider() loads channel summary and appends
  it to the system prompt as a single combined system message.
- ADDED: _load_summary_text() — loads and formats the channel summary

CHANGES v1.0.0: Initial implementation (SOW v2.23.0)
- estimate_tokens(), build_context_for_provider(), record_usage()
"""
import json
from collections import defaultdict
from config import CONTEXT_BUDGET_PERCENT, RETRIEVAL_TOP_K
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


def _retrieve_topic_context(channel_id, conversation_msgs, token_budget):
    """Embed the latest user message, find relevant topics, return formatted
    context string of their linked messages.

    Returns (context_text, tokens_used). Returns ("", 0) on any failure.
    """
    try:
        from utils.embedding_store import (
            embed_text, find_relevant_topics, get_topic_messages)

        # Find latest non-empty user message
        query_text = None
        for msg in reversed(conversation_msgs):
            if msg.get("role") == "user" and msg.get("content", "").strip():
                query_text = msg["content"].strip()
                break
        if not query_text:
            logger.debug(f"Retrieval skip ch:{channel_id}: no user message in window")
            return "", 0

        query_vec = embed_text(query_text)
        if query_vec is None:
            logger.debug(f"Retrieval skip ch:{channel_id}: embed_text returned None for query {query_text[:60]!r}")
            return "", 0

        topics = find_relevant_topics(query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
        if not topics:
            logger.debug(f"Retrieval skip ch:{channel_id}: find_relevant_topics returned empty (no topic embeddings?)")
            return "", 0

        logger.debug(f"Retrieval ch:{channel_id}: {len(topics)} topics found, scores: {[round(s,3) for _,_,s in topics]}")

        # IDs already in the recent window — avoid duplication
        recent_ids = set()
        for msg in conversation_msgs:
            if "_msg_id" in msg:
                recent_ids.add(msg["_msg_id"])

        lines = []
        tokens_used = 0
        for topic_id, title, score in topics:
            msgs = get_topic_messages(topic_id, exclude_ids=recent_ids)
            if not msgs:
                logger.debug(f"  topic {topic_id!r}: 0 messages (all excluded or none linked)")
                continue
            section = f"[Topic: {title}]\n"
            section += "\n".join(
                f"{author}: {content}"
                for _, author, content, _ in msgs
            )
            section_tokens = estimate_tokens(section)
            if tokens_used + section_tokens > token_budget:
                logger.debug(f"  topic {topic_id!r}: budget exceeded ({tokens_used}+{section_tokens}>{token_budget}), stopping")
                break
            lines.append(section)
            tokens_used += section_tokens

        if not lines:
            logger.debug(f"Retrieval skip ch:{channel_id}: all {len(topics)} topics had 0 usable messages")
            return "", 0

        logger.debug(
            f"Retrieved {len(lines)} topics for ch:{channel_id} "
            f"({tokens_used} tokens, query: {query_text[:60]!r})")
        return "\n\n".join(lines), tokens_used

    except Exception as e:
        logger.warning(f"Topic retrieval failed for ch:{channel_id}: {e}")
        return "", 0


def build_context_for_provider(channel_id, provider):
    """Build a token-budget-aware message list for an AI provider call.

    Injects always-on context (overview, facts, actions, questions) plus
    semantically retrieved topic messages. Falls back to full summary
    injection if retrieval is unavailable.
    """
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

        # Full remaining budget goes to retrieval. Retrieved content is injected
        # into the system prompt, so system_tokens is recalculated below and the
        # recent-message trimmer naturally drops oldest messages to compensate.
        system_base_tokens = estimate_tokens(system_msg["content"]) + MSG_OVERHEAD
        retrieval_budget = max(0, budget - system_base_tokens - always_on_tokens)

        retrieved, retrieved_tokens = _retrieve_topic_context(
            channel_id, conversation_msgs, retrieval_budget)

        if retrieved:
            context_block = (
                f"--- CONVERSATION CONTEXT ---\n{always_on}\n\n"
                f"--- RELEVANT HISTORY ---\n{retrieved}"
            )
            logger.debug(
                f"Semantic context: {always_on_tokens} always-on + "
                f"{retrieved_tokens} retrieved tokens for ch:{channel_id}")
        else:
            # No topics retrieved — fall back to full summary
            full = format_summary_for_context(summary)
            context_block = (
                f"--- CONVERSATION CONTEXT ---\n"
                f"The following is a summary of this channel's conversation "
                f"history. Use it to inform your responses.\n\n{full}"
            )
            logger.debug(
                f"Fallback to full summary for ch:{channel_id} "
                f"(retrieval returned empty — see above for reason)")

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
