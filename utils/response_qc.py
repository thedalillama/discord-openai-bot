# utils/response_qc.py
# Version 1.0.1
"""
General response quality control pass (SOW v7.4.1).

Replaces citation-specific verification (v7.4.0) with a broader LLM check:
after generating a response, GPT-4o-mini verifies it is logically supported
by the full injected context (always-on summary, session bridge, retrieved
segments). Unsupported claims trigger re-reasoning; persistent failure returns
None to signal QC_FAIL.

CHANGES v1.0.1: Tune _QC_SYSTEM to reduce pass-2 false positives
- MODIFIED: _QC_SYSTEM — explicit do-not-flag list; adds negative claims,
  absence-of-information statements, and framing sentences to ignored set;
  restricts flagging to specific positive factual assertions only

CREATED v1.0.0:
- _has_injected_context(system_content) — detect injected factual context
- _build_context_block(messages, token_cap) — format full context for QC
- _build_qc_prompt(context_block, question, response) — QC prompt string
- _call_qc(prompt) — sync GPT-4o-mini call (asyncio.to_thread wrapper)
- _parse_qc_result(raw) — (passed, unsupported_sentences)
- build_correction_context(sentences) — [QC CORRECTION] prohibition block
- run_response_qc(response_text, messages, channel_id, ...) — orchestrator
"""
import os
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('response_qc')

_CONTEXT_MARKERS = (
    "--- CONVERSATION CONTEXT ---",
    "--- PAST MESSAGES FROM THIS CHANNEL",
)

_QC_SYSTEM = (
    "You are a factual accuracy checker. Catch AI responses that assert "
    "precise, specific facts about conversation content that are NOT in the context.\n\n"
    "Do NOT flag:\n"
    "- General knowledge from model training\n"
    "- Hedged statements (\"may\", \"likely\", \"I believe\", \"seems\")\n"
    "- Conversational filler, introductory phrases, or framing sentences\n"
    "- Negative claims (that something was NOT discussed, NOT found, or NOT present)\n"
    "- Acknowledgments of limited or missing information\n"
    "- General characterizations or reasonable summaries of events that ARE in context\n\n"
    "Only flag: (1) sentences with precise details (exact quotes, specific numbers, "
    "named events with specifics, exact dates) that contradict or cannot be found "
    "anywhere in the provided context; or (2) statements that attribute an action or "
    "statement to a specific person/bot when the context clearly attributes it to "
    "a different person/bot.\n\n"
    "If all claims are supported or ignorable, respond exactly: PASS\n"
    "If any claim is unsupported, list each unsupported sentence on its own "
    "line prefixed with UNSUPPORTED:"
)


def _has_injected_context(system_content):
    """True if system_content contains an always-on summary or retrieved block."""
    return any(m in system_content for m in _CONTEXT_MARKERS)


def _build_context_block(messages, token_cap=6000):
    """Build context string for the QC prompt.

    System content is always included in full. Session turns (messages[1:-1])
    are appended oldest-first; stops when total chars exceed token_cap * 4.
    """
    if not messages:
        return ""
    sys_content = messages[0].get("content", "")
    char_cap = token_cap * 4
    parts = [sys_content]
    used = len(sys_content)
    if len(messages) > 2:
        turn_lines = []
        for msg in messages[1:-1]:
            line = f"[{msg.get('role', 'user')}] {msg.get('content', '')}"
            if used + len(line) > char_cap:
                break
            turn_lines.append(line)
            used += len(line)
        if turn_lines:
            parts.append("--- SESSION HISTORY ---\n" + "\n".join(turn_lines))
    return "\n\n".join(parts)


def _build_qc_prompt(context_block, question, response):
    return (
        f"CONTEXT:\n{context_block}\n\n"
        f"USER QUESTION: {question}\n\n"
        f"ASSISTANT RESPONSE:\n{response}"
    )


def _call_qc(prompt):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": _QC_SYSTEM},
                  {"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
    )
    return resp.choices[0].message.content or ""


def _parse_qc_result(raw):
    """Parse QC response. Returns (passed, unsupported_sentences).
    Ambiguous/empty response → fail-open (True, []).
    """
    raw = raw.strip()
    if raw.upper() == "PASS":
        return True, []
    unsupported = []
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("UNSUPPORTED:"):
            sentence = line[len("UNSUPPORTED:"):].strip()
            if sentence:
                unsupported.append(sentence)
    return (False, unsupported) if unsupported else (True, [])


def build_correction_context(unsupported_sentences):
    """Build [QC CORRECTION] prohibition block from list of unsupported sentences."""
    sentences_text = "\n".join(f'  "{s}"' for s in unsupported_sentences)
    return (
        "[QC CORRECTION]\n"
        "The following statements in your previous response are not supported "
        "by the context you were given and must be omitted:\n\n"
        f"{sentences_text}\n\n"
        "Respond again using only what the context directly states or clearly "
        "implies. Do not reintroduce these claims."
    )


async def run_response_qc(response_text, messages, channel_id,
                          provider_override=None):
    """Orchestrate QC check → re-reason → second QC.

    Returns:
        str  — verified/corrected response (PASS or fail-open paths)
        None — both QC checks failed; caller must send QC_FAIL message
    Max API calls: 2 × GPT-4o-mini + 1 × provider.
    """
    from utils.ai_utils import generate_ai_response
    try:
        sys_content = messages[0].get("content", "") if messages else ""
        if not _has_injected_context(sys_content):
            return response_text

        context_block = _build_context_block(messages)
        question = messages[-1].get("content", "") if messages else ""

        # Pass 1
        try:
            raw1 = await asyncio.to_thread(
                _call_qc, _build_qc_prompt(context_block, question, response_text))
            logger.debug(f"QC pass 1: {raw1[:120]}")
            passed1, unsupported = _parse_qc_result(raw1)
        except Exception as e:
            logger.warning(f"QC pass 1 error, failing open: {e}")
            return response_text

        if passed1:
            logger.debug("QC PASS (pass 1)")
            return response_text

        logger.info(f"QC FAIL pass 1: {len(unsupported)} unsupported claim(s)")

        # Re-reason: prepend prohibition to final user message
        correction = build_correction_context(unsupported)
        mod_msgs = list(messages)
        if mod_msgs and mod_msgs[-1].get("role") == "user":
            last_q = mod_msgs[-1]["content"]
            mod_msgs[-1] = {**mod_msgs[-1], "content": f"{correction}\n\n{last_q}"}

        try:
            new_resp = await generate_ai_response(
                mod_msgs, channel_id=channel_id, provider_override=provider_override)
            if isinstance(new_resp, dict):
                new_resp = new_resp.get("text", response_text)
        except Exception as e:
            logger.warning(f"Re-reason call failed, failing open: {e}")
            return response_text

        # Pass 2
        try:
            raw2 = await asyncio.to_thread(
                _call_qc, _build_qc_prompt(context_block, question, new_resp))
            logger.debug(f"QC pass 2: {raw2[:120]}")
            passed2, _ = _parse_qc_result(raw2)
        except Exception as e:
            logger.warning(f"QC pass 2 error, failing open: {e}")
            return new_resp

        if passed2:
            logger.info("QC PASS after re-reason")
            return new_resp

        logger.info("QC FAIL after re-reason → QC_FAIL")
        return None

    except Exception as e:
        logger.error(f"run_response_qc unexpected error: {e}")
        return response_text
