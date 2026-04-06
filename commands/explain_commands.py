# commands/explain_commands.py
# Version 1.1.0
"""
!explain command — show context receipt for the most recent bot response.

CHANGES v1.1.0: Add !explain detail mode (SOW v5.7.1)
- ADDED: format_injected_messages() — fetch and format cluster messages on demand
- MODIFIED: explain_cmd() accepts variadic args instead of typed int:
    !explain              — summary receipt (unchanged)
    !explain detail       — receipt + injected messages per cluster
    !explain <id>         — receipt for specific response message ID
    !explain detail <id>  — detail for specific response message ID
- Messages truncated to 150 chars; clusters > 10 msgs show first 5 + last 5

CREATED v1.0.0: Context receipt display (SOW v5.7.0)
- !explain         — receipt for the most recent bot response in this channel
- !explain <id>    — receipt for a specific response message ID

All output prefixed with ℹ️. Uses send_paginated() for long receipts.
"""
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('commands.explain')

_I = "ℹ️ "
_MSG_TRUNCATE = 150
_CLUSTER_SHOW = 5  # show first N + last N when cluster exceeds 2*N messages


def format_receipt(receipt):
    """Format a receipt dict into Discord display lines."""
    lines = []
    query = receipt.get("query", "")
    if query:
        lines.append(f'**Context Receipt** (response to: "{query[:80]}")')
    else:
        lines.append("**Context Receipt**")

    path = receipt.get("query_embedding_path", "unknown")
    lines.append(f"\n**Query Embedding**: {path}")

    ao = receipt.get("always_on", {})
    lines.append(f"\n**Always-On Context** ({ao.get('total_tokens', 0):,} tokens):")
    lines.append(f"  Overview: {'✓' if ao.get('overview_tokens', 0) > 0 else '✗'}")
    lines.append(f"  Key facts: {ao.get('key_facts_count', 0)} items")
    lines.append(f"  Decisions: {ao.get('decisions_count', 0)} items")
    lines.append(f"  Action items: {ao.get('action_items_count', 0)} items")

    clusters = receipt.get("retrieved_clusters", [])
    total_ret = sum(c.get("tokens", 0) for c in clusters)
    lines.append(f"\n**Retrieved Clusters** ({total_ret:,} tokens):")
    for i, c in enumerate(clusters, 1):
        lines.append(
            f"  {i}. {c.get('label','?')} — score {c.get('score',0):.3f}, "
            f"{c.get('messages_injected',0)} msgs ({c.get('tokens',0):,} tok)")
    if not clusters:
        if receipt.get("fallback_used"):
            lines.append("  (none — fallback used)")
        else:
            lines.append("  (none)")

    below = receipt.get("clusters_below_threshold", [])
    if below:
        lines.append("\n**Below Threshold** (filtered out):")
        for c in below[:5]:
            lines.append(f"  {c.get('label','?')} — score {c.get('score',0):.3f}")

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
        f"**Provider**: {receipt.get('provider','?')} / {receipt.get('model','?')}")

    return lines


def format_injected_messages(receipt):
    """Fetch and format injected cluster messages for detail view.

    Fetches messages live from the DB using cluster_ids stored in the receipt.
    Truncates content to _MSG_TRUNCATE chars. Clusters with > 2*_CLUSTER_SHOW
    messages show first + last N with a gap line.
    Returns list of lines; fails gracefully per cluster.
    """
    from utils.cluster_retrieval import get_cluster_messages

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
            if len(msgs) > threshold:
                omitted = len(msgs) - threshold
                display = msgs[:_CLUSTER_SHOW] + [None] + msgs[-_CLUSTER_SHOW:]
            else:
                omitted = 0
                display = msgs

            for item in display:
                if item is None:
                    lines.append(f"  ... and {omitted} more messages ...")
                    continue
                _, author, content, created_at = item
                date = (created_at or "")[:10]
                text = (content or "")
                if len(text) > _MSG_TRUNCATE:
                    text = text[:_MSG_TRUNCATE] + "…"
                lines.append(f"  [{date}] **{author}**: {text}")
        except Exception as e:
            logger.warning(f"Failed to fetch messages for cluster {cluster_id}: {e}")
            lines.append(f"  (error fetching messages)")

    return lines


def register_explain_commands(bot):

    @bot.command(name='explain')
    async def explain_cmd(ctx, *args):
        """Show context receipt. Usage: !explain | !explain detail |
        !explain <id> | !explain detail <id>"""
        channel_id = ctx.channel.id

        # Parse args — valid forms:
        # ()                  → summary, latest
        # ('detail',)         → detail, latest
        # ('<id>',)           → summary, specific id
        # ('detail', '<id>')  → detail, specific id
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
