# Stop Embedding Messages Alone: Context Is the Fix

**The single most important finding from this research is that no production system or academic approach embeds short conversational messages in isolation.** Every system that successfully extracts meaning from chat — commercial products like Gong, Otter.ai, and Slack AI; academic systems benchmarked on IRC and meeting corpora; open-source clustering frameworks — either adds surrounding context before embedding or changes the embedding unit from individual messages to conversation segments. The good news: the minimum viable fix is roughly 20 lines of Python, and it addresses the core failure mode directly.

This report synthesizes findings from academic NLP literature (ACL, EMNLP, SIGIR, NAACL), commercial conversation intelligence products, and open-source implementations. The problem you describe — short replies clustering together as noise, decisions vanishing between Q&A pairs — is well-studied and has validated solutions at multiple complexity levels.

---

## Every production system embeds larger units, not single utterances

A survey of major conversation intelligence products reveals a near-universal architecture: **aggregate first, then analyze**. Otter.ai, Microsoft Teams Copilot, Zoom AI Companion, Google Meet, and Fireflies.ai all operate on full transcripts or large topical segments — never individual utterances — for summarization and decision detection. They capture audio, run speech-to-text, then pass the complete transcript (or semantically chunked segments of **1,500–3,000 tokens**) to LLMs with structured extraction prompts.

The one notable exception is **Gong.io**, which embeds individual sentences as **768-dimensional vectors** stored in Pinecone (billions of vectors total). But Gong uses sentence-level embedding exclusively for its Smart Trackers feature — cross-conversation concept detection ("find all mentions of competitor X across 10,000 calls"). For summarization and decision extraction, Gong still processes full transcripts. This distinction matters: **sentence-level embedding works for retrieval across conversations, but fails for understanding within conversations**.

Google Meet's decision detection is the most sophisticated found: it categorizes outcomes as **Aligned, Needs Further Discussion, Disagreed, or Shelved** — a taxonomy that requires multi-turn analysis of agreement patterns, not keyword extraction. This confirms that decision detection fundamentally requires processing conversational sequences, not individual messages.

For chat-specific tools, Slack AI operates on full channel histories or complete threads. Discord's native AI summary feature (built with OpenAI) processes entire channel conversations. Third-party summarizers built with Zapier or n8n all follow the same pattern: fetch all thread messages via API → format the complete thread → send to LLM. **No chat summarization tool found embeds individual messages for topic extraction.**

---

## What the academic literature says about async chat specifically

The academic NLP community has studied this problem extensively, and the findings directly explain why your pipeline struggles. Three lines of research are particularly relevant.

**Asynchronous chat is structurally different from meetings or documents.** Joty, Carenini, and Ng's foundational 2014 work on topic segmentation in asynchronous conversations demonstrated that standard sequential segmentation methods (like TextTiling's LCSeg) perform poorly on async chat because **topics interleave rather than proceeding sequentially**. In a Discord channel, someone might ask about PostgreSQL, someone else responds about deployment, a third person circles back to the database question, and meanwhile a side conversation about lunch is happening. Linear segmentation assumes topics occur in blocks — async chat violates this assumption. Joty et al. showed that graph-based methods modeling conversation structure significantly outperform linear approaches.

**Context-dependent embeddings dramatically outperform context-free ones.** Amazon's Alexa Prize research (Kim et al., IEEE SLT) demonstrated that adding prior-turn information to utterance embeddings improved topic classification accuracy from **55% to 74%** — a 35% relative improvement on 100,000+ annotated utterances. Their approach was straightforward: a Deep Averaging Network that averages embeddings of the 5 prior turns into a summary vector appended to the current utterance embedding. Pereira et al. (WASSA 2023) confirmed this with RoBERTa: feeding previous conversational turns alongside the target utterance produced context-dependent embeddings that significantly improved emotion recognition. The optimal context window varied by task but **including any context consistently beat no context**.

**Decisions emerge from structured sub-dialogues, not single utterances.** Fernández, Frampton, Ehlen, Purver, and Peters (SIGdial 2008) modeled decision-making in multi-party dialogue and found that decisions consist of distinct phases: **issue-raising → discussion → resolution proposal → agreement**. Their structured Decision-Related Dialogue Acts (DDAs) approach outperformed flat annotation methods. Bui and Peters (ACL 2010) raised decision detection F1 to **0.80** using hierarchical graphical models that captured these phases. This directly explains your PostgreSQL example: the decision exists in the exchange pattern, not in any individual message.

**Conversation disentanglement is a prerequisite for async chat analysis.** Kummerfeld et al. (ACL 2019) created the definitive IRC disentanglement dataset (77,563 annotated messages) and showed that the first step for multi-party chat understanding is identifying which messages belong to the same conversational thread. Recent work (2024/2025) using fine-tuned LLMs for reply-to link prediction achieves **0.90 Shen F-score** even on out-of-domain Discord developer chats. Since Discord already provides `reply_to_message_id` for some messages, you have partial thread structure for free.

