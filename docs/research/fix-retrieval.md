# Stop chasing higher scores — fix the retrieval architecture instead

**Your biggest problem isn't the embeddings — it's querying against cluster centroids.** At 150 segments, centroid-based retrieval compresses your embedding space 10×, placing query targets at the geometric mean of diverse topics rather than near any individual topic. Combined with absolute-threshold filtering on scores that are naturally lower for multi-topic embeddings, this creates a system that works against itself. The fix is a stack of three changes that require roughly a day of implementation: query individual segment embeddings directly, add BM25 hybrid retrieval via SQLite FTS5, and replace your fixed threshold with top-K selection. These three changes alone should resolve the retrieval precision problem without touching your embedding or synthesis pipeline.

The deeper question — whether to decompose syntheses into atomic propositions — is worth doing as a second phase, but only after the architectural quick wins are in place. Here's the full analysis.

## The centroid bottleneck explains most of your score drop

Your current pipeline queries against **15 cluster centroids** rather than **150 individual segment embeddings**. This is the single largest contributor to low similarity scores, and the math makes it clear why.

A cluster centroid is the arithmetic mean of its member embeddings. When a cluster contains segments about database selection, deployment configuration, and API rate limiting, the centroid vector points toward a location in embedding space that is equidistant from all three topics — and therefore **close to none of them**. A query about "What database did we decide on?" must match against this diluted centroid rather than the focused segment that actually discusses database selection. Research on high-dimensional embedding spaces confirms this: vectors near the centroid of a distribution become "hubs" that score similarly for diverse queries, destroying discriminative power. This is formally described in recent work on centrality-driven hubness in embedding spaces.

The performance cost is entirely unnecessary at your scale. Computing cosine similarity against all 150 segments is a single matrix multiply: `scores = query_emb @ segment_embeddings.T`. In NumPy, this executes in **under 1 millisecond** on your 1GB VM. Inverted-file indexing with centroids exists for corpora of 100K–10M+ vectors; at 150 vectors, it adds complexity while removing precision.

**The fix**: Query all segment embeddings directly, then map top-scoring segments back to their parent clusters. This single change should recover a significant portion of the score gap and improve score discrimination between relevant and irrelevant results.

```python
# Replace centroid-based retrieval:
scores = [(seg_id, cosine_sim(query_emb, seg_emb)) 
          for seg_id, seg_emb in all_segments]
top_segments = sorted(scores, key=lambda x: x[1], reverse=True)[:10]
relevant_clusters = set(segment_to_cluster[s] for s, _ in top_segments)
```

## Your score drop is expected — threshold-based filtering is the real problem

The decline from **0.377 to 0.325** average top score is not a retrieval quality problem. It's a geometric consequence of embedding broader text units. When a segment synthesis covers three subtopics, the resulting vector is a weighted average of three semantic directions. Any single-topic query will have a larger angle to this averaged vector than to a focused single-topic embedding. This is well-documented: OpenAI community analyses of text-embedding-ada-002 (same architecture family as text-embedding-3-small) confirm that larger chunks produce **less discriminative cosine similarity distributions** — relevant and irrelevant chunks score closer together.

Your keyword recall improvement from **19% to 50%** proves the system is retrieving better content. The absolute scores dropped, but the ranking quality improved. The problem is that your threshold-based filtering (0.25 cutoff) was calibrated for the old score distribution and is now cutting into relevant results.

Three approaches fix this, in order of simplicity:

**Top-K retrieval** replaces thresholds entirely. Return the top 3–5 results regardless of absolute score. This is what virtually all production retrieval systems use (Azure AI Search, Elasticsearch, Pinecone). For 15 clusters, returning the top 3–5 is almost always correct. This requires about 5 minutes of code changes.

**Percentile-based thresholding** adapts automatically to the score distribution of each query. Instead of checking `score > 0.25`, compute the 75th percentile of all scores for that query and use it as the cutoff. This handles different query types gracefully — narrow queries produce steep score distributions with high top scores, while broad queries produce flatter distributions where the percentile threshold naturally lowers.

```python
scores = [cosine_sim(query_emb, seg_emb) for seg_emb in all_segments]
threshold = np.percentile(scores, 75)  # Top 25% of scores
# Or use score-gap detection: find the largest drop between adjacent scores
```

**Z-score normalization** computes `z = (score - mean) / std_dev` per query, returning results that are statistically unusual relative to the distribution. OpenSearch benchmarks show z-score normalization provides a **2.08% average increase in nDCG@10** over min-max normalization.

