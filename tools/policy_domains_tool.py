"""Expose the domains that have policy evidence in the local vector store."""
import json
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool


METADATA_PATH = Path("data/vector_store/metadata.json")


@tool
def get_available_domains() -> str:
    """Return indexed policy domains and the number of chunks available for each."""
    if not METADATA_PATH.exists():
        return "{}"

    chunks = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    counts = Counter(domain for chunk in chunks for domain in chunk.get("domains", []))
    return json.dumps(dict(sorted(counts.items())))
