# utils/summary_display.py
# Version 1.1.0
"""
Summary display formatting and pagination for Discord output.

CHANGES v1.1.0: ℹ️ prefix on all output for noise filtering
- MODIFIED: send_paginated() prepends ℹ️ to every Discord message

CREATED v1.0.0: Extracted from summary_commands.py v2.1.0
"""
from utils.logging_utils import get_logger

logger = get_logger('summary_display')

MAX_MSG = 1900
_PFX = "ℹ️ "


async def send_paginated(ctx, lines):
    """Send lines as one or more Discord messages, each prefixed with ℹ️."""
    buffer = ""
    for line in lines:
        entry = line + "\n"
        if len(buffer) + len(entry) + len(_PFX) > MAX_MSG:
            if buffer.strip():
                await ctx.send(f"{_PFX}{buffer.strip()}")
            buffer = entry
        else:
            buffer += entry
    if buffer.strip():
        await ctx.send(f"{_PFX}{buffer.strip()}")


def format_summary(summary, full=False):
    """Format structured summary JSON into display lines."""
    lines = []

    if summary.get("overview"):
        lines += ["**Overview**", summary["overview"], ""]

    topics = [t for t in summary.get("active_topics", [])
              if t.get("status") not in ("archived", "completed")]
    if topics:
        lines.append("**Active Topics**")
        for t in topics:
            summary_text = t.get("summary", "") or ""
            if summary_text:
                lines.append(f"• **{t['title']}** — {summary_text}")
            else:
                lines.append(f"• **{t['title']}**")
        lines.append("")

    decisions = [d for d in summary.get("decisions", [])
                 if d.get("status") == "active" and d.get("decision")]
    if decisions:
        lines.append("**Decisions**")
        for d in decisions:
            lines.append(f"• {d['decision']}")
        lines.append("")

    superseded = [d for d in summary.get("decisions", [])
                  if d.get("status") == "superseded" and d.get("decision")]
    if superseded:
        lines.append("**Superseded Decisions**")
        for d in superseded:
            lines.append(f"• ~~{d['decision']}~~")
        lines.append("")

    actions = [a for a in summary.get("action_items", [])
               if a.get("status") in ("open", "in_progress")]
    if actions:
        lines.append("**Open Action Items**")
        for a in actions:
            owner = a.get("owner", "unassigned")
            lines.append(f"• [ ] {a.get('task', '?')} — {owner}")
        lines.append("")

    completed = [a for a in summary.get("action_items", [])
                 if a.get("status") == "completed"]
    if completed:
        lines.append("**Completed Actions**")
        for a in completed:
            owner = a.get("owner", "unassigned")
            lines.append(f"• [x] {a.get('task', '?')} — {owner}")
        lines.append("")

    questions = [q for q in summary.get("open_questions", [])
                 if q.get("status") == "open"]
    if questions:
        lines.append("**Open Questions**")
        for q in questions:
            lines.append(f"• {q.get('question', '?')}")
        lines.append("")

    if full:
        facts = [f for f in summary.get("key_facts", [])
                 if f.get("status") == "active"]
        if facts:
            lines.append("**Key Facts**")
            for f in facts:
                lines.append(f"• {f.get('fact', '?')}")
            lines.append("")

        archived = [t for t in summary.get("active_topics", [])
                    if t.get("status") in ("archived", "completed")]
        if archived:
            lines.append("**Archived/Completed Topics**")
            for t in archived:
                lines.append(f"• {t['title']}")
            lines.append("")

        pinned = summary.get("pinned_memory", [])
        if pinned:
            lines.append("**Pinned Memory**")
            for p in pinned:
                lines.append(f"• {p.get('text', '?')}")
            lines.append("")

    tc = summary.get("summary_token_count", 0)
    meta = summary.get("meta", {})
    mr = meta.get("message_range", {})
    count = mr.get("count", 0)
    lines.append(f"*{count} messages summarized | {tc} tokens*")

    return lines
