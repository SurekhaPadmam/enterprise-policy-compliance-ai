"""Run the policy compliance LangGraph.

The graph is intentionally small:
    supervisor -> selected domain agents -> merge results

Run with: uv run main.py
"""
import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from models import Citation, ComplianceDecision, DomainFinding, Evidence, FinalResponse, RoutingDecision
from agents.domain_agents import finance_agent, hr_agent, it_agent, security_agent
from agents.compliance_agent import ComplianceAgent
from agents.citation_agent import CitationAgent
from agents.supervisor_agent import SupervisorAgent


DOMAIN_AGENTS = {
    "security": security_agent,
    "hr": hr_agent,
    "finance": finance_agent,
    "it": it_agent,
}


class PolicyState(TypedDict):
    question: str
    routing: dict
    pending_agents: list[str]
    domain_findings: Annotated[list[dict], operator.add]
    combined_evidence: list[dict]
    compliance_decision: dict
    citations: list[dict]
    highlighted_documents: list[str]
    final_result: dict


def supervisor_node(state: PolicyState) -> dict:
    """Ask Gemini which domain agents should handle the question."""
    routing = SupervisorAgent().route(state["question"])
    selected_agents = routing.agents
    if "general" in selected_agents:
        selected_agents = list(DOMAIN_AGENTS)
    selected_agents = [agent for agent in selected_agents if agent in DOMAIN_AGENTS]
    return {"routing": routing.model_dump(), "pending_agents": selected_agents}


def next_node(state: PolicyState) -> str:
    """Route to one selected agent at a time, then merge all findings."""
    if state["pending_agents"]:
        return state["pending_agents"][0]
    return "merge"


def make_domain_node(domain: str):
    """Create a graph node for one focused domain agent."""
    def domain_node(state: PolicyState) -> dict:
        print(f"Checking {domain} agent...")
        finding = DOMAIN_AGENTS[domain](state["question"])
        print(f"{domain.title()} finding: {finding.finding}")
        remaining_agents = [agent for agent in state["pending_agents"] if agent != domain]
        return {"domain_findings": [finding.model_dump()], "pending_agents": remaining_agents}

    return domain_node


def merge_node(state: PolicyState) -> dict:
    """Combine every domain finding and its supporting policy evidence."""
    findings = [DomainFinding.model_validate(item) for item in state["domain_findings"]]
    evidence: list[Evidence] = []
    seen_sources = set()
    for finding in findings:
        for item in finding.evidence:
            source_key = (item.document, item.page, item.section)
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            evidence.append(Evidence(
                domain=finding.domain,
                document=item.document,
                page=item.page,
                section=item.section,
                text=item.text,
                excerpt=item.text[:350],
                semantic_score=item.semantic_score,
            ))
    return {"combined_evidence": [item.model_dump() for item in evidence]}


def compliance_node(state: PolicyState) -> dict:
    """Create one final compliance decision from all evidence."""
    print("Checking compliance agent...")
    decision = ComplianceAgent().evaluate(
        state["question"],
        [DomainFinding.model_validate(item) for item in state["domain_findings"]],
        [Evidence.model_validate(item) for item in state["combined_evidence"]],
    )
    print(f"Compliance status: {decision.status}")
    return {"compliance_decision": decision.model_dump()}


def citation_node(state: PolicyState) -> dict:
    """Attach source citations and create highlighted source-PDF copies."""
    print("Checking citation agent...")
    result = CitationAgent().format([Evidence.model_validate(item) for item in state["combined_evidence"]])
    return result.model_dump()


def response_node(state: PolicyState) -> dict:
    """Return one readable, structured result to the user."""
    decision = ComplianceDecision.model_validate(state["compliance_decision"])
    citations = [Citation.model_validate(item) for item in state["citations"]]
    citation_lines = []
    for citation in citations:
        page = f", page {citation.page}" if citation.page else ""
        section = f", {citation.section}" if citation.section else ""
        citation_lines.append(f"[{citation.id}] {citation.document}{page}{section}")
    approval_text = ", ".join(decision.approvals_required) or "None"
    formatted_answer = (
        f"Compliance Status: {decision.status}\n\n"
        f"Reasoning: {decision.reasoning}\n\n"
        f"Risk: {decision.risk}\n\n"
        f"Recommended Next Action: {decision.recommended_next_action}\n\n"
        f"Approvals Required: {approval_text}\n\n"
        f"Evidence:\n" + "\n".join(citation_lines)
    )
    final_result = FinalResponse(
        question=state["question"],
        routing=RoutingDecision.model_validate(state["routing"]),
        compliance_decision=decision,
        findings=[DomainFinding.model_validate(item) for item in state["domain_findings"]],
        citations=citations,
        highlighted_documents=state["highlighted_documents"],
        formatted_answer=formatted_answer,
    )
    return {"final_result": final_result.model_dump(mode="json")}


# This is the LangGraph workflow. Every node and edge is defined here.
workflow = StateGraph(PolicyState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("security", make_domain_node("security"))
workflow.add_node("hr", make_domain_node("hr"))
workflow.add_node("finance", make_domain_node("finance"))
workflow.add_node("it", make_domain_node("it"))
workflow.add_node("merge", merge_node)
workflow.add_node("compliance", compliance_node)
workflow.add_node("citations", citation_node)
workflow.add_node("response", response_node)

workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges("supervisor", next_node)
workflow.add_conditional_edges("security", next_node)
workflow.add_conditional_edges("hr", next_node)
workflow.add_conditional_edges("finance", next_node)
workflow.add_conditional_edges("it", next_node)
workflow.add_edge("merge", "compliance")
workflow.add_edge("compliance", "citations")
workflow.add_edge("citations", "response")
workflow.add_edge("response", END)

policy_graph = workflow.compile()


def main() -> None:
    question = input("What action or policy question would you like to check?\n> ").strip()
    if not question:
        print("Please enter a policy question.")
        return

    result = policy_graph.invoke({"question": question, "domain_findings": []})
    print("\nOutput findings with evidence:")
    print(json.dumps(result["final_result"], indent=2))


if __name__ == "__main__":
    main()
