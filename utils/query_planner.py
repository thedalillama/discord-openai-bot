# utils/query_planner.py
# Version 1.2.0
"""
Query planner for metadata-aware retrieval (SOW v7.5.0).

CHANGES v1.2.0: extract_query_info() validates author prefix against member list
  (fixes colon-in-URL false splits); normalize_authors() logs collisions;
  run_planner_and_embed() extracted; TTL member cache (10 min).
CHANGES v1.1.4: _ATTRIB_RE. v1.1.3: fuzzy author. v1.1.x: pronoun resolution.
CREATED v1.0.0: Query planner + fast-path + plan_and_retrieve()
"""
import re
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from config import DATABASE_PATH, QUERY_PLANNER_MODEL
from utils.logging_utils import get_logger

logger = get_logger('query_planner')

_member_cache = {}  # {channel_id: (timestamp, [names])}; TTL=600s

_TIME_RE = re.compile(
    r'\b(yesterday|today|this (morning|afternoon|week)|'
    r'last (week|month|night|\d+ days?)|\d+ (days?|weeks?|months?) ago|'
    r'recently|earlier|just now)\b', re.IGNORECASE)
_EXIST_RE = re.compile(
    r'\b(did we (ever|already)|have we (ever )?(discussed|talked|mentioned|covered)|'
    r'has anyone|was .{0,20} (ever |discussed|mentioned)|'
    r'has .{0,20} (come up|been discussed))\b', re.IGNORECASE)
_ATTRIB_RE = re.compile(
    r'\bwho\s+(said|told|mentioned|guessed|asked|wrote|posted|suggested|noted|thought)\b',
    re.IGNORECASE)
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
            "content_query": {"type": "string",
                "description": "Topic to search for. Empty if query is purely about who/when."},
            "author": {"type": "array", "items": {"type": "string"},
                "description": "Participant names (exact from list). Empty if no filter."},
            "after": {"type": ["string", "null"],
                      "description": "ISO 8601 start time. Null if no filter."},
            "before": {"type": ["string", "null"],
                       "description": "ISO 8601 end time. Null if no filter."},
            "mode": {"type": "string",
                "enum": ["lookup", "summary", "existence", "attribution"],
                "description": "lookup=content. summary=overview. existence=did it occur. attribution=who said."},
        },
        "required": ["content_query", "mode"]
    }
}


def get_channel_members(channel_id):
    """Return distinct author names for channel. TTL-cached."""
    now = time.time()
    cached = _member_cache.get(channel_id)
    if cached and (now - cached[0]) < 600:
        return cached[1]
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT author_name FROM messages "
            "WHERE channel_id=? AND author_name IS NOT NULL",
            (channel_id,)).fetchall()
    finally:
        conn.close()
    members = [r[0] for r in rows if r[0]]
    _member_cache[channel_id] = (now, members)
    return members


def _is_known_author(name, channel_id):
    return any(name.lower() == m.split('#')[0].strip().lower()
               for m in get_channel_members(channel_id))


@dataclass
class QueryInfo:
    raw: str
    text: str
    author: Optional[str]


def extract_query_info(conversation_msgs, channel_id):
    """Extract last user message; validate author prefix against member list."""
    raw = next(
        (m["content"].strip() for m in reversed(conversation_msgs or [])
         if m.get("role") == "user" and m.get("content", "").strip()), None)
    if not raw:
        return None
    if ':' in raw:
        prefix, rest = raw.split(':', 1)
        if _is_known_author(prefix.strip(), channel_id) and rest.strip():
            return QueryInfo(raw=raw, text=rest.strip(), author=prefix.strip())
    return QueryInfo(raw=raw, text=raw, author=None)


def needs_query_planner(query_text, channel_id):
    """Return True if query contains metadata signals requiring the planner."""
    q = query_text.lower()
    q_words = set(re.findall(r'\b\w+\b', q))
    for name in get_channel_members(channel_id):
        clean = name.split('#')[0].strip().lower()
        if (len(clean) >= 3 and clean in q) or any(
                len(tok) >= 4 and tok in q_words
                for tok in re.findall(r'\b\w+\b', clean)):
            return True
    return bool(_TIME_RE.search(q) or _EXIST_RE.search(q)
                or _PRONOUN_RE.search(q) or _ATTRIB_RE.search(q))


