"""Focused policy-domain agents grounded in FAISS evidence."""
import json

from agents.llm import create_llm
from models import DomainAnalysis, DomainFinding, Evidence
from tools.retriever_tool import search_policies


DOMAIN_INSTRUCTIONS = {
    "security": "Focus on data classification, secure transfer, passwords, security incidents, and access controls.",
    "hr": "Focus on leave, remote work, employee conduct, and manager or HR approvals.",
    "finance": "Focus on travel, expenses, reimbursement limits, receipts, and financial approvals.",
    "it": "Focus on company devices, software approval, service desk actions, and technical access.",
}


class DomainAgent:
    """One reusable implementation configured as Security, HR, Finance, or IT."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.structured_llm = create_llm().with_structured_output(DomainAnalysis)

    def analyze(self, question: str) -> DomainFinding:
        evidence_json = search_policies.invoke({"query": question, "domains": [self.domain]})
        evidence = [Evidence.model_validate(item) for item in json.loads(evidence_json)]
        if not evidence:
            return DomainFinding(domain=self.domain, finding="No relevant policy evidence was retrieved.")

        prompt = f"""You are the {self.domain} policy agent.
{DOMAIN_INSTRUCTIONS[self.domain]}

Answer only from the retrieved policy evidence. Do not invent policy requirements.

User question: {question}

Retrieved evidence:
{evidence_json}"""
        analysis = DomainAnalysis.model_validate(self.structured_llm.invoke(prompt))
        return DomainFinding(domain=self.domain, evidence=evidence, **analysis.model_dump())


def security_agent(question: str) -> DomainFinding:
    return DomainAgent("security").analyze(question)


def hr_agent(question: str) -> DomainFinding:
    return DomainAgent("hr").analyze(question)


def finance_agent(question: str) -> DomainFinding:
    return DomainAgent("finance").analyze(question)


def it_agent(question: str) -> DomainFinding:
    return DomainAgent("it").analyze(question)