## SQLite FTS5 hybrid search adds the missing keyword signal

Dense embeddings capture semantic meaning but miss exact keyword matches that matter for conversational recall. When a user asks "What have we said about gorillas?", BM25 can match the word "gorillas" directly, while the embedding must rely on semantic proximity. Combining sparse (BM25) and dense retrieval improves **nDCG@10 by 10–15%** across the BEIR benchmark suite, with gains up to **+24%** on domain-specific datasets.

SQLite's FTS5 extension gives you production-quality BM25 with zero additional dependencies. It's built into SQLite, handles tokenization and indexing natively, and includes a `bm25()` scoring function with standard parameters (k1=1.2, b=0.75).

```sql
-- Create FTS5 table mirroring your syntheses
CREATE VIRTUAL TABLE syntheses_fts USING fts5(
    synthesis_text, 
    tokenize="porter unicode61"
);

-- Query with BM25 scoring
SELECT rowid, rank FROM syntheses_fts 
WHERE syntheses_fts MATCH ? ORDER BY rank LIMIT 20;
```

Merge the two result lists using **Reciprocal Rank Fusion (RRF)**, which is score-agnostic — it works on ranking positions only, so you never need to normalize BM25 scores against cosine similarity. The standard parameter k=60 works well for general retrieval; for your small result sets (15 clusters), k=10–15 gives stronger emphasis on top-ranked results.

```python
def rrf_fuse(bm25_ranked, dense_ranked, k=15, top_n=5):
    scores = {}
    for rank, doc_id in enumerate(bm25_ranked, 1):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    for rank, doc_id in enumerate(dense_ranked, 1):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
```

The AIngram project, which implements exactly this pattern (FTS5 + vector embeddings + RRF in a single SQLite file) for agent memory, achieves **95.5% correct session retrieval** in top-10 results on the LongMemEval benchmark.

## Proposition decomposition is the high-impact second phase

If the three architectural changes above don't fully resolve your precision needs, **proposition decomposition** directly attacks the root cause: multi-topic syntheses producing diluted embeddings. The technique, formalized in the Dense X Retrieval paper (Chen et al., EMNLP 2024), decomposes each text chunk into atomic, self-contained propositions before embedding each one separately.

A synthesis like *"The team decided on PostgreSQL for the database, agreed to deploy on GCP, and set rate limits at 100 req/min"* becomes three separate propositions:
- "The team decided to use PostgreSQL as the database."
- "The team agreed to deploy the application on Google Cloud Platform."
- "The team set API rate limits at 100 requests per minute."

Each proposition gets its own embedding, stored with a foreign key back to the parent synthesis. At query time, you search proposition embeddings (producing high cosine similarity for precise matches) and return the parent synthesis for full context. This is essentially a parent-child retrieval architecture.

**Benchmark results are strong**: Dense X Retrieval shows **+22–35% relative improvement in Recall@5** for unsupervised retrievers and +2.4–4.5% for supervised retrievers across five QA datasets. The improvement is largest on queries the retriever wasn't specifically trained for — exactly your situation with conversational data and a general-purpose embedding model.

**The decomposition prompt** (adapted from the LangChain propositional-retrieval template):

```
Decompose this conversation summary into independent, atomic facts. 
Each fact must:
1. Be a single, complete sentence expressing one claim or decision
2. Include all necessary context (replace "they/it/we" with specific names)
3. Be understandable without reading the original summary

Summary: {synthesis_text}
Return as JSON: {"propositions": ["fact1", "fact2", ...]}
```

**Cost estimate**: Using GPT-4o-mini at $0.15/M input tokens and $0.60/M output tokens, decomposing 150 syntheses averaging 200 tokens each = ~30K input tokens + ~45K output tokens ≈ **$0.03**. Embedding the resulting ~500–750 propositions with text-embedding-3-small at $0.02/M tokens ≈ **$0.0002**. Total: well under your $0.10 budget. The trade-off is storing 4–5× more embeddings (~750 vs 150), which is trivial in SQLite.

## What the conversational memory research says

Microsoft's **SeCom** (ICLR 2025) validates your segmentation approach but adds a critical step: **compress segments before embedding** using LLMLingua-2. Removing natural language redundancy (filler words, repetitive confirmations, hedging) concentrates the embedding vector on core semantic content. SeCom shows compression alone improves retrieval by **up to 9.46 GPT4Score points** on the LOCOMO benchmark. This is particularly relevant because your syntheses are LLM-generated text — LLMs tend to produce verbose output with redundant phrasing that dilutes embedding signal.