def normalize_authors(intent, channel_id):
    """Normalize partial author names to full names; logs ambiguous matches."""
    members = get_channel_members(channel_id)
    normalized = []
    for partial in intent.get("author", []):
        matches = [m for m in members if partial.lower() in m.lower()]
        if not matches:
            logger.warning(f"No match for author '{partial}' in ch:{channel_id}")
        elif len(matches) > 1:
            logger.warning(f"Ambiguous author '{partial}' → {matches}; picking first")
        normalized.append(matches[0] if matches else partial)
    intent["author"] = normalized
    return intent


def run_query_planner(query_text, channel_id, recent_context=None, current_speaker=None):
    """Parse query into structured intent dict; returns None on failure."""
    import openai
    from config import OPENAI_API_KEY
    members = get_channel_members(channel_id)
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    system = (
        f"You are a query planner for a conversation memory system. "
        f"Current time: {now_iso}. Participants: {', '.join(members) or 'unknown'}.\n"
        "Rules: Resolve relative dates to ISO 8601. Match author names against the participant list exactly.\n"
        "Resolve pronouns (he/she/they) to a third party using recent context; exclude the current speaker."
        + (f" Current speaker: '{current_speaker}' — never resolve pronouns to them.\n" if current_speaker else "\n")
        + "mode=existence for 'did we ever/have we discussed'. mode=attribution for 'who said/was it X that'.\n"
        "mode=summary for broad overview. mode=lookup for all other queries.\n"
        "Leave author empty if not about a specific participant. Leave content_query empty if purely about who/when."
    )
    if recent_context:
        system += "\n\nRecent context:\n" + "\n".join(
            f"[{m.get('role','user')}] {m.get('content','')[:200]}"
            for m in recent_context)
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
        for k, v in [("author",[]),("after",None),("before",None),("content_query",""),("mode","lookup")]:
            intent.setdefault(k, v)
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
            if name.lower() != (current_speaker or "").lower() and re.search(
                    r'\b' + re.escape(tok) + r'\b', msg.get('content', '').lower()):
                return name
    return None


def run_planner_and_embed(query_info, channel_id, conversation_msgs):
    """Run planner + embedding in parallel. Returns (vec, path, ms, intent)."""
    from utils.embedding_context import embed_query_with_smart_context
    recent = [m for m in (conversation_msgs or [])[-6:]
              if m.get("role") in ("user", "assistant")][-5:]
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        pf = ex.submit(run_query_planner, query_info.text, channel_id,
                       recent, query_info.author)
        ef = ex.submit(embed_query_with_smart_context,
                       query_info.raw, channel_id, conversation_msgs)
        intent = pf.result()
        query_vec, embedding_path = ef.result()
    return query_vec, embedding_path, round((time.monotonic() - t0) * 1000), intent


def plan_and_retrieve(channel_id, conversation_msgs, budget, exclude_ids=None):
    """Layer 3 entry point. Returns (context_text, tokens, receipt, citation_map)."""
    from utils.context_retrieval import _retrieve_segment_context
    from utils.query_router import route_query

    _empty = ("", 0, {}, {})
    query_info = extract_query_info(conversation_msgs, channel_id)
    if not query_info:
        return _empty

    if not needs_query_planner(query_info.text, channel_id):
        return _retrieve_segment_context(
            channel_id, conversation_msgs, budget, exclude_ids=exclude_ids)

    query_vec, embedding_path, planner_ms, intent = run_planner_and_embed(
        query_info, channel_id, conversation_msgs)
    if query_vec is None:
        return _empty

    if intent is None:
        logger.debug(f"Planner failed ch:{channel_id} — falling back to RRF")
        return _retrieve_segment_context(
            channel_id, conversation_msgs, budget,
            exclude_ids=exclude_ids, query_vec=query_vec,
            embedding_path=embedding_path, query_text=query_info.text)

    recent_5 = [m for m in (conversation_msgs or [])[-6:]
                if m.get("role") in ("user", "assistant")][-5:]
    if not intent.get("author") and _PRONOUN_RE.search(query_info.text):
        ref = _resolve_pronoun_fallback(recent_5[:-1], channel_id, query_info.author)
        if ref:
            intent["author"] = [ref]

    intent = normalize_authors(intent, channel_id)
    recent_ids = {m["_msg_id"] for m in (conversation_msgs or []) if "_msg_id" in m}
    if exclude_ids:
        recent_ids = recent_ids | set(exclude_ids)

    return route_query(
        intent, query_vec, channel_id, budget,
        exclude_ids=recent_ids, embedding_path=embedding_path,
        query_text=query_info.text, planner_ms=planner_ms)
