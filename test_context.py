# test_context.py
# Load the summary, format it, combine with system prompt,
# add a test question, call the provider, print the response

import json
from utils.summary_store import get_channel_summary
from utils.summary_display import format_summary_for_context
from utils.history.prompts import get_system_prompt

CHANNEL_ID = 1472003599985934560  # #openclaw

# Build the same system prompt the bot builds
system_prompt = get_system_prompt(CHANNEL_ID)
raw, _ = get_channel_summary(CHANNEL_ID)
summary = json.loads(raw)
summary_text = format_summary_for_context(summary)

combined = f"{system_prompt}\n\n--- CONVERSATION CONTEXT ---\n{summary_text}"

print("=== SYSTEM PROMPT ===")
print(combined)
print(f"\n=== {len(combined)} chars ===")

# Ask a test question
question = "What's my favorite number?"

messages = [
    {"role": "system", "content": combined},
    {"role": "user", "content": f"absolutebeginner: {question}"},
]

# Call the provider
from ai_providers import get_provider
provider = get_provider("deepseek")
import asyncio
response = asyncio.run(provider.generate_ai_response(messages))
print(f"\n=== RESPONSE ===\n{response}")
