# MOON Memory Semantic Search
# Adds embedding-vector-like semantic recall on top of the existing SQLite memory.
#
# Professional agents (MemGPT, Leta, GPT-4 with long context) maintain a
# searchable memory layer. MOON already has SQLite FTS via sqlite_fts_search.
# This module adds a lightweight semantic layer using:
#  - TF-IDF-style keyword weighting over memory entries
#  - Cosine-similarity scoring against the query
#  - Hybrid rank: semantic score + FTS score combined
#
# No external embedding model required — operates on token-frequency vectors
# built from memory entry text. Good enough for semantic recall without
# pulling in a heavy model.

import re as _re
import math as _math
from collections import Counter as _Counter
from typing import Any

from agent.engine import _eng

# ---------------------------------------------------------------------------
# Tokenisation and vectorisation helpers
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "but", "and",
    "or", "if", "while", "although", "until", "unless", "about", "against",
    "it", "its", "this", "that", "these", "those", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "him", "her", "they", "them",
    "what", "which", "who", "whom", "whose", "am", "at", "by", "for",
    "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "and", "but", "or", "nor", "so", "yet", "both",
    "either", "neither", "each", "every", "all", "any", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "than", "too", "very", "just", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against",
    "between", "into", "through", "during", "before", "after", "above",
    "below", "to", "from", "up", "down", "in", "out", "on", "off",
    "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both",
    "each", "every", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "because", "as", "until", "while", "it", "its",
    "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "she", "him", "her", "they", "them", "what",
    "which", "who", "whom", "whose", "am", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can",
    "need", "dare", "ought", "the", "and", "but", "or", "if", "because",
    "as", "until", "while", "of", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "in", "out", "on",
    "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both",
    "each", "every", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "about", "above", "after", "again", "against",
    "all", "am", "an", "and", "any", "are", "as", "at", "be", "because",
    "been", "before", "being", "below", "between", "both", "but", "by",
    "could", "did", "do", "does", "doing", "don", "down", "during",
    "each", "few", "for", "from", "further", "had", "has", "have", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "would",
    "you", "your", "yours", "yourself", "yourselves",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace, filter stopwords."""
    text = text.lower()
    text = _re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in _STOPWORDS and len(t) > 1]
    return tokens


def _tf_vector(tokens: list[str]) -> dict[str, float]:
    """Term-frequency vector (raw counts, not normalized)."""
    return dict(_Counter(tokens))


def _idf(vectors: list[dict[str, float]]) -> dict[str, float]:
    """Compute inverse document frequency across a corpus of TF vectors."""
    n = max(len(vectors), 1)
    doc_count: dict[str, int] = {}
    for v in vectors:
        for term in v:
            doc_count[term] = doc_count.get(term, 0) + 1
    return {term: _math.log(n / max(c, 1)) for term, c in doc_count.items()}


def _cosine_similarity(v1: dict[str, float], v2: dict[str, float],
                        idf: dict[str, float] | None = None) -> float:
    """Cosine similarity between two TF (or TF-IDF) vectors."""
    if idf:
        v1 = {t: c * idf.get(t, 0) for t, c in v1.items()}
        v2 = {t: c * idf.get(t, 0) for t, c in v2.items()}
    dot = sum(v1.get(t, 0) * v2.get(t, 0) for t in set(v1) | set(v2))
    norm1 = _math.sqrt(sum(c * c for c in v1.values()))
    norm2 = _math.sqrt(sum(c * c for c in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


# ---------------------------------------------------------------------------
# Corpus management — build and cache TF-IDF vectors from memory
# ---------------------------------------------------------------------------

_corpus_vectors: list[dict[str, float]] = []
_corpus_entries: list[dict[str, Any]] = []
_corpus_idf: dict[str, float] = {}
_corpus_dirty = True


def _rebuild_corpus():
    """Pull all memory entries from the engine and rebuild semantic vectors."""
    global _corpus_vectors, _corpus_entries, _corpus_idf, _corpus_dirty
    try:
        from agent.memory import get_all_entries
        entries = get_all_entries()
    except Exception:
        entries = []
    _corpus_entries = entries
    _corpus_vectors = []
    for e in entries:
        data = e.get("data", {})
        text = ""
        if isinstance(data, dict):
            text = " ".join(str(v) for v in data.values() if isinstance(v, str))
        elif isinstance(data, str):
            text = data
        elif isinstance(data, (list, tuple)):
            text = " ".join(str(x) for x in data if isinstance(x, str))
        tokens = _tokenize(text)
        if tokens:
            _corpus_vectors.append(_tf_vector(tokens))
        else:
            _corpus_vectors.append({})
    _corpus_idf = _idf(_corpus_vectors) if _corpus_vectors else {}
    _corpus_dirty = False


def _ensure_corpus():
    global _corpus_dirty
    if _corpus_dirty or not _corpus_vectors:
        _rebuild_corpus()


# ---------------------------------------------------------------------------
# Main semantic search tool
# ---------------------------------------------------------------------------

async def _tool_memory_vector_search(args: dict) -> dict:
    """Semantic search over MOON's long-term memory using TF-IDF cosine similarity.

    Combines semantic ranking with the existing SQLite FTS (sqlite_fts_search)
    for a hybrid recall result.

    Usage:
      memory_vector_search(query="what did we discuss about the security audit")
      memory_vector_search(query="python script", top_k=5, hybrid=True)
      memory_vector_search(query="deployment", top_k=3, semantic_only=True)

    Returns ranked entries with semantic score, FTS score (if hybrid), and snippet.
    """
    query = args.get("query", "").strip()
    if not query:
        return {"error": "query is required"}

    top_k = int(args.get("top_k", 10))
    hybrid = args.get("hybrid", True)

    _ensure_corpus()
    query_tokens = _tokenize(query)
    if not query_tokens:
        return {"error": "query too generic (no meaningful tokens)", "query": query}

    query_vec = _tf_vector(query_tokens)

    # Semantic scores
    scored: list[tuple[float, dict]] = []
    for i, entry in enumerate(_corpus_entries):
        vec = _corpus_vectors[i] if i < len(_corpus_vectors) else {}
        if not vec:
            continue
        sim = _cosine_similarity(query_vec, vec, _corpus_idf)
        if sim > 0:
            scored.append((sim, entry))

    scored.sort(key=lambda x: -x[0])
    top_semantic = scored[:top_k * 2]  # fetch extra for hybrid filtering

    # Hybrid: also run FTS and merge
    results: list[dict] = []
    seen_ids: set[int] = set()

    if hybrid:
        try:
            from agent.engine import default_engine as _eng_inst
            fts_result = await _eng_inst.run_tool("sqlite_fts_search", {"query": query, "limit": top_k})
            fts_entries = fts_result.get("results", [])
            fts_scores: dict[int, float] = {}
            for item in fts_entries:
                eid = item.get("id")
                if eid is not None:
                    fts_scores[eid] = item.get("rank", 1.0)
        except Exception:
            fts_scores = {}

        for sim, entry in top_semantic[:top_k]:
            eid = entry.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            fts_score = fts_scores.get(eid, 0.0)
            # Blend: semantic dominates, FTS adds signal
            blended = round(sim * 0.7 + (1.0 / (1.0 + fts_score)) * 0.3, 4) if fts_score else sim
            results.append({
                "id": eid,
                "session_id": entry.get("session_id", ""),
                "timestamp": entry.get("timestamp", ""),
                "data": entry.get("data", {}),
                "semantic_score": round(sim, 4),
                "fts_score": round(fts_score, 4) if fts_score else None,
                "hybrid_score": blended,
                "snippet": _strip_data_to_snippet(entry.get("data", {})),
                "match_type": "semantic" if not fts_score else "hybrid",
            })
    else:
        for sim, entry in top_semantic[:top_k]:
            eid = entry.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            results.append({
                "id": eid,
                "session_id": entry.get("session_id", ""),
                "timestamp": entry.get("timestamp", ""),
                "data": entry.get("data", {}),
                "semantic_score": round(sim, 4),
                "hybrid_score": round(sim, 4),
                "snippet": _strip_data_to_snippet(entry.get("data", {})),
                "match_type": "semantic",
            })

    results.sort(key=lambda r: -r.get("hybrid_score", r.get("semantic_score", 0)))
    return {
        "query": query,
        "results": results[:top_k],
        "total_matches": len(results),
        "method": "hybrid tf-idf cosine" if hybrid else "semantic tf-idf cosine",
        "corpus_size": len(_corpus_entries),
        "query_tokens": query_tokens,
    }


def _strip_data_to_snippet(data: Any) -> str:
    """Extract a short human-readable snippet from a memory data field."""
    if isinstance(data, str):
        return data[:200]
    if isinstance(data, dict):
        parts = [str(v)[:100] for v in data.values() if isinstance(v, str)]
        return " | ".join(parts)[:200]
    return str(data)[:200]


# ---------------------------------------------------------------------------
# Memory stats — how many entries, corpus coverage, etc.
# ---------------------------------------------------------------------------

async def _tool_memory_stats(args: dict) -> dict:
    """Report on the memory corpus: entry count, semantic coverage, top terms."""
    _ensure_corpus()
    from agent.memory import get_all_entries
    try:
        all_entries = get_all_entries()
    except Exception:
        all_entries = []
    total = len(all_entries)
    with_text = sum(1 for e in all_entries if _tokenize(_strip_data_to_snippet(e.get("data", {}))))
    top_terms: dict[str, int] = {}
    for vec in _corpus_vectors:
        for term, count in vec.items():
            top_terms[term] = top_terms.get(term, 0) + count
    sorted_terms = sorted(top_terms.items(), key=lambda x: -x[1])[:20]
    return {
        "total_entries": total,
        "entries_with_text": with_text,
        "semantic_corpus_size": len(_corpus_vectors),
        "unique_terms": len(top_terms),
        "top_terms": [{"term": t, "count": c} for t, c in sorted_terms],
        "idf_coverage": len(_corpus_idf),
    }
