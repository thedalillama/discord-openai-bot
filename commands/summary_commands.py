# commands/summary_commands.py
# Version 1.0.0
"""
!summarize and !summary commands for channel summary management.

CREATED v1.0.0: Structured summary generation (SOW v3.2.0)
- ADDED: !summarize — run summarization for a channel (admin only)
- ADDED: !summary  — display current summary (all users)

Usage:
  !summarize    Run summarization for this channel (admin only)
  !summary      Show current channel summary (all users)
"""
import json
from utils.logging_utils import get_logger

logger = get_logger('commands.summary')


def register_summary_commands(bot):
    """Register !summarize and !summary commands with the bot."""

    @bot.command(name='summarize')
    async def summarize_cmd(ctx):
        """
        Run summarization for this channel.

        Usage: !summarize  (admin only)
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You need administrator permissions to run summarization.")
            logger.warning(
                f"Unauthorized !summarize by {ctx.author.display_name} in #{channel_name}"
            )
            return

        async with ctx.typing():
            try:
                from utils.summarizer import summarize_channel
                result = await summarize_channel(channel_id)

                if result.get("error"):
                    await ctx.send(f"Summarization failed: {result['error']}")
                    logger.error(f"!summarize failed for #{channel_name}: {result['error']}")
                    return

                msgs = result["messages_processed"]
                if msgs == 0:
                    await ctx.send(f"No new messages to summarize for #{channel_name}.")
                    return

                tokens = result["token_count"]
                v = result["verification"]
                mismatches = v.get("mismatches", 0)
                src_failed = v.get("source_checks_failed", 0)

                lines = [
                    f"**Summary updated for #{channel_name}**",
                    f"Messages processed: {msgs}",
                    f"Summary token count: {tokens}",
                ]
                if mismatches:
                    lines.append(f"⚠️ Hash mismatches corrected: {mismatches}")
                if src_failed:
                    lines.append(f"⚠️ Source verification failures: {src_failed}")
                if not mismatches and not src_failed:
                    lines.append("✅ Verification passed")

                await ctx.send("\n".join(lines))
                logger.info(
                    f"!summarize complete for #{channel_name}: "
                    f"{msgs} messages, {tokens} tokens"
                )

            except Exception as e:
                logger.error(f"Error in !summarize for #{channel_name}: {e}")
                await ctx.send(f"Error running summarization: {e}")

    @bot.command(name='summary')
    async def summary_cmd(ctx):
        """
        Show the current channel summary.

        Usage: !summary  (all users)
        """
        channel_id = ctx.channel.id
        channel_name = ctx.channel.name

        try:
            from utils.summary_store import get_channel_summary
            summary_json, _ = get_channel_summary(channel_id)

            if not summary_json:
                await ctx.send(
                    f"No summary available for #{channel_name}. "
                    f"An admin can run `!summarize` to generate one."
                )
                return

            summary = json.loads(summary_json)
            lines = [f"**Summary for #{channel_name}**", ""]

            if summary.get("overview"):
                lines += ["**Overview**", summary["overview"], ""]

            topics = [t for t in summary.get("active_topics", [])
                      if t.get("status") not in ("archived", "completed")]
            if topics:
                lines.append("**Active Topics**")
                for t in topics[:5]:
                    lines.append(f"• **{t['title']}** — {t.get('summary', '')[:80]}")
                lines.append("")

            decisions = [d for d in summary.get("decisions", [])
                         if d.get("status") == "active"]
            if decisions:
                lines.append("**Recent Decisions**")
                for d in decisions[:3]:
                    lines.append(f"• {d['decision'][:100]}")
                lines.append("")

            actions = [a for a in summary.get("action_items", [])
                       if a.get("status") in ("open", "in_progress")]
            if actions:
                lines.append("**Open Action Items**")
                for a in actions[:3]:
                    owner = a.get("owner", "unassigned")
                    lines.append(f"• {a['task'][:80]} ({owner})")
                lines.append("")

            questions = [q for q in summary.get("open_questions", [])
                         if q.get("status") == "open"]
            if questions:
                lines.append("**Open Questions**")
                for q in questions[:3]:
                    lines.append(f"• {q['question'][:80]}")

            message = "\n".join(lines).strip()
            if len(message) > 1900:
                message = message[:1897] + "..."

            await ctx.send(message)
            logger.debug(f"!summary displayed for #{channel_name}")

        except Exception as e:
            logger.error(f"Error in !summary for #{channel_name}: {e}")
            await ctx.send(f"Error retrieving summary: {e}")
