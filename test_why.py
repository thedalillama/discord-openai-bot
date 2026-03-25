#!/usr/bin/env python3
"""Ask the Structurer why it didn't generate add_topic ops."""
import json, sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from utils.message_store import init_database
init_database()

async def main():
    channel_id = 1472003599985934560

    with open(f"data/secretary_raw_{channel_id}.txt") as f:
        minutes = f.read()
    with open(f"data/structurer_raw_{channel_id}.json") as f:
        structurer_output = f.read()

    prompt = f"""You were given these meeting minutes to convert into JSON delta ops:

{minutes[:3000]}

You produced this output:
{structurer_output}

The minutes contain 4 ACTIVE TOPICS (Database Decision, Animal Evolution \
and Strength, Bachelor Party Toasts, AI Model Pricing and Image Generation) \
and 7 ARCHIVED items. But your output has zero add_topic ops.

Why did you not generate add_topic ops for the ACTIVE TOPICS and ARCHIVED \
sections? What in the schema or instructions caused you to skip them?"""

    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    provider = get_provider(SUMMARIZER_PROVIDER)

    response = await provider.generate_ai_response(
        [{"role": "user", "content": prompt}],
        temperature=0,
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
