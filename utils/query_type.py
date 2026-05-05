# utils/query_type.py
# Version 1.0.0
"""
Query type classifier for context assembly (SOW v7.6.0).

Distinguishes conversational messages (greetings, jokes, reactions) from
information queries (questions, requests, attribution). Conversational queries
bypass Layer 1 always-on summary and Layer 3 retrieval — they receive bot
personality, control file, and Layer 2 only.

CREATED v1.0.0: Regex/heuristic classifier; no LLM (SOW v7.6.0)
"""
import re
from enum import Enum


class QueryType(Enum):
    CONVERSATIONAL = "conversational"
    INFORMATION = "information"


_CONV_RE = [re.compile(p, re.IGNORECASE) for p in [
    r'^(hi|hey|hello|yo|sup|hola)\b',
    r'^(thanks|thank you|thx|ty)\b',
    r'^(ok|okay|cool|nice|got it|sounds good|alright)\b',
    r'^(lol|haha|hehe|lmao|lmfao)\b',
    r'^knock\s*knock\b',
    r"^who'?s there\b",
    r'^(yes|no|maybe|sure|nope|yep|yeah|yup)\b\.?$',
    r'^(bye|goodbye|later|cya|ttyl)\b',
]]

_QUESTION_STARTS = frozenset([
    'what', 'who', 'when', 'where', 'why', 'how',
    'which', 'did', 'do', 'does', 'is', 'are',
    'was', 'were', 'can', 'could', 'would', 'should',
    'tell', 'show', 'find',
])
_REQUEST_RE = re.compile(
    r'\b(tell me|show me|find|search|look up|remember|what did|who said)\b',
    re.IGNORECASE)


def classify_query(query_text, members=None):
    """Classify user message. Returns QueryType.

    members: optional list of known author names for author-prefix stripping
    before classification (e.g. 'Alice: knock knock' → 'knock knock').
    """
    raw = (query_text or "").strip()
    if not raw:
        return QueryType.CONVERSATIONAL
    text = raw.lower()

    if ':' in text:
        prefix, rest = text.split(':', 1)
        prefix = prefix.strip()
        is_known = (any(prefix == m.lower().split('#')[0].strip() for m in members)
                    if members
                    else len(prefix.split()) == 1 and len(prefix) <= 32)
        if is_known and rest.strip():
            text = rest.strip()

    for pat in _CONV_RE:
        if pat.match(text):
            return QueryType.CONVERSATIONAL

    first = text.split()[0] if text.split() else ""
    if text.endswith('?') or first in _QUESTION_STARTS or _REQUEST_RE.search(text):
        return QueryType.INFORMATION

    return QueryType.CONVERSATIONAL
