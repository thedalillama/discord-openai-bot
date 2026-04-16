# utils/summary_display.py
# Version 1.3.3
"""
Summary display formatting and pagination for Discord output.

CHANGES v1.3.3: Read pipeline label from summary meta instead of hardcoding cluster-v5
CHANGES v1.3.2: Fix footer for cluster-v5 summaries (cluster_count key)
CHANGES v1.3.1: "Key facts:" → "Key facts established in this conversation:"
CHANGES v1.3.0: format_always_on_context() for semantic retrieval (SOW v4.0.0)
CHANGES v1.2.1: Key Facts in default !summary view
CHANGES v1.2.0: format_summary_for_context() for system prompt injection
CHANGES v1.1.0: ℹ️ prefix on all output for noise filtering
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


def format_always_on_context(summary):
    """Slim always-on context: overview, key facts, open actions, open questions.
    Topics excluded — retrieved semantically per query by context_manager."""
    parts = []
    if summary.get("overview"):
        parts.append(f"Overview: {summary['overview']}")
    facts = [f for f in summary.get("key_facts", [])
             if f.get("status") == "active" and f.get("fact")]
    if facts:
        parts.append("Key facts established in this conversation:\n" + "\n".join(f"- {f['fact']}" for f in facts))
    actions = [a for a in summary.get("action_items", [])
               if a.get("status") in ("open", "in_progress")]
    if actions:
        parts.append("Open action items:\n" + "\n".join(
            f"- {a.get('task','?')} (owner: {a.get('owner','unassigned')})"
            for a in actions))
    questions = [q for q in summary.get("open_questions", [])
                 if q.get("status") == "open"]
    if questions:
        parts.append("Open questions:\n" + "\n".join(
            f"- {q.get('question','?')}" for q in questions))
    return "\n\n".join(parts)


def format_summary_for_context(summary):
    """Format the full summary as plain text for system prompt injection.

    Returns a clean text block with all sections. Returns empty string
    if summary has no meaningful content."""
    parts = []

    overview = summary.get("overview", "")
    if overview:
        parts.append(f"Overview: {overview}")

    decisions = [d for d in summary.get("decisions", [])
                 if d.get("status") == "active" and d.get("decision")]
    if decisions:
        items = "; ".join(d["decision"] for d in decisions)
        parts.append(f"Active decisions: {items}")

    superseded = [d for d in summary.get("decisions", [])
                  if d.get("status") == "superseded" and d.get("decision")]
    if superseded:
        items = "; ".join(d["decision"] for d in superseded)
        parts.append(f"Superseded decisions: {items}")

    topics = [t for t in summary.get("active_topics", [])
              if t.get("status") not in ("archived", "completed")]
    if topics:
        topic_lines = []
        for t in topics:
            s = t.get("summary", "")
            if s:
                topic_lines.append(f"- {t['title']}: {s}")
            else:
                topic_lines.append(f"- {t['title']}")
        parts.append("Active topics:\n" + "\n".join(topic_lines))

    facts = [f for f in summary.get("key_facts", [])
             if f.get("status") == "active" and f.get("fact")]
    if facts:
        items = "\n".join(f"- {f['fact']}" for f in facts)
        parts.append(f"Key facts:\n{items}")

    actions = [a for a in summary.get("action_items", [])
               if a.get("status") in ("open", "in_progress")]
    if actions:
        items = "\n".join(
            f"- {a.get('task', '?')} (owner: {a.get('owner', '?')})"
            for a in actions)
        parts.append(f"Open action items:\n{items}")

    completed = [a for a in summary.get("action_items", [])
                 if a.get("status") == "completed"]
    if completed:
        items = "; ".join(a.get("task", "?") for a in completed)
        parts.append(f"Completed actions: {items}")

    questions = [q for q in summary.get("open_questions", [])
                 if q.get("status") == "open"]
    if questions:
        items = "\n".join(f"- {q.get('question', '?')}" for q in questions)
        parts.append(f"Open questions:\n{items}")

    participants = summary.get("participants", [])
    if participants:
        names = ", ".join(p.get("display_name", p["id"]) for p in participants)
        parts.append(f"Participants: {names}")

    archived = [t for t in summary.get("active_topics", [])
                if t.get("status") in ("archived", "completed")]
    if archived:
        items = "; ".join(t["title"] for t in archived)
        parts.append(f"Archived topics: {items}")

    pinned = summary.get("pinned_memory", [])
    if pinned:
        items = "\n".join(f"- {p.get('text', '?')}" for p in pinned)
        parts.append(f"Pinned memory:\n{items}")

    if not parts:
        return ""

    return "\n\n".join(parts)


def format_summary(summary, full=False):
    """Format structured summary JSON into display lines for Discord."""
    lines = []

    if summary.get("overview"):
        lines += ["**Overview**", summary["overview"], ""]

    topics = [t for t in summary.get("active_topics", [])
              if t.get("status") not in ("archived", "completed")]
    if topics:
        lines.append("**Active Topics**")
        for t in topics:
            s = t.get("summary", "") or ""
            if s:
                lines.append(f"• **{t['title']}** — {s}")
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

    facts = [f for f in summary.get("key_facts", [])
             if f.get("status") == "active"]
    if facts:
        lines.append("**Key Facts**")
        for f in facts:
            lines.append(f"• {f.get('fact', '?')}")
        lines.append("")

    if full:
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

    if "cluster_count" in summary:
        cc = summary["cluster_count"]
        nc = summary.get("noise_message_count", 0)
        pipeline_label = summary.get("meta", {}).get("pipeline", "cluster-v5")
        lines.append(f"*{cc} clusters ({nc} noise) | {pipeline_label}*")
    else:
        tc = summary.get("summary_token_count", 0)
        meta = summary.get("meta", {})
        mr = meta.get("message_range", {})
        count = mr.get("count", 0)
        lines.append(f"*{count} messages summarized | {tc} tokens*")

    return lines
