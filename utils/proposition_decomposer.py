# utils/proposition_decomposer.py
# Version 1.1.0
"""
GPT-4o-mini proposition decomposer for segment syntheses (SOW v6.3.0).

Breaks each segment synthesis into 3-5 atomic, self-contained claims.
Each claim resolves pronouns (replaces "they/we/the team" with participant
names) so it can be understood without the original synthesis.

Runs during !summary create after segmentation + FTS5 population, before
segment clustering. Phase failure does NOT abort the pipeline — degrades
to two-signal retrieval (dense + BM25, same as v6.2.0).

Functions:
- decompose_syntheses(segments, batch_size, progress_fn) — GPT-4o-mini batch
- run_proposition_phase(channel_id, progress_fn) — orchestrate full phase

CHANGES v1.1.0: Retry proposition embedding once after 5s on transient error
CREATED v1.0.0: Proposition decomposition pipeline (SOW v6.3.0)
"""
import os
import asyncio
import json
from utils.logging_utils import get_logger

logger = get_logger('proposition_decomposer')

DECOMPOSITION_SYSTEM_PROMPT = """\
Decompose each labeled conversation summary into independent, atomic facts.
Each fact must:
1. Be a single, complete sentence expressing one claim or decision
2. Replace all pronouns — use participant names instead of "they/we/the team"
3. Be understandable without reading the original summary

Return ONLY valid JSON:
{"results": [{"id": <number>, "propositions": ["fact1", "fact2", ...]}, ...]}
Produce 3-5 propositions per summary. Skip items with no decomposable claims."""


def _call_decompose(items_text):
    """Call GPT-4o-mini with JSON mode. Returns parsed results list or []."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DECOMPOSITION_SYSTEM_PROMPT},
            {"role": "user",   "content": items_text},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=2048,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw).get("results", [])


async def decompose_syntheses(segments, batch_size=10, progress_fn=None):
    """Batch-decompose segment syntheses into atomic propositions.

    Args:
        segments: list of (segment_id, synthesis) tuples
        batch_size: syntheses per GPT-4o-mini call (default 10)
        progress_fn: optional async progress callback

    Returns:
        list of (segment_id, [proposition_strings]) tuples.
        Segments where decomposition fails are skipped silently.
    """
    results = []
    for batch_start in range(0, len(segments), batch_size):
        batch = segments[batch_start:batch_start + batch_size]
        items = "\n\n".join(
            f"[{i + 1}] {synthesis}"
            for i, (_, synthesis) in enumerate(batch)
            if synthesis and synthesis.strip()
        )
        if not items.strip():
            continue
        try:
            raw_results = await asyncio.to_thread(_call_decompose, items)
            by_id = {r.get("id"): r.get("propositions", [])
                     for r in raw_results if isinstance(r, dict)}
            for i, (seg_id, _) in enumerate(batch):
                props = [p for p in by_id.get(i + 1, []) if isinstance(p, str)]
                if props:
                    results.append((seg_id, props))
        except Exception as e:
            batch_num = batch_start // batch_size + 1
            logger.warning(f"Decomposition batch {batch_num} failed: {e}")
        if progress_fn:
            done = min(batch_start + batch_size, len(segments))
            await progress_fn(
                f"Decomposing propositions: {done}/{len(segments)} segments")
    return results


async def run_proposition_phase(channel_id, progress_fn=None):
    """Orchestrate full proposition phase: decompose → store → embed.

    Returns proposition count stored; 0 on failure. Does not raise —
    caller should log and continue (degrades to dense+BM25 retrieval).
    """
    import sqlite3
    from config import DATABASE_PATH, PROPOSITION_BATCH_SIZE
    from utils.proposition_store import (
        store_propositions, clear_channel_propositions,
        store_proposition_embedding, get_proposition_count)
    from utils.embedding_store import embed_texts_batch
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        rows = conn.execute(
            "SELECT id, synthesis FROM segments WHERE channel_id=?",
            (channel_id,)).fetchall()
        conn.close()
        if not rows:
            logger.warning(f"No segments for proposition phase ch:{channel_id}")
            return 0
        if progress_fn:
            await progress_fn(
                f"Decomposing {len(rows)} segments into propositions...")
        clear_channel_propositions(channel_id)
        decomposed = await decompose_syntheses(
            rows, batch_size=PROPOSITION_BATCH_SIZE, progress_fn=progress_fn)
        prop_texts, prop_ids_flat = [], []
        for seg_id, props in decomposed:
            new_ids = store_propositions(channel_id, seg_id, props)
            prop_ids_flat.extend(new_ids)
            prop_texts.extend(props)
        if not prop_texts:
            logger.warning(f"No propositions produced ch:{channel_id}")
            return 0
        if progress_fn:
            await progress_fn(f"Embedding {len(prop_texts)} propositions...")
        emb_results = None
        for attempt in range(2):
            try:
                emb_results = await asyncio.to_thread(
                    embed_texts_batch, prop_texts, 1000)
                break
            except Exception as emb_err:
                if attempt == 0:
                    logger.warning(
                        f"Proposition embedding attempt 1 failed, "
                        f"retrying in 5s: {emb_err}")
                    await asyncio.sleep(5)
                else:
                    logger.error(
                        f"Proposition embedding failed after 2 attempts "
                        f"ch:{channel_id}: {emb_err}")
                    return 0
        for idx, vec in (emb_results or []):
            if idx < len(prop_ids_flat):
                await asyncio.to_thread(
                    store_proposition_embedding, prop_ids_flat[idx], vec)
        total = get_proposition_count(channel_id)
        logger.info(
            f"Proposition phase: {total} props from "
            f"{len(rows)} segs ch:{channel_id}")
        if progress_fn:
            await progress_fn(f"Propositions ready: {total} total")
        return total
    except Exception as e:
        logger.error(f"Proposition phase failed ch:{channel_id}: {e}")
        return 0
