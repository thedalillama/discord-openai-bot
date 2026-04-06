# utils/citation_utils.py
# Version 1.0.0
"""
Citation validation and footer building for citation-backed responses (SOW v5.9.0).

CREATED v1.0.0:
- strip_hallucinated_citations() — remove [N] from response where N not in citation_map
- build_citation_footer()        — build Sources: footer for cited messages
- apply_citations()              — combined: strip + footer, returns (main, footer)

citation_map format: {int: {"author": str, "content": str, "date": str}}
"""
import re
from utils.logging_utils import get_logger

logger = get_logger('citation_utils')


def strip_hallucinated_citations(text, citation_map):
    """Remove [N] markers from text where N is not a real citation number."""
    def _replace(m):
        return m.group(0) if int(m.group(1)) in citation_map else ''
    return re.sub(r'\[(\d+)\]', _replace, text)


def build_citation_footer(response_text, citation_map):
    """Build a Sources footer for citations used in response_text.

    Caps at 5 shown sources to prevent bloat. Returns (footer_str, total_cited).
    footer_str is empty string if no valid citations found.
    """
    cited_nums = sorted({int(n) for n in re.findall(r'\[(\d+)\]', response_text)
                         if int(n) in citation_map})
    if not cited_nums:
        return "", 0

    shown = cited_nums[:5]
    lines = ["\n**Sources:**"]
    for n in shown:
        src = citation_map[n]
        date = (src.get("date") or "")[:10]
        author = src.get("author", "?")
        content = src.get("content") or ""
        if len(content) > 100:
            content = content[:100] + "…"
        lines.append(f'[{n}] {author} ({date}): "{content}"')
    if len(cited_nums) > 5:
        lines.append(f"... and {len(cited_nums) - 5} more sources")

    return "\n".join(lines), len(cited_nums)


def apply_citations(text, citation_map):
    """Strip hallucinated citations, build and attach footer.

    If response + footer fits within 1950 chars, footer is appended to main text
    (returns empty footer string). Otherwise returns them separately so caller
    can send footer as a follow-up message.

    Returns:
        (main_text, footer_str) — footer_str is empty if no citations or already appended.
    """
    if not citation_map or not text:
        return text, ""

    text = strip_hallucinated_citations(text, citation_map)
    footer, count = build_citation_footer(text, citation_map)

    if not footer:
        return text, ""

    logger.debug(f"Citation footer: {count} sources cited")

    if len(text) + len(footer) <= 1950:
        return text + footer, ""

    return text, footer
