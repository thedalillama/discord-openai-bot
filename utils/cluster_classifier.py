# utils/cluster_classifier.py
# Version 1.6.0
"""
GPT-4o-mini classifier for cross-cluster overview items.

Per-item whitelist filter — first quality gate in the pipeline.
QA (dedup + answered-Q check) has moved to utils/cluster_qa.py.

CHANGES v1.6.0: Remove QA pass — moved to cluster_qa.py
- REMOVED: qa_pass(), _call_qa(), QA_SYSTEM_PROMPT, _QA_REQUIRED_KEYS
  (replaced by deduplicate_summary() + remove_answered_questions() in
  cluster_qa.py which use embedding dedup + targeted GPT-4o-mini check)

CHANGES v1.5.0: QA pass switched to DeepSeek Reasoner
CHANGES v1.4.0: qa_pass() cross-item consistency check
CHANGES v1.3.0: max_tokens 1024→4096; default-to-DROP; DEBUG logging
CHANGES v1.2.0: action item prefix AI→A; include owner in prompt line
CHANGES v1.1.0: expanded prompt; open_questions whitelist (category 6)
CHANGES v1.0.1: remove maxItems caps
CREATED v1.0.0: classify_overview_items() (SOW v5.3.0)
"""
import os
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('cluster_classifier')

CLASSIFIER_SYSTEM_PROMPT = """\
You are a strict filter for a Discord bot's always-on memory.
DEFAULT ACTION IS DROP. Only mark KEEP for items matching the
whitelist below. Everything else is DROP.

KEEP whitelist (ONLY these categories survive):
1. User identity: name, age, location, occupation, preferences
   explicitly stated by the user
2. Project decisions: database choice, hosting region, tech stack,
   rate limits — the CURRENT decision only, not historical ones
3. Project configuration: specific values in use (model names,
   API settings, regions, limits)
4. Open action items: tasks with a named human owner that are
   still actionable TODAY
5. Channel purpose: what the channel is used for
6. Open questions: ONLY questions that represent a genuinely
   unresolved project or planning decision that the channel needs
   to revisit. Examples: "What region should we deploy to?" or
   "Should we add a caching layer?"

DROP everything else, including but not limited to:
- General knowledge (science, history, public figures, animals)
- Encyclopedic facts about ANY topic (evolution, physics, etc.)
- API pricing details (the bot can look these up)
- Past commodity prices, weather, time, moon phases
- Math calculations
- Book/movie plot summaries or reading progress
- Bot capabilities or limitations
- Questions someone asked a bot in past conversation
- "What did we discuss/decide" recall questions
- "Can you/do you" capability questions
- Trivia, curiosity, or rhetorical questions
- Questions about current prices, times, or weather
- Questions about topics (animals, physics, books, people)
- "What specific aspect would you like to discuss" prompts
- Zoo incidents, animal behavior, aerodynamics
- Anything the LLM would know from training data
- Historical decisions that were later changed
- Action items assigned to bots, not humans
- Action items that are no longer actionable (old lookups)

For each item respond KEEP or DROP. When in doubt, DROP.
"""


def _build_prompt(overview_result):
    """Build classifier user prompt from overview arrays."""
    lines = ["Classify each item as KEEP or DROP:", ""]
    sections = [
        ("[DECISIONS]",      "D",  "decisions"),
        ("[KEY_FACTS]",      "KF", "key_facts"),
        ("[ACTION_ITEMS]",   "A",  "action_items"),
        ("[OPEN_QUESTIONS]", "Q",  "open_questions"),
    ]
    for header, prefix, field in sections:
        items = overview_result.get(field, [])
        if not items:
            continue
        lines.append(header)
        for i, item in enumerate(items, 1):
            text = item.get("text", "")
            if field == "action_items" and item.get("owner"):
                text = f"{text} — {item['owner']}"
            lines.append(f"{prefix}{i}: {text}")
        lines.append("")
    return "\n".join(lines)


def _apply_verdicts(response_text, overview_result):
    """Parse KEEP/DROP response. Missing verdicts default to DROP."""
    verdicts = {}
    for line in response_text.splitlines():
        line = line.strip()
        if ": " in line:
            key, verdict = line.split(": ", 1)
            verdicts[key.strip()] = verdict.strip().upper()
    sections = [
        ("decisions", "D"), ("key_facts", "KF"),
        ("action_items", "A"), ("open_questions", "Q"),
    ]
    result = dict(overview_result)
    total_kept = total_dropped = 0
    for field, prefix in sections:
        kept, dropped_labels = [], []
        for i, item in enumerate(overview_result.get(field, []), 1):
            if verdicts.get(f"{prefix}{i}", "DROP") != "DROP":
                kept.append(item)
            else:
                dropped_labels.append(item.get("text", "")[:60])
        result[field] = kept
        total_kept += len(kept)
        total_dropped += len(dropped_labels)
        if dropped_labels:
            logger.debug(f"Classifier dropped [{field}]: {dropped_labels}")
    logger.info(f"Classifier: {total_kept} kept, {total_dropped} dropped")
    return result


def _call_classifier(prompt):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                  {"role": "user",   "content": prompt}],
        temperature=0, max_tokens=4096,
    )
    return resp.choices[0].message.content or ""


async def classify_overview_items(overview_result):
    """Filter overview arrays with GPT-4o-mini. Fail-safe: returns original on error."""
    prompt = _build_prompt(overview_result)
    logger.debug(f"Classifier prompt: {len(prompt)} chars")
    try:
        text = await asyncio.to_thread(_call_classifier, prompt)
        logger.debug(
            f"Classifier raw response ({len(text)} chars, "
            f"{text.count(chr(10))} lines)")
        logger.debug(f"Classifier response preview: {text[:500]}")
        return _apply_verdicts(text, overview_result)
    except Exception as e:
        logger.warning(f"Classifier failed, using unfiltered items: {e}")
        return overview_result
