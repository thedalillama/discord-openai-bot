#!/usr/bin/env python3
"""
Test script to inspect the summarization pipeline.

Run from the bot directory:
    python test_summary.py

Shows:
1. The Secretary's raw minutes output
2. The Structurer's JSON delta ops
3. The formatted context that gets injected into the system prompt
4. Interactive Q&A against the combined system prompt
"""
import json
import asyncio
import sys
import os

# Add bot directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
from dotenv import load_dotenv
load_dotenv()

from utils.message_store import init_database
init_database()

from utils.summary_store import get_channel_summary
from utils.summary_display import format_summary_for_context
from utils.history.prompts import get_system_prompt
from utils.context_manager import estimate_tokens


def show_stored_summary(channel_id):
    """Display the current stored summary."""
    raw, _ = get_channel_summary(channel_id)
    if not raw:
        print("No summary stored for this channel.")
        return None
    summary = json.loads(raw)

    print("=" * 60)
    print("STORED SUMMARY (JSON)")
    print("=" * 60)

    # Show each section
    print(f"\nOverview: {summary.get('overview', '(none)')}")

    print(f"\nDecisions ({len(summary.get('decisions', []))}):")
    for d in summary.get("decisions", []):
        print(f"  [{d.get('status')}] {d.get('id')}: {d.get('decision')}")

    print(f"\nKey Facts ({len(summary.get('key_facts', []))}):")
    for f in summary.get("key_facts", []):
        print(f"  [{f.get('status')}] {f.get('id')}: {f.get('fact')}")

    print(f"\nAction Items ({len(summary.get('action_items', []))}):")
    for a in summary.get("action_items", []):
        print(f"  [{a.get('status')}] {a.get('id')}: {a.get('task')} "
              f"(owner: {a.get('owner')})")

    print(f"\nOpen Questions ({len(summary.get('open_questions', []))}):")
    for q in summary.get("open_questions", []):
        print(f"  [{q.get('status')}] {q.get('id')}: {q.get('question')}")

    print(f"\nActive Topics ({len(summary.get('active_topics', []))}):")
    for t in summary.get("active_topics", []):
        print(f"  [{t.get('status')}] {t.get('id')}: {t.get('title')}")

    print(f"\nParticipants ({len(summary.get('participants', []))}):")
    for p in summary.get("participants", []):
        print(f"  {p.get('display_name', p.get('id'))}")

    tc = summary.get("summary_token_count", 0)
    mr = summary.get("meta", {}).get("message_range", {})
    print(f"\nTokens: {tc} | Messages: {mr.get('count', 0)}")

    return summary


def show_context_injection(channel_id, summary):
    """Show what gets injected into the system prompt."""
    print("\n" + "=" * 60)
    print("CONTEXT INJECTION (what the bot sees)")
    print("=" * 60)

    system_prompt = get_system_prompt(channel_id)
    summary_text = format_summary_for_context(summary)

    print(f"\nSystem prompt ({estimate_tokens(system_prompt)} tokens):")
    print(f"  {system_prompt[:200]}...")

    print(f"\nSummary text ({estimate_tokens(summary_text)} tokens):")
    print(summary_text)

    combined = (
        f"{system_prompt}\n\n"
        f"--- CONVERSATION CONTEXT ---\n"
        f"The following is a summary of this channel's conversation "
        f"history. Use it to inform your responses.\n\n"
        f"{summary_text}"
    )
    print(f"\nCombined system prompt: {estimate_tokens(combined)} tokens")
    return combined


def show_topic_statuses(summary):
    """Show topic status breakdown — helps debug display issues."""
    topics = summary.get("active_topics", [])
    if not topics:
        print("\nNo topics.")
        return

    print("\n" + "=" * 60)
    print(f"TOPIC STATUS BREAKDOWN ({len(topics)} total)")
    print("=" * 60)

    by_status = {}
    for t in topics:
        s = t.get("status", "unknown")
        by_status.setdefault(s, []).append(t.get("title", "?"))

    for status, titles in sorted(by_status.items()):
        print(f"\n  {status} ({len(titles)}):")
        for title in titles:
            print(f"    - {title}")


async def interactive_qa(combined_prompt, channel_id):
    """Interactive Q&A loop using the combined system prompt."""
    print("\n" + "=" * 60)
    print("INTERACTIVE Q&A (type 'quit' to exit)")
    print("=" * 60)

    from ai_providers import get_provider
    from utils.history import get_ai_provider
    from config import AI_PROVIDER

    provider_name = get_ai_provider(channel_id) or AI_PROVIDER
    provider = get_provider(provider_name)
    print(f"Using provider: {provider_name}")

    history = []

    while True:
        question = input("\nYou: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break

        history.append({"role": "user",
                        "content": f"absolutebeginner: {question}"})

        messages = [
            {"role": "system", "content": combined_prompt}
        ] + history

        try:
            response = await provider.generate_ai_response(messages)
            print(f"\nBot: {response}")
            history.append({"role": "assistant", "content": response})
        except Exception as e:
            print(f"\nError: {e}")


def main():
    # Default to #openclaw — change as needed
    CHANNEL_ID = 1472003599985934560

    if len(sys.argv) > 1:
        CHANNEL_ID = int(sys.argv[1])

    print(f"Channel ID: {CHANNEL_ID}")

    summary = show_stored_summary(CHANNEL_ID)
    if not summary:
        return

    show_topic_statuses(summary)
    combined = show_context_injection(CHANNEL_ID, summary)

    # Interactive mode
    try:
        asyncio.run(interactive_qa(combined, CHANNEL_ID))
    except (KeyboardInterrupt, EOFError):
        print("\nDone.")


if __name__ == "__main__":
    main()
