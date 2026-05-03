# utils/query_planner.py
# Version 1.1.4
"""
Query planner for metadata-aware retrieval (SOW v7.5.0).

Fast-path check detects metadata signals (speaker names, temporal, existence
patterns). Queries without signals bypass the planner entirely — no latency
penalty for topic-only queries.

When signals are detected, GPT-4o-mini parses the query into structured intent
(author list, time bounds, mode) which the router converts to SQL pre-filters.
Planner and embedding calls run in parallel via ThreadPoolExecutor to hide
planner latency. Both are synchronous HTTP calls, so ThreadPoolExecutor is used
instead of asyncio (build_context_for_provider runs in a thread pool already).

plan_and_retrieve() is the Layer 3 entry point, replacing _retrieve_segment_context
in context_manager.py. Returns (context_text, tokens, receipt, citation_map).

CHANGES v1.1.4: Add _ATTRIB_RE — 'who said/guessed/told' triggers planner with mode=attribution.
CHANGES v1.1.3: Fuzzy-match author names; exclude current speaker from pronoun resolution.
CHANGES v1.1.1: Stronger pronoun resolution instruction; _resolve_pronoun_fallback() fallback.
CHANGES v1.1.0: Token-level name matching (≥4-char tokens); _PRONOUN_RE; last 5 turns for pronoun resolution.
CREATED v1.0.0: Query planner + fast-path + plan_and_retrieve() (SOW v7.5.0)
"""
import re
import json
import sqlite3
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from config import DATABASE_PATH, QUERY_PLANNER_MODEL
from utils.logging_utils import get_logger

logger = get_logger('query_planner')

_member_cache = {}

_TIME_RE = re.compile(
    r'\b(yesterday|today|this (morning|afternoon|week)|'
    r'last (week|month|night|\d+ days?)|\d+ (days?|weeks?|months?) ago|'
    r'recently|earlier|just now)\b', re.IGNORECASE)

_EXIST_RE = re.compile(
    r'\b(did we (ever|already)|have we (ever )?(discussed|talked|mentioned|covered)|'
    r'has anyone|was .{0,20} (ever |discussed|mentioned)|'
    r'has .{0,20} (come up|been discussed))\b', re.IGNORECASE)

_ATTRIB_RE = re.compile(r'\bwho\s+(said|told|mentioned|guessed|asked|wrote|posted|suggested|noted|thought)\b', re.IGNORECASE)
_PRONOUN_RE = re.compile(
    r'\bwhat\s+(?:did|has|have)\s+(?:he|she|they)\b'
    r'|\b(?:he|she|they)\s+(?:said|mentioned|discussed|wrote|posted|asked|'
    r'replied|suggested|explained|noted|thought)\b', re.IGNORECASE)

_PLANNER_TOOL = {
    "name": "retrieve_conversation",
    "description": "Retrieve conversation history with structured filters.",
    "parameters": {
        "type": "object",
        "properties": {
            "content_query": {
                "type": "string",
                "description": ("Topic to search for. Empty string if query "
                                "is purely about who spoke or when.")
            },
            "author": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("Participant names to filter by. Use exact "
                                "names from the participant list. Empty if no "
                                "speaker filter.")
            },
            "after": {"type": ["string", "null"],
                      "description": "ISO 8601 start time. Null if no filter."},
            "before": {"type": ["string", "null"],
                       "description": "ISO 8601 end time. Null if no filter."},
            "mode": {
                "type": "string",
                "enum": ["lookup", "summary", "existence", "attribution"],
                "description": ("lookup=find content. summary=broad overview. "
                                "existence=did topic ever come up. "
                                "attribution=who said a specific thing.")
            }
        },
        "required": ["content_query", "mode"]
    }
}


def get_channel_members(channel_id):
    """Return list of distinct author names for channel (cached per channel)."""
    if channel_id not in _member_cache:
        conn = sqlite3.connect(DATABASE_PATH)
        try:
            rows = conn.execute(
                "SELECT DISTINCT author_name FROM messages "
                "WHERE channel_id=? AND author_name IS NOT NULL",
                (channel_id,)).fetchall()
        finally:
            conn.close()
        _member_cache[channel_id] = [r[0] for r in rows if r[0]]
    return _member_cache[channel_id]


def needs_query_planner(query_text, channel_id):
    """Return True if query contains metadata signals requiring the planner."""
    q = query_text.lower()
    q_words = set(re.findall(r'\b\w+\b', q))
    for name in get_channel_members(channel_id):
        clean = name.split('#')[0].strip().lower()
        if len(clean) >= 3 and clean in q:
            return True
        for tok in re.findall(r'\b\w+\b', clean):
            if len(tok) >= 4 and tok in q_words:
                return True
    return bool(_TIME_RE.search(q) or _EXIST_RE.search(q) or _PRONOUN_RE.search(q) or _ATTRIB_RE.search(q))


