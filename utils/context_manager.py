# utils/context_manager.py
# Version 3.2.0
"""
Token-budget-aware context management and usage tracking.

CHANGES v3.2.0: Conversational classifier bypasses Layer 1 summary + Layer 3
  retrieval; build_system_prompt() extracted to context_helpers; Receipt dataclass.
CHANGES v3.1.4-3.1.0: Author-filter header; plan_and_retrieve() entry.
CHANGES v3.0.0: Three-layer context assembly (SOW v7.0.0 M1)
CREATED v1.0.0: Initial implementation
"""
from collections import defaultdict
from datetime import date
from config import CONTEXT_BUDGET_PERCENT, MAX_RECENT_MESSAGES, LAYER2_BUDGET_PCT
from utils.history.message_processing import prepare_messages_for_api
from utils.context_helpers import (
    _load_summary, read_control_file, _merge_dedup_sort,
    _trim_to_budget, _format_as_turn, build_system_prompt)
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
    """Build token-budget-aware message list for an AI provider call.

    Layer 1 (guaranteed): system prompt + control file + always-on summary.
    Layer 2 (guaranteed): session bridge + unsummarized messages.
    Layer 3 (fills remainder): historical RRF retrieval.
    Conversational queries bypass Layer 1 summary and Layer 3 entirely.

    Returns: (messages, receipt_data, citation_map)
    """
    from utils.query_planner import plan_and_retrieve, get_channel_members
    from utils.query_type import classify_query, QueryType
    from utils.receipt import Receipt, PlannerInfo, AlwaysOnInfo, ContinuityInfo
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

    # Classify query type — conversational bypasses summary + retrieval
    query_text = next(
        (m["content"].strip() for m in reversed(conversation_msgs)
         if m.get("role") == "user" and m.get("content", "").strip()), "")
    members = get_channel_members(channel_id) if query_text else []
    query_type = classify_query(query_text, members) if query_text else QueryType.INFORMATION
    is_conv = (query_type == QueryType.CONVERSATIONAL)

    # ── Layer 1: System + control file + always-on summary ──
    always_on, always_on_tokens = "", 0
    if summary and not is_conv:
        from utils.summary_display import format_always_on_context
        always_on = format_always_on_context(summary)
        always_on_tokens = estimate_tokens(always_on)

    control = read_control_file()
    control_tokens = estimate_tokens(control)
    today = date.today().isoformat()

    # Conservative budget estimate includes always-on even for author-filter queries
    base_content = system_msg["content"]
    if control:
        base_content += f"\n\n{control}"
    if always_on:
        base_content += (f"\n\n--- CONVERSATION CONTEXT ---\n"
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

    # ── Layer 3: Historical retrieval (skipped for conversational queries) ──
    seen_ids = {m["id"] for m in continuity_block}
    cluster_receipt, citation_map, retrieved = {}, {}, ""
    if not is_conv:
        retrieved, _, cluster_receipt, citation_map = plan_and_retrieve(
            channel_id, conversation_msgs, remaining, exclude_ids=seen_ids)

    # ── Build system message ──
    af_list = ((cluster_receipt.get("query_planner") or {}).get("author_filter") or [])
    af_query = cluster_receipt.get("query", "").strip() if af_list else ""
    system_content = build_system_prompt(
        system_msg["content"], control, always_on,
        retrieved, af_list, af_query,
        citation_map, summary, today, channel_id, query_type)

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

    if len(conversation_msgs) > len(selected):
        logger.info(f"Token budget trim: dropped {len(conversation_msgs)-len(selected)} msgs ch:{channel_id}")

    total_tokens = system_tokens + layer2_tokens + used

    # ── Build receipt ──
    receipt_data = None
    if summary or is_conv:
        qp = cluster_receipt.get("query_planner")
        tf = (qp.get("time_filter") or {}) if qp else {}

        def _count(lst, key, vals):
            return len([x for x in (summary or {}).get(lst, []) if x.get(key) in vals])

        receipt = Receipt(
            query=cluster_receipt.get("query", query_text),
            query_type=query_type.value,
            query_embedding_path=cluster_receipt.get("embedding_path", "unknown"),
            planner=PlannerInfo(
                used=bool(qp),
                mode=(qp.get("mode") if qp else None),
                author_filter=((qp.get("author_filter") or []) if qp else []),
                time_filter_after=tf.get("after"),
                time_filter_before=tf.get("before"),
                candidates=(qp.get("candidates") if qp else None),
                planner_latency_ms=(qp.get("planner_latency_ms", 0) if qp else 0),
                note=(qp.get("note") if qp else None),
                content_query=(qp.get("content_query") if qp else None),
            ),
            always_on=AlwaysOnInfo(
                total_tokens=always_on_tokens + control_tokens,
                overview_tokens=always_on_tokens,
                control_file_tokens=control_tokens,
                key_facts_count=_count("key_facts", "status", {"active"}),
                decisions_count=_count("decisions", "status", {"active"}),
                action_items_count=_count("action_items", "status", {"open", "in_progress"}),
                open_questions_count=_count("open_questions", "status", {"open"}),
            ),
            continuity=ContinuityInfo(
                session_bridge_messages=len(bridge),
                unsummarized_messages=len(unsummarized),
                total_continuity_messages=len(continuity_block),
                continuity_tokens=layer2_tokens,
                trimmed=trimmed,
            ),
            retrieved_segments=cluster_receipt.get("retrieved_segments"),
            score_gap_applied=cluster_receipt.get("score_gap_applied", False),
            retrieved_clusters=cluster_receipt.get("retrieved_clusters", []),
            clusters_below_threshold=cluster_receipt.get("clusters_below_threshold", []),
            fallback_used=cluster_receipt.get("fallback_used", False),
            fallback_messages=cluster_receipt.get("fallback_messages", 0),
            recent_messages=len(selected),
            total_context_tokens=total_tokens,
            budget_tokens=budget,
            budget_used_pct=round(total_tokens / budget * 100, 1) if budget else 0,
            provider=provider.name,
            model=getattr(provider, 'model', '?'),
        )
        receipt_data = receipt.to_dict()

    final_messages = ([{"role": "system", "content": system_content}]
                      + layer2_turns + selected)
    try:
        import json
        json.dump(final_messages, open('/tmp/last_full_context.json', 'w'),
                  indent=2, default=str)
    except Exception:
        pass
    return final_messages, receipt_data, citation_map
