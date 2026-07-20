"""Validated data exchanged by the policy workflow."""
from typing import Literal

from pydantic import BaseModel, Field


class RoutingDecision(BaseModel):
    intent: str
    request_type: Literal["compliance_check", "policy_question", "incident", "approval_request"]
    needs_rag: bool
    agents: list[str]


class Evidence(BaseModel):
    domain: str = ""
    document: str
    page: int | None = None
    section: str | None = None
    text: str = ""
    excerpt: str = ""
    semantic_score: float | None = None


class DomainAnalysis(BaseModel):
    finding: str
    relevant_rules: list[str] = Field(default_factory=list)


class DomainFinding(DomainAnalysis):
    domain: str
    evidence: list[Evidence] = Field(default_factory=list)


class ComplianceDecision(BaseModel):
    status: Literal["Allowed", "Allowed with Conditions", "Needs Approval", "Not Compliant", "Insufficient Policy Evidence"]
    reasoning: str
    risk: Literal["Low", "Medium", "High", "Unknown"]
    policies_involved: list[str]
    recommended_next_action: str
    approvals_required: list[str] = Field(default_factory=list)


class Citation(Evidence):
    id: int


class CitationResult(BaseModel):
    citations: list[Citation]
    highlighted_documents: list[str] = Field(default_factory=list)


class FinalResponse(BaseModel):
    question: str
    routing: RoutingDecision
    compliance_decision: ComplianceDecision
    findings: list[DomainFinding]
    citations: list[Citation]
    highlighted_documents: list[str]
    formatted_answer: str