---

## The minimum viable change: prepend context before embedding

The research converges on a clear recommendation for the simplest high-impact change. **Prepend 3–5 previous messages as context before embedding each message.** This takes roughly 20 lines of code, increases embedding cost negligibly, and directly addresses the core failure mode.

```python
def build_contextual_text(messages, index, window_size=3):
    start = max(0, index - window_size)
    context = messages[start:index]
    current = messages[index]
    
    if context:
        context_str = " | ".join(
            f"{m['author']}: {m['content']}" for m in context
        )
        return f"[Previous: {context_str}] {current['author']}: {current['content']}"
    return f"{current['author']}: {current['content']}"
```

With this change, "Yes, let's go with that" no longer embeds as a generic affirmation — it embeds as a response to "Should we use PostgreSQL?" and lands in the database discussion cluster. "What about the cost?" embeds with the preceding discussion about whatever "the cost" refers to. The embedding model can now see the referent.

**Cost impact is minimal.** With 3-message context prepend, token count per embedding increases roughly 3–5×. At OpenAI's $0.02 per million tokens for `text-embedding-3-small`, embedding 100K messages at ~60 tokens each costs **$0.12** (vs. $0.04 without context). Using the Batch API cuts this to $0.06. This is functionally free.

**An even stronger variant exists**: Anthropic's Contextual Retrieval technique (September 2024) uses an LLM to generate a brief explanatory context for each chunk before embedding. Their benchmarks showed a **35% reduction in retrieval failure** with contextual embeddings alone, and **49%** when combined with BM25. For budget-conscious setups, this adds ~$0.50–2.00 per 100K messages using GPT-4.1-mini or Claude Haiku with prompt caching. This is the "next step up" if prepending raw messages isn't sufficient.

You should also **exploit reply chains when available**. Discord's `reply_to_message_id` gives you explicit conversational structure. When a message is a reply, prepend the replied-to message (and its context) instead of just the N chronologically previous messages. This handles cases where a reply references a message from 20 messages ago, outside the sliding window.

---

## The architecturally superior approach: segment first, then embed

If you want to move beyond the minimum viable change, the highest-impact architectural improvement is to **change the unit of embedding from individual messages to conversation segments**. Instead of embedding 2,000 messages and clustering 2,000 vectors, segment the conversation into 50–200 topical chunks and embed those. Each embedding now represents a coherent conversational exchange rather than an isolated utterance.

The simplest segmentation method is **time-gap segmentation**: split the conversation whenever the gap between consecutive messages exceeds a threshold (e.g., 30 minutes). This is roughly 15 lines of code and works surprisingly well for Discord, where topic shifts often coincide with activity gaps. It naturally handles short follow-ups — "Agreed" becomes part of the segment containing the statement it agrees with.

A more sophisticated option is **embedding-similarity segmentation** (a neural variant of TextTiling). Embed each message, compute cosine similarity between consecutive messages, and place topic boundaries where similarity drops sharply. The Dial-START system (Gao et al., SIGIR 2023) achieves state-of-the-art unsupervised topic segmentation using contrastive learning on unlabeled dialogue data. The open-source `topic_segmenter` library (GitHub: walter-erquinigo/topic_segmenter) implements chat-specific segmentation that explicitly handles "reply objects" — short agreement/disagreement messages that carry no standalone meaning — by attaching them to the preceding topic.

The segment-then-embed approach has three practical advantages over context-prepended individual message embedding:

- **Reduces API calls and cost** (50–200 segment embeddings vs. 2,000 message embeddings)
- **Produces more meaningful clusters** (each vector represents a complete conversational exchange)
- **Naturally captures decisions** (the full Q&A exchange is one segment, so the decision is preserved)

The SeCom paper (2025) provides direct empirical evidence: topical segmentation before embedding **outperforms both turn-level and session-level approaches** for memory retrieval accuracy and semantic quality on the LOCOMO and Long-MT-Bench+ benchmarks.

For your system, a practical hybrid approach would combine both: use time-gap segmentation as the primary unit for topic clustering, but maintain context-prepended individual message embeddings for fine-grained retrieval when your LLM summarizer needs to find specific messages within a cluster.

---

## No specialized conversational embedding model beats general-purpose models with context

