
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

import faiss
import fitz
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}
DOCUMENTS_DIR = Path("data/input/policies")
VECTOR_STORE_DIR = Path("data/vector_store")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
METADATA_SCHEMA_VERSION = 2

DOMAIN_KEYWORDS = {
    "hr": ["hr", "human resources", "leave", "employee", "manager", "sick leave", "remote work", "conduct"],
    "security": ["security", "restricted data", "password", "encryption", "vpn", "incident", "data classification"],
    "finance": ["expense", "receipt", "reimburse", "travel", "client entertainment", "per person"],
    "it": ["laptop", "device", "software", "service desk", "installing", "access"],
    "legal_privacy": ["gdpr", "privacy", "personal data", "data subject", "legal"],
    "procurement_vendor": ["vendor", "supplier", "procurement", "purchase order", "third party"],
}

FILENAME_DOMAINS = {
    "ai_usage_policy": ["security", "it"],
    "information_security_policy": ["security", "it"],
    "hr_policy": ["hr"],
    "leave_policy": ["hr"],
    "expense_policy": ["finance"],
}


class PolicyChunk(BaseModel):
    """Text and traceable source metadata stored alongside its vector."""

    chunk_id: str
    source_path: str
    document: str
    document_hash: str
    domains: list[str]
    page: int | None
    section: str | None
    text: str


def extract_document(path: Path) -> list[tuple[int | None, str]]:
    """Return page-aware text from a PDF, Markdown, or plain-text policy."""
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as pdf:
            return [(number + 1, page.get_text("text")) for number, page in enumerate(pdf)]
    return [(None, path.read_text(encoding="utf-8", errors="replace"))]


