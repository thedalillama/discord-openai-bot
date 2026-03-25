#!/usr/bin/env python3
"""Ask the Structurer what schema it thinks it has."""
import json, sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from utils.message_store import init_database
init_database()

async def main():
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER
    from utils.summary_schema import DELTA_SCHEMA
    from utils.summary_prompts_authoring import STRUCTURER_SYSTEM_PROMPT

    provider = get_provider(SUMMARIZER_PROVIDER)

    prompt = f"""You are about to be used as a structured data extractor.

Here is your system prompt:
---
{STRUCTURER_SYSTEM_PROMPT}
---

Here is the JSON schema you will be constrained to:
---
{json.dumps(DELTA_SCHEMA, indent=2)}
---

Questions:
1. List every valid value for the "op" field.
2. Is "add_topic" in the enum? Yes or no.
3. What fields would you use for an add_topic op?
4. If the minutes contain "### Database Decision" followed by a \
paragraph, what op would you emit?"""

    response = await provider.generate_ai_response(
        [{"role": "user", "content": prompt}],
        temperature=0,
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
