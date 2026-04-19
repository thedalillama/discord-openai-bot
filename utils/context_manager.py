# utils/context_manager.py
# Version 3.0.3
"""
Token-budget-aware context management and usage tracking.

CHANGES v3.0.3: Reverse dedup — Layer 2 canonical; selected only adds SQLite-missing msgs

CHANGES v3.0.2: Add /tmp/last_full_context.json DEBUG dump (full messages array)

CHANGES v3.0.1: Fix always_on receipt missing total_tokens key (overview + control)

CHANGES v3.0.0: Three-layer context assembly (SOW v7.0.0 M1)
- ADDED: read_control_file() — re-exported from context_helpers
- MODIFIED: build_context_for_provider() — Layer 1 (system+control+always-on),
  Layer 2 (session bridge+unsummarized, guaranteed), Layer 3 (RRF, fills remainder)
- MODIFIED: receipt_data includes continuity section for !explain

CHANGES v2.5.x: receipt fixes, DEBUG dump, citation pass-through (SOW v5.9.0–v6.1.0)
CHANGES v2.4.0: Return (messages, receipt_data) tuple (SOW v5.7.0)
CHANGES v2.3.0: Extract retrieval to context_retrieval.py (SOW v5.6.0)
CREATED v1.0.0: Initial implementation (SOW v2.23.0)
"""
from collections import defaultdict
from datetime import date
from config import CONTEXT_BUDGET_PERCENT, MAX_RECENT_MESSAGES, LAYER2_BUDGET_PCT
from utils.history.message_processing import prepare_messages_for_api
from utils.context_helpers import (
    _load_summary, read_control_file, _merge_dedup_sort,
    _trim_to_budget, _format_as_turn)
from utils.logging_utils import get_logger

logger = get_logger('context_manager')

_tiktoken_encoding = None
_tiktoken_available = None
MSG_OVERHEAD = 4
_channel_usage = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})


def _get_encoding():
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
    enc = _get_encoding()
    return len(enc.encode(text)) if enc is not None else int(len(text) / 3.2)


def record_usage(channel_id, provider_name, input_tokens, output_tokens):
    """Record token usage from an API call."""
    total = input_tokens + output_tokens
    logger.info(
        f"Token usage [{provider_name}] ch:{channel_id}: "
        f"{input_tokens} in + {output_tokens} out = {total} total")
    if channel_id is not None:
        u = _channel_usage[channel_id]
        u["input"] += input_tokens
        u["output"] += output_tokens
        u["calls"] += 1


def get_channel_usage(channel_id):
    return dict(_channel_usage.get(
        channel_id, {"input": 0, "output": 0, "calls": 0}))


