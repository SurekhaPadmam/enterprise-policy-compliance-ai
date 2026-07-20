"""Reusable FAISS retrieval tool for policy-domain agents."""
import json
from functools import lru_cache
from pathlib import Path

import faiss
from langchain_core.tools import tool
from sentence_transformers import SentenceTransformer


VECTOR_STORE_DIR = Path("data/vector_store")


@lru_cache
def load_embedding_model():
    return SentenceTransformer("BAAI/bge-small-en-v1.5")


@tool
def search_policies(query: str, domains: list[str]) -> str:
    """Retrieve the most relevant indexed policy chunks for the requested domains."""
    index_path = VECTOR_STORE_DIR / "policies.faiss"
    metadata_path = VECTOR_STORE_DIR / "metadata.json"
    if not index_path.exists() or not metadata_path.exists():
        return "[]"

    index = faiss.read_index(str(index_path))
    chunks = json.loads(metadata_path.read_text(encoding="utf-8"))
    query_vector = load_embedding_model().encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vector)

    # FAISS returns chunks ordered by semantic similarity to the user question.
    scores, indices = index.search(query_vector, index.ntotal)
    evidence = []
    for score, chunk_id in zip(scores[0], indices[0]):
        if chunk_id < 0:
            continue
        chunk = chunks[chunk_id]
        if not set(chunk.get("domains", [])).intersection(domains):
            continue
        evidence.append({
            "domain": domains[0] if domains else "general",
            "document": chunk["document"],
            "page": chunk["page"],
            "section": chunk["section"],
            "text": chunk["text"],
            "semantic_score": round(float(score), 3),
        })
        if len(evidence) == 4:
            break
    return json.dumps(evidence, indent=2)