You could approximate this without LLMLingua-2 by adjusting your synthesis prompt to produce terser output:

```
Summarize this conversation segment as a dense list of factual claims.
Use minimal words. No filler phrases. No hedging language.
State each decision, preference, or fact in under 15 words.
```

**Mem0** (the most widely deployed memory system, used by tens of thousands of developers) takes the extraction-first approach further: it doesn't embed conversation segments at all. Instead, an LLM extracts **individual facts and preferences** as atomic memory units ("user prefers PostgreSQL," "team decided on GCP"), then embeds those. This naturally avoids multi-topic dilution. Mem0 achieves **0.148s p50 search latency** with **78% fewer input tokens** than full-context approaches.

**MemGAS** (ICLR 2026) introduces an entropy-based router that automatically selects the right retrieval granularity per query — keywords for narrow queries, full sessions for broad ones. While the full MemGAS pipeline is too complex for a solo developer, the insight is valuable: different queries benefit from different granularities. Your system could implement a lightweight version by checking if a query contains specific entities (use keyword/FTS5 matching) vs. asking a broad thematic question (use embedding similarity).

## Ranked recommendations for your system

Here are the approaches ranked by expected impact relative to implementation effort, given your specific constraints (solo developer, 1GB VM, SQLite, OpenAI embeddings, ~150 segments):

**Phase 1 — Architectural fixes (implement first, ~4 hours total):**

1. **Query individual segment embeddings instead of centroids.** Impact: high. Effort: 30 minutes. This should immediately improve top scores and score discrimination.

2. **Replace fixed threshold with top-K selection.** Impact: medium-high. Effort: 15 minutes. Eliminates the threshold calibration problem entirely.

3. **Add SQLite FTS5 hybrid search with RRF fusion.** Impact: high. Effort: 2–3 hours. Adds keyword matching that embeddings miss, particularly for named entities and specific terms. No new dependencies.

**Phase 2 — Embedding improvements (implement if Phase 1 is insufficient, ~6 hours total):**

4. **Decompose syntheses into atomic propositions.** Impact: high. Effort: 3–4 hours. Directly solves multi-topic dilution. Cost: ~$0.03 per rebuild. Store propositions with parent synthesis foreign key.

5. **Tighten synthesis prompts for density.** Impact: medium. Effort: 1 hour. Produce terser, more factual syntheses that embed more precisely. Free — just prompt engineering.

**Phase 3 — Precision refinement (implement if retrieval quality still needs improvement):**

6. **Add lightweight re-ranking with FlashRank.** Impact: medium. Effort: 1–2 hours. A **4MB** ONNX-based cross-encoder model (ms-marco-TinyBERT-L-2-v2) that runs in **<20ms** on CPU with no PyTorch dependency. Retrieve top 20 segments via hybrid search, rerank, return top 5. Alternatively, use GPT-4o-mini as a reranker at ~$0.001/query for deeper conversational understanding.

7. **Extract and store keyword tags per segment.** Impact: medium. Effort: 2 hours. Have your synthesis LLM also output 3–5 keyword tags per segment. Store as a comma-separated column. Use for pre-filtering or as an additional RRF signal.

## What "just lower the threshold" gets right and wrong

The instinct is partially correct: your current 0.25 threshold was calibrated for single-message embeddings and needs adjustment for segment-level embeddings. But simply lowering it to 0.20 creates a different problem — you'll retrieve more noise alongside more signal. The better version of this insight is: **abandon absolute thresholds entirely in favor of top-K retrieval with optional score-gap detection.** Return the top 3–5 results always, and if you need a relevance cutoff, look for the largest gap in the sorted score list (e.g., scores of [0.42, 0.38, 0.35, 0.21, 0.18] have a natural break between 0.35 and 0.21).

The combination of individual segment retrieval (not centroids), hybrid BM25+dense search, and top-K selection should bring your effective retrieval quality well above the current baseline — likely achieving both the higher keyword recall of your segment-based system and score discrimination comparable to your old message-based system. Proposition decomposition is the strongest additional lever if these architectural changes aren't sufficient, and at ~$0.03 per rebuild it's well within budget. The full stack — direct segment retrieval + FTS5 hybrid + RRF + top-K + proposition decomposition — is implementable in a weekend and maintainable by one person indefinitely.
