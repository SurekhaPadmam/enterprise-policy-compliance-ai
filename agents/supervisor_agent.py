"""Gemini-powered supervisor that classifies a question and selects domains."""
import json

from agents.llm import create_llm
from models import RoutingDecision
from tools.policy_domains_tool import get_available_domains


class SupervisorAgent:
    """Uses Gemini structured output to route a user question to policy domains."""

    def __init__(self) -> None:
        self.structured_llm = create_llm().with_structured_output(RoutingDecision)

    def route(self, question: str) -> RoutingDecision:
        available_domains = json.loads(get_available_domains.invoke({}))
        if not available_domains:
            raise ValueError("No policy metadata found. Run ingest_policies.py first.")
        routable_agents = ["security", "hr", "finance", "it"]
        allowed_agents = [agent for agent in routable_agents if agent in available_domains] + ["general"]
        prompt = f"""You are the supervisor for an enterprise policy compliance assistant.

Classify the user's question. Select every relevant domain agent, but only from:
{allowed_agents}

Use `incident` for loss, theft, a suspected breach, or another security incident.
Use `approval_request` when the user is explicitly asking how to obtain approval.
Use `policy_question` when the user asks what a policy says.
Otherwise use `compliance_check` for a proposed action.

Always set needs_rag to true. Use `general` only when no listed domain applies.

User question: {question}"""
        decision = RoutingDecision.model_validate(self.structured_llm.invoke(prompt))

        valid_agents = [agent for agent in decision.agents if agent in allowed_agents]
        if not valid_agents:
            valid_agents = ["general"]
        return decision.model_copy(update={"agents": valid_agents})
