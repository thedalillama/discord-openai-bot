#!/usr/bin/env python3
"""
Test the summarization pipeline outside of Discord.

Run from the bot directory:
    python test_pipeline.py

Shows:
1. Messages loaded from SQLite
2. Secretary output (raw natural language minutes)
3. Structurer output (JSON delta ops)

Does NOT save anything — read-only inspection.
"""
import json
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utils.message_store import init_database
init_database()


async def run_pipeline(channel_id):
    from utils.message_store import get_channel_messages
    from utils.summary_store import get_channel_summary
    from utils.summary_prompts import build_label_map
    from utils.summary_prompts_authoring import (
        build_secretary_prompt, build_structurer_prompt,
    )
    from utils.summary_schema import DELTA_SCHEMA
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER, SUMMARIZER_MODEL
    from utils.context_manager import estimate_tokens

    provider = get_provider(SUMMARIZER_PROVIDER)
    print(f"Provider: {SUMMARIZER_PROVIDER} / {SUMMARIZER_MODEL}")

    # Load messages from SQLite
    messages = get_channel_messages(channel_id)
    # Filter: no bot messages, no commands, no noise
    from utils.history.message_processing import (
        is_noise_message, is_settings_message,
    )
    filtered = [
        m for m in messages
        if not m.is_bot_author
        and not m.content.startswith("!")
        and not is_noise_message(m.content)
        and not is_settings_message(m.content)
    ]

    print(f"\n{'='*60}")
    print(f"MESSAGES: {len(messages)} total, {len(filtered)} after filtering")
    print(f"{'='*60}")
    for m in filtered[:5]:
        print(f"  {m.author_name}: {m.content[:80]}...")
    if len(filtered) > 5:
        print(f"  ... ({len(filtered) - 5} more)")

    # Build label map
    _, labeled_text = build_label_map(filtered)
    print(f"\nLabeled text: {estimate_tokens(labeled_text)} tokens")

    # Check for existing summary
    raw_json, _ = get_channel_summary(channel_id)
    if raw_json:
        current = json.loads(raw_json)
        print(f"\nExisting summary: {current.get('summary_token_count', 0)} tokens")
    else:
        current = None
        print("\nNo existing summary (cold start)")

    # --- Pass 1: Secretary ---
    print(f"\n{'='*60}")
    print("PASS 1: SECRETARY (natural language minutes)")
    print(f"{'='*60}")

    secretary_prompt = build_secretary_prompt("", labeled_text)
    print(f"\nSystem prompt: {estimate_tokens(secretary_prompt[0]['content'])} tokens")
    print(f"User prompt: {estimate_tokens(secretary_prompt[1]['content'])} tokens")

    print("\nCalling Gemini...")
    try:
        minutes_text = await provider.generate_ai_response(
            secretary_prompt, temperature=0,
        )
    except Exception as e:
        print(f"Secretary failed: {e}")
        return

    print(f"\nSecretary output ({estimate_tokens(minutes_text)} tokens):")
    print("-" * 40)
    print(minutes_text)
    print("-" * 40)

    # --- Pass 2: Structurer ---
    print(f"\n{'='*60}")
    print("PASS 2: STRUCTURER (JSON delta ops)")
    print(f"{'='*60}")

    structurer_prompt = build_structurer_prompt(minutes_text, current)
    print(f"\nSystem prompt: {estimate_tokens(structurer_prompt[0]['content'])} tokens")
    print(f"User prompt: {estimate_tokens(structurer_prompt[1]['content'])} tokens")

    print("\nCalling Gemini with structured output...")
    try:
        response_text = await provider.generate_ai_response(
            structurer_prompt, temperature=0,
            response_mime_type="application/json",
            response_json_schema=DELTA_SCHEMA,
        )
    except Exception as e:
        print(f"Structurer failed: {e}")
        return

    print(f"\nStructurer raw output ({estimate_tokens(response_text)} tokens):")
    print("-" * 40)

    try:
        delta = json.loads(response_text)
        print(json.dumps(delta, indent=2))

        ops = delta.get("ops", [])
        print(f"\n{len(ops)} ops generated:")
        by_type = {}
        for op in ops:
            t = op.get("op", "?")
            by_type[t] = by_type.get(t, 0) + 1
        for t, count in sorted(by_type.items()):
            print(f"  {t}: {count}")
    except json.JSONDecodeError:
        print(response_text)
        print("(Failed to parse as JSON)")

    print("-" * 40)
    print("\nDone. Nothing was saved.")


def main():
    channel_id = 1472003599985934560  # #openclaw
    if len(sys.argv) > 1:
        channel_id = int(sys.argv[1])
    print(f"Channel: {channel_id}")
    asyncio.run(run_pipeline(channel_id))


if __name__ == "__main__":
    main()
