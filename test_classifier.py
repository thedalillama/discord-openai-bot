#!/usr/bin/env python3
"""
Test GPT-5.4 nano as a classification pass on summary items.

Run from the bot directory:
    python test_classifier.py

Loads the current summary, sends each item to nano for classification,
and reports what should be kept, dropped, or reclassified.
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

CLASSIFIER_PROMPT = """\
You are a summary quality classifier. For each item below, decide:
- KEEP: correctly classified, worth retaining
- DROP: not worth storing (transient queries, bot behavior, greetings)
- RECLASSIFY: wrong category — specify the correct one

Categories and their definitions:
- DECISION: A choice agreed upon by participants ("Let's use Redis")
- KEY_FACT: Durable personal detail or project info ("User is 65 years old")
- ACTION_ITEM: A task someone committed to do
- OPEN_QUESTION: An unresolved question affecting plans
- ACTIVE_TOPIC: An ongoing discussion worth tracking
- ARCHIVED_TOPIC: A resolved discussion kept for reference (only keep \
category-level entries, not individual bot responses)

Rules:
- Scientific facts are NOT decisions (physics, biology = DROP or ACTIVE_TOPIC)
- Bot behavior descriptions are DROP ("bot refused adult jokes")
- Individual bot responses are DROP ("bot provided gold prices")
- Category-level archives are KEEP ("Financial market queries")
- Personal details shared intentionally are KEY_FACT

Respond with ONLY a JSON array. Each element:
{"id": "item-id", "current": "current_category", "verdict": "KEEP|DROP|RECLASSIFY", "reclassify_to": "new_category or null", "reason": "brief reason"}
"""


async def run_classifier():
    from utils.summary_store import get_channel_summary

    channel_id = 1472003599985934560  # #openclaw
    if len(sys.argv) > 1:
        channel_id = int(sys.argv[1])

    raw, _ = get_channel_summary(channel_id)
    if not raw:
        print("No summary found.")
        return

    summary = json.loads(raw)

    # Build items list for classification
    items = []

    for d in summary.get("decisions", []):
        items.append({
            "id": d["id"],
            "category": "DECISION",
            "status": d.get("status", "active"),
            "text": d.get("decision", ""),
        })

    for f in summary.get("key_facts", []):
        items.append({
            "id": f["id"],
            "category": "KEY_FACT",
            "status": f.get("status", "active"),
            "text": f.get("fact", ""),
        })

    for a in summary.get("action_items", []):
        items.append({
            "id": a["id"],
            "category": "ACTION_ITEM",
            "status": a.get("status", "open"),
            "text": f"{a.get('task', '')} (owner: {a.get('owner', '?')})",
        })

    for q in summary.get("open_questions", []):
        items.append({
            "id": q["id"],
            "category": "OPEN_QUESTION",
            "status": q.get("status", "open"),
            "text": q.get("question", ""),
        })

    for t in summary.get("active_topics", []):
        cat = "ARCHIVED_TOPIC" if t.get("status") == "archived" else "ACTIVE_TOPIC"
        items.append({
            "id": t["id"],
            "category": cat,
            "status": t.get("status", "active"),
            "text": t.get("title", ""),
        })

    print(f"Items to classify: {len(items)}")
    print(f"  Decisions: {sum(1 for i in items if i['category'] == 'DECISION')}")
    print(f"  Key Facts: {sum(1 for i in items if i['category'] == 'KEY_FACT')}")
    print(f"  Action Items: {sum(1 for i in items if i['category'] == 'ACTION_ITEM')}")
    print(f"  Open Questions: {sum(1 for i in items if i['category'] == 'OPEN_QUESTION')}")
    print(f"  Active Topics: {sum(1 for i in items if i['category'] == 'ACTIVE_TOPIC')}")
    print(f"  Archived Topics: {sum(1 for i in items if i['category'] == 'ARCHIVED_TOPIC')}")

    # Format items for the classifier
    items_text = json.dumps(items, indent=2)
    print(f"\nItems payload: {len(items_text)} chars")

    # Call GPT-5.4 nano
    print("\nCalling GPT-5.4 nano...")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": f"Classify these items:\n{items_text}"},
            ],
            temperature=0,
        )

        result_text = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens

        print(f"Tokens: {tokens_in} in + {tokens_out} out")
        cost_in = tokens_in * 0.03 / 1_000_000
        cost_out = tokens_out * 0.15 / 1_000_000
        print(f"Cost: ${cost_in + cost_out:.6f}")

    except Exception as e:
        print(f"Error calling nano: {e}")
        return

    # Parse results
    print(f"\n{'='*60}")
    print("CLASSIFICATION RESULTS")
    print(f"{'='*60}")

    try:
        # Strip markdown fences if present
        clean = result_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        results = json.loads(clean)
    except json.JSONDecodeError:
        print("Failed to parse JSON response:")
        print(result_text)
        return

    keep = [r for r in results if r.get("verdict") == "KEEP"]
    drop = [r for r in results if r.get("verdict") == "DROP"]
    reclassify = [r for r in results if r.get("verdict") == "RECLASSIFY"]

    print(f"\nKEEP: {len(keep)}")
    for r in keep:
        print(f"  ✅ [{r['current']}] {r['id']}")

    print(f"\nDROP: {len(drop)}")
    for r in drop:
        print(f"  ❌ [{r['current']}] {r['id']} — {r.get('reason', '')}")

    print(f"\nRECLASSIFY: {len(reclassify)}")
    for r in reclassify:
        print(f"  🔄 [{r['current']} → {r.get('reclassify_to')}] "
              f"{r['id']} — {r.get('reason', '')}")

    print(f"\n{'='*60}")
    print(f"Summary: {len(keep)} keep, {len(drop)} drop, "
          f"{len(reclassify)} reclassify out of {len(results)} items")


if __name__ == "__main__":
    asyncio.run(run_classifier())
