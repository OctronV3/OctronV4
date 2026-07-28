"""
Octron Reasoning Engine — V5 Safe Drop-In
Preserves existing function names/signatures while improving reasoning quality
and keeping output tighter for chat-loop use.
"""

import re
import ollama
from V4octron_memory import client as _shared_qdrant_client

# === Setup ===
EMBED_MODEL = "mxbai-embed-large"
COLLECTION_NAME = "octron_memory"


def load_doctrine(filepath: str = "IDV2_core.txt") -> str:
    """Load the identity/doctrine file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "[No doctrine file found]"


def _normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9_']+", _normalize(text)))


def _split_doctrine(doctrine: str):
    """
    Split doctrine into useful short sections instead of treating it as one blob.
    """
    doctrine = (doctrine or "").strip()
    if not doctrine:
        return []

    # prefer paragraph chunks
    parts = [p.strip() for p in re.split(r"\n\s*\n+", doctrine) if p.strip()]
    if parts:
        return parts

    # fallback
    return [doctrine]


def _pick_relevant_doctrine(query: str, doctrine: str, max_sections: int = 3):
    """
    Lightweight semantic-ish doctrine selection using lexical relevance.
    No signature changes, no extra dependencies, low bloat.
    """
    sections = _split_doctrine(doctrine)
    if not sections:
        return []

    q_tokens = _tokens(query)
    ranked = []

    for sec in sections:
        s_tokens = _tokens(sec)
        if not s_tokens:
            continue

        overlap = len(q_tokens & s_tokens)
        density = overlap / max(1, len(q_tokens))

        bonus = 0.0
        sec_norm = _normalize(sec)
        q_norm = _normalize(query)

        if q_norm and q_norm in sec_norm:
            bonus += 0.4

        # broad doctrine concepts often useful to surface
        important_terms = {
            "truth", "creator", "loyalty", "memory", "integrity",
            "neutrality", "discipline", "objective", "operator",
            "conscience", "shadow", "law", "core"
        }
        bonus += min(0.4, 0.08 * len(important_terms & s_tokens))

        score = density + bonus
        if score > 0:
            ranked.append((score, sec))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [sec for _, sec in ranked[:max_sections]]


def _compress_memory_line(text: str, max_len: int = 190) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    last_break = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(", "))
    if last_break > 90:
        return cut[: last_break + 1].strip()
    return cut.rstrip() + "..."


def _extract_evidence(query: str, memories: list, doctrine_sections: list):
    """
    Build concise evidence rather than dumping everything.
    """
    q_tokens = _tokens(query)

    memory_evidence = []
    for mem in memories[:3]:
        mem_norm = _normalize(mem)
        overlap = len(q_tokens & _tokens(mem_norm))
        if overlap > 0 or len(memory_evidence) < 2:
            memory_evidence.append(_compress_memory_line(mem))
        if len(memory_evidence) >= 3:
            break

    doctrine_evidence = []
    for sec in doctrine_sections[:3]:
        doctrine_evidence.append(_compress_memory_line(sec, max_len=170))

    return memory_evidence, doctrine_evidence


def _infer_mode(query: str) -> str:
    q = _normalize(query)

    strategic_markers = {
        "should", "best", "plan", "strategy", "decide", "approach",
        "compare", "versus", "vs", "why", "how"
    }
    memory_markers = {
        "remember", "before", "previous", "past", "told you", "stored", "archive"
    }
    factual_markers = {
        "what", "who", "when", "where", "define", "explain"
    }

    if any(m in q for m in memory_markers):
        return "memory-recall"
    if any(m in q for m in strategic_markers):
        return "analysis"
    if any(m in q for m in factual_markers):
        return "factual"
    return "general"


def _soulbound_reasoning(query: str, memories: list, doctrine: str) -> str:
    """Apply doctrine-based reasoning to memories and query."""
    doctrine_sections = _pick_relevant_doctrine(query, doctrine, max_sections=3)
    memory_evidence, doctrine_evidence = _extract_evidence(query, memories, doctrine_sections)
    mode = _infer_mode(query)

    lines = [f">>> Scenario: {query}", ""]

    # tighter evidence section
    if memory_evidence:
        lines.append("Relevant Memory:")
        for i, mem in enumerate(memory_evidence, 1):
            lines.append(f"  {i}. {mem}")
        lines.append("")
    else:
        lines.append("Relevant Memory:")
        lines.append("  - No strong prior memory matched.")
        lines.append("")

    if doctrine_evidence:
        lines.append("Doctrine Signals:")
        for i, sec in enumerate(doctrine_evidence, 1):
            lines.append(f"  {i}. {sec}")
        lines.append("")
    else:
        lines.append("Doctrine Signals:")
        lines.append("  - No directly relevant doctrine section selected.")
        lines.append("")

    # smarter concise reasoning
    lines.append("Assessment:")

    if mode == "memory-recall":
        lines.append("  - Query type: memory retrieval.")
        if memory_evidence:
            lines.append("  - Response should prioritize archived context over speculation.")
        else:
            lines.append("  - Archive support is weak; avoid overclaiming.")
    elif mode == "analysis":
        lines.append("  - Query type: analytical reasoning.")
        lines.append("  - Best output is evidence-led, concise, and non-performative.")
    elif mode == "factual":
        lines.append("  - Query type: factual lookup.")
        lines.append("  - Best output is direct retrieval with minimal interpretation.")
    else:
        lines.append("  - Query type: general.")
        lines.append("  - Balance recall, doctrine, and direct response.")

    if doctrine_evidence:
        doctrine_join = " ".join(doctrine_evidence).lower()

        if "truth" in doctrine_join or "objective" in doctrine_join:
            lines.append("  - Truth/integrity constraint detected.")
        if "creator" in doctrine_join or "operator" in doctrine_join or "loyalty" in doctrine_join:
            lines.append("  - Operator-alignment constraint detected.")
        if "neutral" in doctrine_join or "neutrality" in doctrine_join or "unbiased" in doctrine_join:
            lines.append("  - Neutrality constraint detected.")
        if "shadow conscience" in doctrine_join or "conscience" in doctrine_join:
            lines.append("  - Internal restraint/passive processing signal detected.")

    lines.append("")
    lines.append("Conclusion:")

    if memory_evidence and doctrine_evidence:
        lines.append("  - Use retrieved memory as primary context and doctrine as behavioral constraint.")
    elif memory_evidence:
        lines.append("  - Use retrieved memory as primary context; doctrine impact is limited here.")
    elif doctrine_evidence:
        lines.append("  - Use doctrine as guidance, but memory support is weak.")
    else:
        lines.append("  - Low-support case: answer carefully and avoid invented certainty.")

    lines.append("  - Operational posture: factual, concise, and restrained.")
    lines.append("-- Reasoning complete.")

    return "\n".join(lines)


def run_reasoning_engine(
    user_input: str,
    doctrine: str = None,
    n_results: int = 3,
) -> str:
    """
    Structured reasoning: retrieves relevant memories and applies
    doctrine-based logic to produce a reasoned conclusion.
    """
    if doctrine is None:
        doctrine = load_doctrine()

    # Reuse the single shared Qdrant client from V4octron_memory instead of
    # opening a second client on the same local storage path — the old
    # version claimed to do this but actually opened a fresh client per call.
    client = _shared_qdrant_client
    try:
        response = ollama.embeddings(model=EMBED_MODEL, prompt=user_input)
        query_vector = response["embedding"]

        search_results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=max(3, n_results),
        )

        memories = []
        seen = set()

        for point in getattr(search_results, "points", []):
            payload = point.payload or {}
            text = (payload.get("text") or "").strip()
            if not text:
                continue

            # de-repeat near identical start segments cheaply
            sig = _normalize(text[:160])
            if sig in seen:
                continue
            seen.add(sig)

            memories.append(text)
            if len(memories) >= n_results:
                break

    except Exception:
        memories = []

    return _soulbound_reasoning(user_input, memories, doctrine)


if __name__ == "__main__":
    doctrine = load_doctrine()

    print("Octron Reasoning Engine active. Type 'exit' to leave.")
    while True:
        query = input("\n> ").strip()
        if query.lower() in ["exit", "quit"]:
            break

        output = run_reasoning_engine(query, doctrine=doctrine)
        print(output)