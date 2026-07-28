"""
Octron Memory System — V4 Safe Drop-In
Preserves function names/signatures from V3 while improving retrieval quality.
"""

import uuid
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Optional

import ollama
from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, VectorParams


# === Config ===
client = QdrantClient(path="./qdrant_data")
COLLECTION_NAME = "octron_memory"
EMBED_MODEL = "mxbai-embed-large"
VECTOR_SIZE = 1024

CORE_SOURCES = {"IDV2_core.txt", "IDV2_core(2).txt", "CORE LAWS.txt"}

# Create collection if missing
try:
    client.get_collection(COLLECTION_NAME)
except Exception:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9_']+", _normalize_text(text)))


def _phrase_overlap_boost(query: str, text: str) -> float:
    """
    Small lexical boost so retrieval isn't purely embedding-based.
    Helps exact/intended matches rise without breaking existing behavior.
    """
    q_norm = _normalize_text(query)
    t_norm = _normalize_text(text)

    if not q_norm or not t_norm:
        return 0.0

    boost = 0.0

    # exact substring boost
    if q_norm in t_norm:
        boost += 0.12

    q_tokens = _tokenize(q_norm)
    t_tokens = _tokenize(t_norm)

    if q_tokens and t_tokens:
        overlap = len(q_tokens & t_tokens) / max(1, len(q_tokens))
        boost += min(0.18, overlap * 0.18)

    return boost


def _text_similarity(a: str, b: str) -> float:
    """
    Lightweight near-duplicate detection to reduce repetitive recall results.
    """
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return inter / max(1, union)


def _source_topic_boost(query: str, source: str, topic: str, topic_filter: Optional[str]) -> float:
    boost = 0.0
    q = _normalize_text(query)

    if topic_filter and topic:
        if _normalize_text(topic_filter) == _normalize_text(topic):
            boost += 0.08

    if source:
        source_norm = _normalize_text(source)
        if source_norm and any(tok in source_norm for tok in _tokenize(q)):
            boost += 0.03

    if topic:
        topic_norm = _normalize_text(topic)
        if topic_norm and any(tok in topic_norm for tok in _tokenize(q)):
            boost += 0.05

    return boost


def _trim_memory_text(text: str, max_len: int = 420) -> str:
    """
    Keep recalled memory compact enough for chat loops.
    """
    text = text.strip()
    if len(text) <= max_len:
        return text

    # prefer sentence-ish trim
    chunk = text[:max_len]
    last_break = max(chunk.rfind(". "), chunk.rfind("\n"), chunk.rfind("; "))
    if last_break > 180:
        return chunk[: last_break + 1].strip()
    return chunk.rstrip() + "..."


def store_memory(text: str, source_name: str = "unknown", topic: str = "general") -> bool:
    """
    Store a text chunk with embedding + metadata.
    Returns False if exact duplicate exists.
    """
    text = (text or "").strip()
    if not text:
        return False

    content_hash = _content_hash(text)

    existing, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.content_hash",
                    match=models.MatchValue(value=content_hash),
                )
            ]
        ),
        limit=1,
        with_payload=False,
        with_vectors=False,
    )

    if existing:
        return False

    response = ollama.embeddings(model=EMBED_MODEL, prompt=text)
    vector = response["embedding"]

    point = models.PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "text": text,
            "metadata": {
                "source": source_name,
                "topic": topic,
                "content_hash": content_hash,
                "stored_at": datetime.now().isoformat(),
            },
        },
    )

    client.upsert(collection_name=COLLECTION_NAME, points=[point])
    return True


def recall_memory(
    query: str,
    n_results: int = 5,
    hide_core: bool = False,
    min_score: float = 0.35,
    topic_filter: str = None,
):
    """
    Smarter recall:
    - semantic retrieval via embeddings
    - small lexical rerank boost
    - near-duplicate collapse
    - tighter memory text to reduce prompt bloat
    Returns list[dict] with keys: text, source, score
    """
    try:
        query = (query or "").strip()
        if not query:
            return []

        response = ollama.embeddings(model=EMBED_MODEL, prompt=query)
        query_vector = response["embedding"]

        must = []
        must_not = []

        if hide_core:
            for source_name in CORE_SOURCES:
                must_not.append(
                    models.FieldCondition(
                        key="metadata.source",
                        match=models.MatchValue(value=source_name),
                    )
                )

        if topic_filter:
            must.append(
                models.FieldCondition(
                    key="metadata.topic",
                    match=models.MatchValue(value=topic_filter),
                )
            )

        search_filter = None
        if must or must_not:
            search_filter = models.Filter(
                must=must if must else None,
                must_not=must_not if must_not else None,
            )

        # Pull a few more than needed so reranking + dedupe has room
        raw_limit = max(n_results * 3, n_results + 4)

        search_result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=raw_limit,
        )

        rescored = []
        for hit in getattr(search_result, "points", []):
            payload = hit.payload or {}
            metadata = payload.get("metadata", {}) or {}
            text = (payload.get("text") or "").strip()
            if not text:
                continue

            base_score = float(getattr(hit, "score", 0.0))
            source = metadata.get("source", "unknown")
            topic = metadata.get("topic", "general")

            final_score = base_score
            final_score += _phrase_overlap_boost(query, text)
            final_score += _source_topic_boost(query, source, topic, topic_filter)

            if final_score < min_score:
                continue

            rescored.append(
                {
                    "text": text,
                    "source": source,
                    "topic": topic,
                    "score": round(final_score, 4),
                    "_base_score": round(base_score, 4),
                }
            )

        # sort by final score descending
        rescored.sort(key=lambda x: x["score"], reverse=True)

        # near-duplicate collapse
        filtered = []
        for item in rescored:
            is_duplicateish = False
            for chosen in filtered:
                sim = _text_similarity(item["text"], chosen["text"])
                if sim >= 0.82:
                    is_duplicateish = True
                    break
            if not is_duplicateish:
                filtered.append(item)
            if len(filtered) >= n_results:
                break

        # tighten text for downstream prompts
        results = []
        for item in filtered:
            results.append(
                {
                    "text": _trim_memory_text(item["text"]),
                    "source": item["source"],
                    "score": item["score"],
                }
            )

        return results

    except Exception as e:
        return [{"text": f"[memory error: {e}]", "source": "system", "score": 0.0}]


def recall_memory_simple(query: str, n_results: int = 5, hide_core: bool = False):
    """
    Backward-compatible wrapper returning only text strings.
    """
    results = recall_memory(query, n_results=n_results, hide_core=hide_core)
    return [r["text"] for r in results if isinstance(r, dict) and "text" in r]


def memory_count() -> int:
    """
    Return total number of stored memory chunks.
    """
    info = client.get_collection(COLLECTION_NAME)
    return info.points_count


def memory_stats() -> dict:
    """
    Return basic collection stats.
    """
    info = client.get_collection(COLLECTION_NAME)
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    sources = {}
    topics = {}

    for point in points:
        payload = point.payload or {}
        metadata = payload.get("metadata", {}) or {}

        source = metadata.get("source", "unknown")
        topic = metadata.get("topic", "general")

        sources[source] = sources.get(source, 0) + 1
        topics[topic] = topics.get(topic, 0) + 1

    return {
        "total_chunks": info.points_count,
        "sources": sources,
        "topics": topics,
    }