def build_context_for_provider(channel_id, provider):
    """Build a token-budget-aware message list for an AI provider call.

    Three-layer context assembly:
      Layer 1 (guaranteed): system prompt + control file + always-on summary
      Layer 2 (guaranteed): session bridge + unsummarized messages
      Layer 3 (fills remainder): historical RRF retrieval

    Return: (messages, receipt_data, citation_map)
    """
    from utils.context_retrieval import _retrieve_segment_context
    from utils.pipeline_state import (
        get_session_bridge_messages, get_unsummarized_messages)

    all_messages = prepare_messages_for_api(channel_id)
    if not all_messages:
        logger.warning(f"No messages for channel {channel_id}")
        return all_messages, None, {}

    context_window = provider.max_context_length
    max_output = provider.max_response_tokens
    budget = int(context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output
    if budget <= 0:
        logger.warning(f"Token budget non-positive ({budget}) for {provider.name}")
        return all_messages, None, {}

    system_msg = all_messages[0]
    conversation_msgs = all_messages[1:]
    summary = _load_summary(channel_id)
    receipt_data = None
    citation_map = {}

    # ── Layer 1: System + control file + always-on summary ──
    always_on, always_on_tokens = "", 0
    if summary:
        from utils.summary_display import format_always_on_context
        always_on = format_always_on_context(summary)
        always_on_tokens = estimate_tokens(always_on)

    control = read_control_file()
    control_tokens = estimate_tokens(control)
    today = date.today().isoformat()

    base_content = system_msg["content"]
    if control:
        base_content += f"\n\n{control}"
    if always_on:
        base_content += (
            f"\n\n--- CONVERSATION CONTEXT ---\n"
            f"Today's date: {today}\n\n{always_on}")

    base_tokens = estimate_tokens(base_content) + MSG_OVERHEAD
    remaining = budget - base_tokens
    if remaining <= 0:
        logger.warning(f"Layer 1 ({base_tokens} tok) exceeds budget ({budget})")
        return [{"role": "system", "content": base_content}], None, {}

    # ── Layer 2: Conversation continuity (guaranteed) ──
    bridge = get_session_bridge_messages(channel_id)
    unsummarized = get_unsummarized_messages(channel_id)
    continuity = _merge_dedup_sort(bridge, unsummarized)
    max_layer2 = int(remaining * LAYER2_BUDGET_PCT)
    continuity_block, layer2_tokens = _trim_to_budget(continuity, max_layer2)
    trimmed = len(continuity_block) < len(continuity)
    remaining -= layer2_tokens

    # ── Layer 3: Historical retrieval (fills remainder) ──
    seen_ids = {m["id"] for m in continuity_block}
    retrieved, ret_tokens, cluster_receipt, citation_map = _retrieve_segment_context(
        channel_id, conversation_msgs, remaining, exclude_ids=seen_ids)

    # ── Build final system message ──
    system_content = base_content
    if retrieved:
        cite_instr = (
            "CITATION INSTRUCTIONS: Messages are numbered [1], [2], etc. "
            "When your answer uses specific information from these messages, "
            'cite with [N] inline. Example: "Gorillas can lift 5-10x their '
            'weight [1]."\n\n') if citation_map else ""
        system_content += (
            f"\n\n--- PAST MESSAGES FROM THIS CHANNEL (retrieved by topic relevance) ---\n"
            f"The following are real messages previously sent in this channel, "
            f"retrieved because they are relevant to the current query. "
            f"They ARE part of this conversation's history.\n\n{cite_instr}{retrieved}")
    elif summary:
        from utils.summary_display import format_summary_for_context
        system_content += (
            f"\n\n--- CONVERSATION CONTEXT ---\nToday's date: {today}\n\n"
            f"The following is a summary of this channel's conversation "
            f"history.\n\n{format_summary_for_context(summary)}")
        logger.warning(f"Retrieval fully degraded ch:{channel_id}")

    logger.debug(f"Context block (first 2000):\n{system_content[:2000]}")
    if logger.isEnabledFor(10):
        try:
            with open('/tmp/last_system_prompt.txt', 'w') as _f:
                _f.write(system_content)
        except Exception:
            pass

    # ── Assemble turns ──
    system_tokens = estimate_tokens(system_content) + MSG_OVERHEAD
    conv_budget = budget - system_tokens - layer2_tokens
    layer2_ids = {m["id"] for m in continuity_block}
    layer2_turns = [_format_as_turn(m) for m in continuity_block]
    selected, used = [], 0
    for msg in reversed(conversation_msgs):
        if msg.get("_msg_id") in layer2_ids:
            continue
        if len(selected) >= MAX_RECENT_MESSAGES:
            break
        t = estimate_tokens(msg["content"]) + MSG_OVERHEAD
        if used + t > conv_budget:
            break
        selected.append(msg)
        used += t
    selected.reverse()

    dropped = len(conversation_msgs) - len(selected)
    if dropped > 0:
        logger.info(f"Token budget trim: dropped {dropped} msgs ch:{channel_id}")

    total_tokens = system_tokens + layer2_tokens + used
    if summary and cluster_receipt:
        receipt_data = {
            "query": cluster_receipt.get("query", ""),
            "query_embedding_path": cluster_receipt.get("embedding_path", "unknown"),
            "always_on": {
                "total_tokens": always_on_tokens + control_tokens,
                "overview_tokens": always_on_tokens,
                "control_file_tokens": control_tokens,
                "key_facts_count": len([f for f in summary.get("key_facts", [])
                                        if f.get("status") == "active"]),
                "decisions_count": len([d for d in summary.get("decisions", [])
                                        if d.get("status") == "active"]),
                "action_items_count": len([a for a in summary.get("action_items", [])
                                           if a.get("status") in ("open", "in_progress")]),
                "open_questions_count": len([q for q in summary.get("open_questions", [])
                                             if q.get("status") == "open"]),
            },
            "continuity": {
                "session_bridge_messages": len(bridge),
                "unsummarized_messages": len(unsummarized),
                "total_continuity_messages": len(continuity_block),
                "continuity_tokens": layer2_tokens,
                "trimmed": trimmed,
            },
            "retrieved_segments": cluster_receipt.get("retrieved_segments"),
            "score_gap_applied": cluster_receipt.get("score_gap_applied", False),
            "retrieved_clusters": cluster_receipt.get("retrieved_clusters", []),
            "clusters_below_threshold": cluster_receipt.get(
                "clusters_below_threshold", []),
            "fallback_used": cluster_receipt.get("fallback_used", False),
            "fallback_messages": cluster_receipt.get("fallback_messages", 0),
            "recent_messages": len(selected),
            "total_context_tokens": total_tokens,
            "budget_tokens": budget,
            "budget_used_pct": (
                round(total_tokens / budget * 100, 1) if budget else 0),
            "provider": provider.name,
            "model": getattr(provider, 'model', '?'),
        }

    final_messages = [{"role": "system", "content": system_content}] + layer2_turns + selected
    if logger.isEnabledFor(10):
        try:
            import json
            with open('/tmp/last_full_context.json', 'w') as _f:
                json.dump(final_messages, _f, indent=2, default=str)
        except Exception:
            pass
    return final_messages, receipt_data, citation_map
