# commands/explain_commands.py
# Version 1.3.0
"""
!explain command — show context receipt for the most recent bot response.

CHANGES v1.3.0: Continuity section display (SOW v7.0.0 M1)
- MODIFIED: format_receipt() — shows Layer 2 continuity block stats
  (session bridge msgs, unsummarized msgs, tokens used, trimmed flag)

CHANGES v1.2.0: Segment-based receipt display (SOW v6.1.0)
- MODIFIED: format_receipt() handles retrieved_segments (v6.1.0+) and
  retrieved_clusters (rollback/pre-v6.1 receipts) — checks which key is present
- MODIFIED: format_injected_messages() uses get_segment_with_messages() for
  segment receipts; falls back to get_cluster_messages() for cluster receipts

CHANGES v1.1.0: Add !explain detail mode (SOW v5.7.1)
- ADDED: format_injected_messages() — fetch and format cluster messages on demand
- MODIFIED: explain_cmd() accepts variadic args: !explain | !explain detail |
  !explain <id> | !explain detail <id>

CREATED v1.0.0: Context receipt display (SOW v5.7.0)

All output prefixed with ℹ️. Uses send_paginated() for long receipts.
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('commands.explain')

_I = "ℹ️ "
_MSG_TRUNCATE = 150
_CLUSTER_SHOW = 5  # show first N + last N when list exceeds 2*N messages


def format_receipt(receipt):
    """Format a receipt dict into Discord display lines."""
    lines = []
    query = receipt.get("query", "")
    lines.append(
        f'**Context Receipt** (response to: "{query[:80]}")' if query
        else "**Context Receipt**")

    path = receipt.get("query_embedding_path", "unknown")
    lines.append(f"\n**Query Embedding**: {path}")

    cont = receipt.get("continuity")
    if cont:
        trimmed_str = " (trimmed)" if cont.get("trimmed") else ""
        lines.append(
            f"\n**Continuity (Layer 2)** ({cont.get('continuity_tokens', 0):,} tokens"
            f"{trimmed_str}):")
        lines.append(
            f"  Session bridge: {cont.get('session_bridge_messages', 0)} msgs")
        lines.append(
            f"  Unsummarized: {cont.get('unsummarized_messages', 0)} msgs")
        lines.append(
            f"  Total injected: {cont.get('total_continuity_messages', 0)} msgs")

    ao = receipt.get("always_on", {})
    lines.append(f"\n**Always-On Context** ({ao.get('total_tokens', 0):,} tokens):")
    lines.append(f"  Overview: {'✓' if ao.get('overview_tokens', 0) > 0 else '✗'}")
    lines.append(f"  Key facts: {ao.get('key_facts_count', 0)} items")
    lines.append(f"  Decisions: {ao.get('decisions_count', 0)} items")
    lines.append(f"  Action items: {ao.get('action_items_count', 0)} items")

    segs = receipt.get("retrieved_segments")
    if segs is not None:
        # Segment-based path (v6.1.0+)
        total_ret = sum(s.get("tokens", 0) for s in segs)
        gap = receipt.get("score_gap_applied", False)
        lines.append(
            f"\n**Retrieved Segments** ({total_ret:,} tokens"
            f"{', gap-cut' if gap else ''}):")
        for i, s in enumerate(segs, 1):
            synth_only = " [synthesis-only]" if s.get("synthesis_only") else ""
            lines.append(
                f"  {i}. {s.get('topic_label', '?')[:50]} — "
                f"score {s.get('score', 0):.3f}, "
                f"{s.get('message_count', 0)} msgs "
                f"({s.get('tokens', 0):,} tok){synth_only}")
        if not segs:
            lines.append(
                "  (none — fallback used)" if receipt.get("fallback_used")
                else "  (none)")
    else:
        # Cluster-based path (rollback or pre-v6.1 receipts)
        clusters = receipt.get("retrieved_clusters", [])
        total_ret = sum(c.get("tokens", 0) for c in clusters)
        lines.append(f"\n**Retrieved Clusters** ({total_ret:,} tokens):")
        for i, c in enumerate(clusters, 1):
            lines.append(
                f"  {i}. {c.get('label', '?')} — score {c.get('score', 0):.3f}, "
                f"{c.get('messages_injected', 0)} msgs ({c.get('tokens', 0):,} tok)")
        if not clusters:
            lines.append(
                "  (none — fallback used)" if receipt.get("fallback_used")
                else "  (none)")
        below = receipt.get("clusters_below_threshold", [])
        if below:
            lines.append("\n**Below Threshold** (filtered out):")
            for c in below[:5]:
                lines.append(f"  {c.get('label', '?')} — score {c.get('score', 0):.3f}")

    if receipt.get("fallback_used"):
        lines.append(
            f"\n**Fallback**: {receipt.get('fallback_messages', 0)} "
            f"msgs retrieved by direct similarity")

    lines.append(f"\n**Recent Messages**: {receipt.get('recent_messages', 0)}")
    total = receipt.get("total_context_tokens", 0)
    budget = receipt.get("budget_tokens", 0)
    pct = receipt.get("budget_used_pct", 0)
    lines.append(f"**Budget**: {total:,} / {budget:,} tokens ({pct:.1f}%)")
    lines.append(
        f"**Provider**: {receipt.get('provider', '?')} / {receipt.get('model', '?')}")
    return lines


def format_injected_messages(receipt):
    """Fetch and format injected segment/cluster messages for detail view."""
    from utils.cluster_retrieval import get_cluster_messages, get_segment_with_messages

    segs = receipt.get("retrieved_segments")
    if segs is not None:
        if not segs:
            return []
        lines = ["\n--- Injected Segments ---"]
        for s in segs:
            seg_id = s.get("segment_id")
            label = s.get("topic_label", "?")
            lines.append(f"\n**[Topic: {label}]**")
            if s.get("synthesis_only"):
                lines.append("  [synthesis-only — token budget exhausted]")
                continue
            try:
                seg_data = get_segment_with_messages(seg_id)
                msgs = seg_data["messages"] if seg_data else []
                if not msgs:
                    lines.append("  (no messages found)")
                    continue
                threshold = _CLUSTER_SHOW * 2
                display = (msgs[:_CLUSTER_SHOW] + [None] + msgs[-_CLUSTER_SHOW:]
                           if len(msgs) > threshold else msgs)
                omitted = max(0, len(msgs) - threshold)
                for item in display:
                    if item is None:
                        lines.append(f"  ... and {omitted} more messages ...")
                        continue
                    _, author, content, created_at = item
                    text = (content or "")[:_MSG_TRUNCATE]
                    if len(content or "") > _MSG_TRUNCATE:
                        text += "…"
                    lines.append(
                        f"  [{(created_at or '')[:10]}] **{author}**: {text}")
            except Exception as e:
                logger.warning(f"Failed to fetch segment {seg_id}: {e}")
                lines.append("  (error fetching messages)")
        return lines

    # Cluster-based path (rollback / pre-v6.1 receipts)
    clusters = receipt.get("retrieved_clusters", [])
    if not clusters:
        return []
    lines = ["\n--- Injected Messages ---"]
    for c in clusters:
        cluster_id = c.get("cluster_id")
        label = c.get("label", "?")
        lines.append(f"\n**[Topic: {label}]**")
        try:
            msgs = get_cluster_messages(cluster_id)
            if not msgs:
                lines.append("  (no messages found)")
                continue
            threshold = _CLUSTER_SHOW * 2
            display = (msgs[:_CLUSTER_SHOW] + [None] + msgs[-_CLUSTER_SHOW:]
                       if len(msgs) > threshold else msgs)
            omitted = max(0, len(msgs) - threshold)
            for item in display:
                if item is None:
                    lines.append(f"  ... and {omitted} more messages ...")
                    continue
                _, author, content, created_at = item
                text = (content or "")[:_MSG_TRUNCATE]
                if len(content or "") > _MSG_TRUNCATE:
                    text += "…"
                lines.append(f"  [{(created_at or '')[:10]}] **{author}**: {text}")
        except Exception as e:
            logger.warning(f"Failed to fetch cluster {cluster_id}: {e}")
            lines.append("  (error fetching messages)")
    return lines


def register_explain_commands(bot):

    @bot.command(name='explain')
    async def explain_cmd(ctx, *args):
        """Show context receipt. Usage: !explain | !explain detail |
        !explain <id> | !explain detail <id>"""
        channel_id = ctx.channel.id

        mode = None
        message_id = None
        try:
            if args and args[0].lower() == 'detail':
                mode = 'detail'
                if len(args) > 1:
                    message_id = int(args[1])
            elif args:
                message_id = int(args[0])
        except ValueError:
            await ctx.send(
                f"{_I}Usage: `!explain` | `!explain detail` | "
                f"`!explain <id>` | `!explain detail <id>`")
            return

        try:
            from utils.receipt_store import get_latest_receipt, get_receipt_by_response

            if message_id is not None:
                receipt = await asyncio.to_thread(
                    get_receipt_by_response, message_id)
                if receipt is None:
                    await ctx.send(f"{_I}No receipt found for that message.")
                    return
            else:
                _, receipt = await asyncio.to_thread(get_latest_receipt, channel_id)
                if receipt is None:
                    await ctx.send(
                        f"{_I}No context receipts found. "
                        f"Receipts are stored starting from this version.")
                    return

            lines = format_receipt(receipt)

            if mode == 'detail':
                detail_lines = await asyncio.to_thread(
                    format_injected_messages, receipt)
                lines.extend(detail_lines)

            from utils.summary_display import send_paginated
            await send_paginated(ctx, lines)

        except Exception as e:
            await ctx.send(f"{_I}Error retrieving receipt: {e}")
            logger.error(f"explain_cmd error ch:{channel_id}: {e}")
