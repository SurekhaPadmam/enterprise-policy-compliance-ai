"""Format evidence as citations and create highlighted source-PDF copies."""
from collections import defaultdict

from models import Citation, CitationResult, Evidence
from tools.document_tool import highlight_policy_evidence


class CitationAgent:
    """Deterministic citation formatter: source metadata always comes from retrieval."""

    def format(self, evidence: list[Evidence]) -> CitationResult:
        citations: list[Citation] = []
        citations_by_document: dict[str, list[dict]] = defaultdict(list)
        for number, item in enumerate(evidence, start=1):
            citation = Citation(id=number, **item.model_dump())
            citations.append(citation)
            citations_by_document[item.document].append(citation.model_dump())

        highlighted_documents = []
        for document, document_citations in citations_by_document.items():
            output_path = highlight_policy_evidence.invoke({
                "document": document,
                "citations": document_citations,
            })
            if output_path:
                highlighted_documents.append(output_path)

        return CitationResult(citations=citations, highlighted_documents=highlighted_documents)
