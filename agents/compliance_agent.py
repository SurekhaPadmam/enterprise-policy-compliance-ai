"""Turn grounded domain findings into one compliance decision."""
from agents.llm import create_llm
from models import ComplianceDecision, DomainFinding, Evidence


class ComplianceAgent:
    """Produces a structured decision using only the retrieved policy evidence."""

    def __init__(self) -> None:
        self.structured_llm = create_llm().with_structured_output(ComplianceDecision)

    def evaluate(self, question: str, findings: list[DomainFinding], evidence: list[Evidence]) -> ComplianceDecision:
        prompt = f"""You are an enterprise policy compliance evaluator.

Decide whether the user's proposed action complies with the supplied policy evidence.
Use only the findings and evidence below. Never invent a policy requirement.
If the evidence does not clearly support a decision, return `Insufficient Policy Evidence`.

User question: {question}

Domain findings: {findings}

Retrieved evidence: {evidence}"""
        return ComplianceDecision.model_validate(self.structured_llm.invoke(prompt))