A perhaps surprising finding: **there is no production-ready conversational embedding model that clearly outperforms general-purpose models when context is properly provided**. TOD-BERT (pre-trained on task-oriented dialogue) and ConveRT (Google/PolyAI's dual-encoder for conversations) showed improvements on specific benchmarks, but TOD-BERT is trained on customer service dialogues that don't resemble Discord chat, ConveRT isn't publicly available as a standard model, and an attempt to create DialogueSentenceBERT "eventually failed" — performances were often lower than vanilla BERT.

The practical recommendation is to **keep using a general-purpose embedding model but enrich the input**. If you want to reduce costs, **nomic-embed-text-v1.5** is the strongest local alternative: 137M parameters, Apache 2.0 licensed, runs locally via Ollama, and outperforms `text-embedding-3-small` on MTEB benchmarks. Critically, it has an **8,192-token context window** (vs. 512 for the popular all-MiniLM-L6-v2), which is essential when prepending conversational context. Switching to nomic-embed-text locally eliminates embedding API costs entirely.

One framework upgrade worth considering: **BERTopic** (Grootendorst, 2022) uses the exact same pipeline you have — Sentence Transformers → UMAP → HDBSCAN — but adds c-TF-IDF topic representations, LLM-based topic labeling, and support for pre-computed embeddings. You can pass context-augmented embeddings for clustering while using original message text for topic word extraction. It's a mature, widely-used library that would replace your raw UMAP + HDBSCAN code with a more feature-rich version of the same approach.

---

## Approaches you may not have considered

Several techniques surfaced during research that address aspects of the problem beyond embedding quality.

**Coreference resolution as preprocessing.** The problem of "the other one," "it," and "that" is fundamentally a coreference resolution problem, and off-the-shelf tools exist. FastCoref and spaCy's experimental CoreferenceResolver can resolve pronouns to their antecedents before embedding. An LLM-based approach is even simpler: prompt a cheap model to rewrite short messages with explicit referents ("No, the other one" → "No, use PostgreSQL instead of Redis"). This preprocessing makes every downstream step more effective.

**Graph-based clustering on conversation structure.** Instead of (or in addition to) embedding-based clustering, model your conversation as a graph where nodes are messages and edges represent reply relationships, temporal proximity, @-mentions, or shared entities. Apply community detection (Louvain, Leiden) to find natural topic clusters. This captures structural relationships that text embeddings miss entirely — two messages might be semantically dissimilar but structurally connected through a reply chain. Recent work combining LLM-predicted reply-to links with graph-based clustering achieves 0.90 F-score on Discord data.

**Anthropic's Clio architecture for conversation clustering at scale.** Clio (December 2024) processes millions of conversations through LLM facet extraction → embedding → k-means clustering → hierarchical tree organization → LLM cluster summarization. An open-source reimplementation called **OpenClio** is available on GitHub and runs with local LLMs via vLLM. This is essentially a production-validated version of your pipeline, designed for conversation data.

**Multi-representation indexing.** Store multiple embeddings per message: the raw message, the message with context window, and a segment-level summary embedding. Different representations serve different retrieval needs. This is more storage but gives the LLM summarizer richer material to work with.

---

## Recommended implementation roadmap

Based on confidence levels from benchmarks, production validation, and implementation complexity, here is a prioritized path from minimum viable change to comprehensive solution.

| Priority | Change | Effort | Expected Impact | Confidence |
|----------|--------|--------|----------------|------------|
| **1** | Prepend 3–5 previous messages before embedding | Hours | High — directly fixes short-message problem | Very high (validated by Amazon/Alexa, Anthropic pattern) |
| **2** | Exploit `reply_to_message_id` to reconstruct reply chains for context | Hours | High for threaded messages | High (structural signal, no ML needed) |
| **3** | Add time-gap segmentation for topic-level clustering | Hours | High — changes embedding unit to conversation segments | High (standard NLP technique) |
| **4** | Switch to BERTopic framework | Hours | Medium — better topic representation and labeling | Very high (widely used, same underlying pipeline) |
| **5** | Switch to nomic-embed-text-v1.5 locally | 1 day | Medium quality + eliminates API cost | High (MTEB benchmarks, 8K context window) |
| **6** | Add LLM contextual expansion (Anthropic pattern) | 1 day | Very high (35–49% retrieval improvement) | Very high (Anthropic benchmarks, production use) |
| **7** | Coreference resolution preprocessing | 1–2 days | Medium — fixes pronoun/reference problem | Medium (tools exist but dialogue-specific accuracy varies) |
| **8** | Graph-based conversation modeling | 1–2 weeks | High for multi-thread channels | Medium-high (academic validation, more complex) |

## Conclusion

The core insight is deceptively simple: **your embedding unit is wrong, not your embedding model**. Short messages are not defective documents that need better embeddings — they are fragments of conversations that need their conversational context restored before any embedding model can represent them meaningfully. The academic literature, commercial products, and open-source tools all converge on this conclusion from different directions.

Start with context prepending (priority 1–2). If your topic clusters improve but you want better decision capture, add time-gap segmentation to change the clustering unit from messages to conversation segments (priority 3). These three changes — context prepending, reply chain exploitation, and time-gap segmentation — collectively address every failure mode in your original examples, cost almost nothing to implement, and require no new infrastructure. Everything beyond that is optimization.
