# utils/response_qc.py
# Version 1.2.0
"""
General response quality control pass (SOW v7.4.1).

CHANGES v1.2.0: _parse_qc_result() returns 3-tuple (passed, unsupported, reasons);
  run_response_qc() accepts receipt_data kwarg; populates receipt_data["qc_fail_details"]
  on double-fail so !explain can show pass 1/2 responses and per-claim reasons.
CHANGES v1.1.2: Rewrite QC prompt — presence-only check, no temporal/accuracy reasoning.
CHANGES v1.1.1: Instruct QC to verify against context only — not training data.
CHANGES v1.1.0: Remove token_cap truncation; add "'s Channel Messages" marker.
CHANGES v1.0.2: Python absence pre-check. v1.0.1: tune _QC_SYSTEM.
CREATED v1.0.0: Full QC pipeline (see git history)
"""
import re
import os
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('response_qc')

_CONTEXT_MARKERS = (
    "--- CONVERSATION CONTEXT ---",
    "--- PAST MESSAGES FROM THIS CHANNEL",
    "'s Channel Messages",
)

_ABSENCE_RE = re.compile(
    r"\b(hasn'?t|haven'?t|didn'?t?|no\s+(record|mention|discussion|specific|"
    r"insights?|information|evidence|detail)|not\s+(found|discussed|mentioned|"
    r"shared|recorded|available)|nothing\s+\S+\s+found|doesn'?t\s+appear|"
    r"i\s+(don'?t|couldn'?t)\s+(see|find|locate)|no\s+evidence|"
    r"not\s+in\s+(our|the)\s+conversation)\b", re.IGNORECASE)


def _is_grounded_absence(response_text):
    """True if response is primarily absence/not-found claims with no positive assertions.

    Bypasses QC — GPT-4o-mini does not reliably follow 'do not flag negative
    claims' instructions, so we gate at the Python level instead.
    """
    sentences = [s.strip() for s in re.split(r'[.!?]', response_text) if s.strip()]
    if not sentences:
        return False
    absence_count = sum(1 for s in sentences if _ABSENCE_RE.search(s))
    return absence_count >= (len(sentences) + 1) // 2

_QC_SYSTEM = (
    "You are checking one thing only: does the response contain specific values "
    "(numbers, exact quotes, named dates) that are completely absent from the context?\n\n"
    "PASS if the value appears anywhere in the context — even once, even in an older "
    "message. Do NOT evaluate whether it is the most recent value, whether the "
    "attribution wording is perfect, or whether the response could be more precise.\n\n"
    "Do NOT flag:\n"
    "- Hedges ('around', 'approximately', 'roughly') applied to a value that IS in context\n"
    "- Paraphrases of statements that ARE in context\n"
    "- Temporal framing ('current', 'at the time') when the underlying value IS in context\n"
    "- General knowledge, filler, negative claims, or absence statements\n\n"
    "Only flag a sentence if a specific value it asserts is NOWHERE in the context at all.\n\n"
    "If nothing is absent, respond exactly: PASS\n"
    "If any value is absent, for each one output:\n"
    "  UNSUPPORTED: <sentence>\n"
    "  REASON: <the specific value that cannot be found anywhere in the context>"
)


def _has_injected_context(system_content):
    """True if system_content contains an always-on summary or retrieved block."""
    return any(m in system_content for m in _CONTEXT_MARKERS)


def _build_context_block(messages):
    """Build full context string for the QC prompt.

    Includes complete system content and all session turns. No truncation —
    QC must see the exact context the answering LLM received.
    """
    if not messages:
        return ""
    sys_content = messages[0].get("content", "")
    parts = [sys_content]
    if len(messages) > 2:
        turn_lines = [
            f"[{msg.get('role', 'user')}] {msg.get('content', '')}"
            for msg in messages[1:-1]
        ]
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
    """Parse QC response. Returns (passed, unsupported_sentences, reasons).
    Ambiguous/empty response → fail-open (True, [], []).
    """
    raw = raw.strip()
    if raw.upper() == "PASS":
        return True, [], []
    unsupported, reasons = [], []
    pending_sentence = None
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("UNSUPPORTED:"):
            pending_sentence = line[len("UNSUPPORTED:"):].strip()
        elif line.upper().startswith("REASON:") and pending_sentence is not None:
            reason = line[len("REASON:"):].strip()
            logger.info(f"QC unsupported reason: {reason}")
            unsupported.append(pending_sentence)
            reasons.append(reason)
            pending_sentence = None
    if pending_sentence:
        unsupported.append(pending_sentence)
        reasons.append("")
    return (False, unsupported, reasons) if unsupported else (True, [], [])


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
                          provider_override=None, receipt_data=None):
    """Orchestrate QC check → re-reason → second QC.

    Returns:
        str  — verified/corrected response (PASS or fail-open paths)
        None — both QC checks failed; caller must send QC_FAIL message
    On double-fail, populates receipt_data["qc_fail_details"] if provided.
    Max API calls: 2 × GPT-4o-mini + 1 × provider.
    """
    from utils.ai_utils import generate_ai_response
    try:
        sys_content = messages[0].get("content", "") if messages else ""
        if not _has_injected_context(sys_content):
            return response_text

        context_block = _build_context_block(messages)
        question = messages[-1].get("content", "") if messages else ""

        if _is_grounded_absence(response_text):
            logger.debug(f"QC skip: grounded absence response ch:{channel_id}")
            return response_text

        # Pass 1
        try:
            raw1 = await asyncio.to_thread(
                _call_qc, _build_qc_prompt(context_block, question, response_text))
            logger.debug(f"QC pass 1: {raw1[:120]}")
            passed1, unsupported, reasons1 = _parse_qc_result(raw1)
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

        if _is_grounded_absence(new_resp):
            logger.debug(f"QC skip: grounded absence after re-reason ch:{channel_id}")
            return new_resp

        # Pass 2
        try:
            raw2 = await asyncio.to_thread(
                _call_qc, _build_qc_prompt(context_block, question, new_resp))
            logger.debug(f"QC pass 2: {raw2[:120]}")
            passed2, unsupported2, reasons2 = _parse_qc_result(raw2)
        except Exception as e:
            logger.warning(f"QC pass 2 error, failing open: {e}")
            return new_resp

        if passed2:
            logger.info("QC PASS after re-reason")
            return new_resp

        logger.info("QC FAIL after re-reason → QC_FAIL")
        if receipt_data is not None:
            receipt_data["qc_fail_details"] = {
                "pass1_response": response_text,
                "pass1_unsupported": unsupported,
                "pass1_reasons": reasons1,
                "pass2_response": new_resp,
                "pass2_unsupported": unsupported2,
                "pass2_reasons": reasons2,
            }
        return None

    except Exception as e:
        logger.error(f"run_response_qc unexpected error: {e}")
        return response_text