def section_at(text: str, position: int) -> str | None:
    """Find the nearest Markdown or numbered heading before a chunk."""
    headings = list(re.finditer(r"(?m)^(?:#{1,6}\s+|\d+(?:\.\d+)*\s+)(.+)$", text))
    prior = [match.group(1).strip() for match in headings if match.start() <= position]
    return prior[-1] if prior else None


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, str]]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(". ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunks.append((start, normalized[start:end].strip()))
        if end == len(normalized):
            break
        start = end - overlap
    return chunks


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def find_policy_files(documents_dir: Path) -> list[Path]:
    files = sorted(path for path in documents_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
    if not files:
        raise ValueError(f"No supported policy documents found in {documents_dir}")
    return files


def detect_domains(path: Path, document_text: str) -> list[str]:
    """Assign one or more policy domains from the filename and policy content."""
    if path.stem.lower() in FILENAME_DOMAINS:
        return FILENAME_DOMAINS[path.stem.lower()]
    filename = path.stem.lower().replace("_", " ")
    text = document_text.lower()
    scores = {
        domain: sum(keyword in text for keyword in keywords) + (3 * sum(keyword in filename for keyword in keywords))
        for domain, keywords in DOMAIN_KEYWORDS.items()
    }
    domains = [domain for domain, score in scores.items() if score > 0]
    return domains or ["general"]


def build_chunks(files: list[Path], chunk_size: int = 900, overlap: int = 150) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for path in files:
        source_path = path.relative_to(DOCUMENTS_DIR).as_posix()
        document_hash = file_hash(path)
        pages = extract_document(path)
        domains = detect_domains(path, "\n".join(text for _, text in pages))
        print(f"Reading: {path.name}")
        print(f"Domains: {', '.join(domains)}")
        document_chunk_count = 0
        for page, text in pages:
            print(f"Chunking: {path.name}" + (f" (page {page})" if page else ""))
            for number, (position, chunk) in enumerate(chunk_text(text, chunk_size, overlap)):
                chunks.append(PolicyChunk(
                    chunk_id=f"{document_hash[:12]}-p{page or 0}-c{number}",
                    source_path=source_path,
                    document=path.name,
                    document_hash=document_hash,
                    domains=domains,
                    page=page,
                    section=section_at(text, position),
                    text=chunk,
                ))
                document_chunk_count += 1
        print(f"Created {document_chunk_count} chunk(s) from {path.name}.")
    return chunks


def load_manifest() -> dict:
    manifest_path = VECTOR_STORE_DIR / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(documents: dict[str, str], total_chunks: int) -> None:
    manifest = {
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "embedding_model": MODEL_NAME,
        "documents": documents,
        "chunks": total_chunks,
    }
    (VECTOR_STORE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def create_embeddings(chunks: list[PolicyChunk]):
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print(f"Creating embeddings for {len(chunks)} chunk(s)...")
    embeddings = model.encode([chunk.text for chunk in chunks], convert_to_numpy=True, show_progress_bar=True)
    print(f"Created {len(embeddings)} embedding(s).")
    embeddings = embeddings.astype("float32")
    faiss.normalize_L2(embeddings)  # cosine similarity via inner-product search
    return embeddings


def rebuild_vector_store(chunks: list[PolicyChunk], document_hashes: dict[str, str]) -> None:
    embeddings = create_embeddings(chunks)
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    print("Creating FAISS vector index...")
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    print(f"Saving vector database to: {VECTOR_STORE_DIR}")
    faiss.write_index(index, str(VECTOR_STORE_DIR / "policies.faiss"))
    (VECTOR_STORE_DIR / "metadata.json").write_text(json.dumps([chunk.model_dump() for chunk in chunks], indent=2), encoding="utf-8")
    save_manifest(document_hashes, len(chunks))


def add_new_documents(new_files: list[Path], document_hashes: dict[str, str]) -> int:
    chunks = build_chunks(new_files)
    embeddings = create_embeddings(chunks)
    index = faiss.read_index(str(VECTOR_STORE_DIR / "policies.faiss"))
    index.add(embeddings)
    existing_chunks = json.loads((VECTOR_STORE_DIR / "metadata.json").read_text(encoding="utf-8"))
    existing_chunks.extend(chunk.model_dump() for chunk in chunks)
    faiss.write_index(index, str(VECTOR_STORE_DIR / "policies.faiss"))
    (VECTOR_STORE_DIR / "metadata.json").write_text(json.dumps(existing_chunks, indent=2), encoding="utf-8")
    save_manifest(document_hashes, len(existing_chunks))
    return len(chunks)


def update_vector_store() -> None:
    files = find_policy_files(DOCUMENTS_DIR)
    print(f"Found {len(files)} policy document(s). Checking for changes...")
    document_hashes = {path.relative_to(DOCUMENTS_DIR).as_posix(): file_hash(path) for path in files}
    manifest = load_manifest()
    known_documents = manifest.get("documents", {})
    new_files = [path for path in files if path.relative_to(DOCUMENTS_DIR).as_posix() not in known_documents]
    changed = [name for name, digest in document_hashes.items() if name in known_documents and known_documents[name] != digest]
    deleted = [name for name in known_documents if name not in document_hashes]
    index_exists = (VECTOR_STORE_DIR / "policies.faiss").exists() and (VECTOR_STORE_DIR / "metadata.json").exists()

    if (
        not index_exists
        or manifest.get("embedding_model") != MODEL_NAME
        or manifest.get("metadata_schema_version") != METADATA_SCHEMA_VERSION
        or not known_documents
    ):
        print("No compatible document manifest found. Building the full vector database...")
        rebuild_vector_store(build_chunks(files), document_hashes)
    elif changed or deleted:
        print("Changed or deleted policies detected. Rebuilding the vector database safely...")
        rebuild_vector_store(build_chunks(files), document_hashes)
    elif new_files:
        print(f"Found {len(new_files)} new policy document(s). Adding only the new documents...")
        added_chunks = add_new_documents(new_files, document_hashes)
        print(f"Added {added_chunks} new chunk(s).")
    else:
        print("No new or changed policy documents. FAISS is already up to date.")


def main() -> None:
    print("Starting policy document ingestion...")
    update_vector_store()
    print(f"Done. Vector database is available in {VECTOR_STORE_DIR}.")


if __name__ == "__main__":
    main()
