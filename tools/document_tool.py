"""Create a highlighted copy of a cited PDF policy document."""
from difflib import SequenceMatcher
import re
from pathlib import Path
from uuid import uuid4

import fitz
from langchain_core.tools import tool


POLICY_DIR = Path("data/input/policies")
HIGHLIGHT_DIR = Path("data/output/highlighted_evidence")


def _normalize_word(word: str) -> str:
    """Normalize punctuation and casing without changing the underlying PDF text."""
    return re.sub(r"[^\w]+", "", word).casefold()


def _tokenize(text: str) -> list[str]:
    return [word for word in (_normalize_word(value) for value in text.split()) if word]


def _merge_word_rectangles(rectangles: list[fitz.Rect]) -> list[fitz.Rect]:
    """Join consecutive words on a line into readable highlight bands."""
    merged: list[fitz.Rect] = []
    for rectangle in rectangles:
        if (
            merged
            and abs(merged[-1].y0 - rectangle.y0) < 2
            and rectangle.x0 <= merged[-1].x1 + 14
        ):
            merged[-1] |= rectangle
        else:
            merged.append(rectangle)
    return merged


def _evidence_rectangles(page: fitz.Page, evidence_text: str) -> list[fitz.Rect]:
    """Locate exact evidence word sequences on a page and return their rectangles."""
    page_words = page.get_text("words", sort=True)
    page_tokens = [_normalize_word(word[4]) for word in page_words]
    evidence_tokens = _tokenize(evidence_text)
    if not page_tokens or not evidence_tokens:
        return []

    matcher = SequenceMatcher(None, evidence_tokens, page_tokens, autojunk=False)
    matching_blocks = [block for block in matcher.get_matching_blocks() if block.size >= 4]
    matched_word_count = sum(block.size for block in matching_blocks)
    required_matches = min(12, max(4, len(evidence_tokens) // 5))
    if matched_word_count < required_matches:
        return []

    rectangles: list[fitz.Rect] = []
    for block in matching_blocks:
        # A four-word minimum prevents headings and incidental short phrases from being marked.
        matching_words = page_words[block.b:block.b + block.size]
        rectangles.extend(fitz.Rect(word[:4]) for word in matching_words)
    return _merge_word_rectangles(rectangles)


@tool
def highlight_policy_evidence(document: str, citations: list[dict]) -> str:
    """Create a PDF copy highlighting only the retrieved evidence text on cited pages."""
    source_path = POLICY_DIR / document
    if source_path.suffix.lower() != ".pdf":
        return ""
    if not source_path.exists():
        return ""

    HIGHLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = HIGHLIGHT_DIR / f"{source_path.stem}_evidence_{uuid4().hex[:8]}.pdf"
    pdf = fitz.open(source_path)
    for citation in citations:
        page_number = citation.get("page")
        if not page_number or page_number > len(pdf):
            continue
        page = pdf[page_number - 1]
        evidence_text = citation.get("text") or citation.get("excerpt", "")
        for rectangle in _evidence_rectangles(page, evidence_text):
            annotation = page.add_highlight_annot(rectangle)
            annotation.set_colors(stroke=(1, 0.9, 0))
            annotation.update()
    pdf.save(output_path)
    pdf.close()
    return str(output_path)