def run_query_planner(query_text, channel_id, recent_context=None, current_speaker=None):
    """Parse query into structured intent dict; returns None on failure."""
    import openai
    from config import OPENAI_API_KEY
    members = get_channel_members(channel_id)
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    system = (
        f"You are a query planner for a conversation memory system.\n"
        f"Current time: {now_iso}\n"
        f"Channel participants: {', '.join(members) or 'unknown'}\n\n"
        "Rules:\n"
        "- Resolve relative dates to ISO 8601 using the current time.\n"
        "- Match author names against the participant list exactly.\n"
        "- Resolve pronouns (he/she/they) to a third-party participant using recent context; exclude the current speaker as a referent.\n"
        + (f"- Current speaker is '{current_speaker}' — never resolve pronouns to them.\n" if current_speaker else "")
        + "- mode=existence for 'did we ever', 'have we discussed' patterns.\n"
        "- mode=attribution for 'who said', 'was it X or Y that' patterns.\n"
        "- mode=summary for broad overview with no specific topic.\n"
        "- mode=lookup for all other queries.\n"
        "- Leave author empty if query is not about a specific participant.\n"
        "- Leave content_query empty if query is purely about who/when."
    )
    if recent_context:
        ctx_lines = "\n".join(
            f"[{m.get('role','user')}] {m.get('content','')[:200]}"
            for m in recent_context)
        system += f"\n\nRecent context:\n{ctx_lines}"
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=QUERY_PLANNER_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": query_text}],
            tools=[{"type": "function", "function": _PLANNER_TOOL}],
            tool_choice={"type": "function",
                         "function": {"name": "retrieve_conversation"}},
            max_tokens=300,
        )
        args = resp.choices[0].message.tool_calls[0].function.arguments
        intent = json.loads(args)
        intent.setdefault("author", [])
        intent.setdefault("after", None)
        intent.setdefault("before", None)
        intent.setdefault("content_query", "")
        intent.setdefault("mode", "lookup")
        logger.debug(f"Planner intent ch:{channel_id}: {intent}")
        return intent
    except Exception as e:
        logger.warning(f"Query planner failed ch:{channel_id}: {e}")
        return None


def _resolve_pronoun_fallback(recent_context, channel_id, current_speaker=None):
    toks = {t: n for n in get_channel_members(channel_id)
            for t in re.findall(r'\b\w+\b', n.split('#')[0].lower()) if len(t) >= 4}
    for msg in reversed(recent_context):
        for tok, name in toks.items():
            if name.lower() != (current_speaker or "").lower() and re.search(r'\b' + re.escape(tok) + r'\b', msg.get('content', '').lower()):
                return name
    return None


def plan_and_retrieve(channel_id, conversation_msgs, budget, exclude_ids=None):
    """Layer 3 entry point — replaces _retrieve_segment_context in context_manager.

    Fast-path: topic-only queries skip the planner and run existing RRF.
    Planner path: parallel GPT-4o-mini planner + query embedding via
    ThreadPoolExecutor, then route_query() for metadata-filtered retrieval.

    Returns (context_text, tokens_used, receipt, citation_map).
    """
    from utils.context_retrieval import _retrieve_segment_context
    from utils.query_router import route_query

    _empty = ("", 0, {}, {})
    query_text = None
    for msg in reversed(conversation_msgs or []):
        if msg.get("role") == "user" and msg.get("content", "").strip():
            query_text = msg["content"].strip()
            break
    if not query_text:
        return _empty

    detect_text = (query_text.split(': ', 1)[1]
                   if ': ' in query_text else query_text)
    current_speaker = query_text.split(': ', 1)[0] if ': ' in query_text else None

    if not needs_query_planner(detect_text, channel_id):
        return _retrieve_segment_context(
            channel_id, conversation_msgs, budget, exclude_ids=exclude_ids)

    # Parallel planner + embed
    from utils.embedding_context import embed_query_with_smart_context
    recent_for_planner = [m for m in (conversation_msgs or [])[-6:]
                          if m.get("role") in ("user", "assistant")][-5:]
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        planner_f = ex.submit(run_query_planner, detect_text, channel_id,
                              recent_for_planner, current_speaker)
        embed_f = ex.submit(
            embed_query_with_smart_context,
            query_text, channel_id, conversation_msgs)
        intent = planner_f.result()
        query_vec, embedding_path = embed_f.result()
    planner_ms = round((time.monotonic() - t0) * 1000)

    if query_vec is None:
        return _empty

    if intent is None:
        logger.debug(f"Planner failed ch:{channel_id} — falling back to RRF")
        return _retrieve_segment_context(
            channel_id, conversation_msgs, budget,
            exclude_ids=exclude_ids,
            query_vec=query_vec, embedding_path=embedding_path,
            query_text=detect_text)

    if not intent.get("author") and _PRONOUN_RE.search(detect_text):
        ref = _resolve_pronoun_fallback(recent_for_planner[:-1], channel_id, current_speaker)
        if ref:
            intent["author"] = [ref]

    if intent.get("author"):
        intent["author"] = [next((m for m in get_channel_members(channel_id) if a.lower() in m.lower()), a) for a in intent["author"]]

    recent_ids = {m["_msg_id"] for m in conversation_msgs if "_msg_id" in m}
    if exclude_ids:
        recent_ids = recent_ids | set(exclude_ids)

    return route_query(
        intent, query_vec, channel_id, budget,
        exclude_ids=recent_ids, embedding_path=embedding_path,
        query_text=detect_text, planner_ms=planner_ms)
