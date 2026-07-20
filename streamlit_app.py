"""Local Streamlit interface for the Enterprise Policy Compliance Assistant.

Run with: uv run streamlit run streamlit_app.py
"""
import base64
import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from main import policy_graph
from models import FinalResponse


st.set_page_config(page_title="Policy Compliance Assistant", page_icon="\U0001F6E1", layout="wide")

st.markdown(
    """
    <style>
        .stApp { background: linear-gradient(135deg, #f7faff 0%, #f4f7fb 55%, #eef8f5 100%); }
        .block-container { max-width: 1250px; padding-top: 3rem; padding-bottom: 3rem; }
        .hero { padding: 0.9rem 1.3rem; border-radius: 14px; color: #ffffff;
                background: linear-gradient(115deg, #123a63, #176b68); box-shadow: 0 14px 30px #123a6330; }
        .hero h1 { margin: 0; font-size: 1.3rem; }
        .hero p { margin: .55rem 0 0; color: #dceefa; font-size: 1.05rem; }
        #policy-result { scroll-margin-top: 1rem; }
        .sample-callout { margin: 1.2rem 0 .7rem; padding: 1rem 1.2rem; border-radius: 14px;
                          border: 1px solid #7db7d8; background: linear-gradient(100deg, #e8f5fb, #eef8f5); }
        .sample-callout h3 { margin: 0; color: #123a63; font-size: 1.15rem; }
        .sample-callout p { margin: .25rem 0 0; color: #45657d; }
        .status-card { border-radius: 16px; padding: 1.35rem 1.5rem; margin-bottom: 1rem;
                       border: 1px solid; box-shadow: 0 7px 18px #172b4d12; }
        .status-label { margin: 0 0 .35rem; font-size: .78rem; font-weight: 700;
                        letter-spacing: .08em; text-transform: uppercase; opacity: .78; }
        .status-value { margin: 0; font-size: 1.7rem; font-weight: 750; }
        .status-meta { display: flex; gap: .65rem; flex-wrap: wrap; margin-top: 1rem; }
        .pill { padding: .3rem .65rem; border-radius: 999px; background: #ffffffa8; font-size: .87rem; font-weight: 600; }
        .risk-low { background: #dff5e7; color: #145a32; }
        .risk-medium { background: #fff1c7; color: #79550a; }
        .risk-high { background: #ffdede; color: #9e2424; }
        .risk-unknown { background: #e5e7eb; color: #334155; }
        .allowed { background: #e9f8ef; border-color: #6bc98b; color: #145a32; }
        .conditional, .approval { background: #fff7df; border-color: #e8bf50; color: #79550a; }
        .not-compliant { background: #fff0f0; border-color: #df7474; color: #9e2424; }
        .insufficient { background: #edf1f7; border-color: #94a3b8; color: #334155; }
        .detailed-answer { line-height: 1.55; }
        .answer-item { margin: 0 0 1rem; }
        .answer-heading { color: #123a63; font-weight: 750; text-decoration: underline;
                          text-underline-offset: 3px; }
    </style>
    """,
    unsafe_allow_html=True,
)

NODE_MESSAGES = {
    "supervisor": "Supervisor is identifying the relevant policy domains...",
    "security": "Security agent is reviewing policy evidence...",
    "hr": "HR agent is reviewing policy evidence...",
    "finance": "Finance agent is reviewing policy evidence...",
    "it": "IT agent is reviewing policy evidence...",
    "merge": "Combining the retrieved policy evidence...",
    "compliance": "Compliance agent is preparing a decision...",
    "citations": "Citation agent is preparing highlighted source documents...",
    "response": "Formatting the final answer...",
}

NEXT_NODES = {
    "merge": "compliance",
    "compliance": "citations",
    "citations": "response",
}

STATUS_CLASSES = {
    "Allowed": "allowed",
    "Allowed with Conditions": "conditional",
    "Needs Approval": "approval",
    "Not Compliant": "not-compliant",
    "Insufficient Policy Evidence": "insufficient",
}

SAMPLE_QUESTIONS_PATH = Path("data/output/sample_questions.md")


@st.cache_data
def load_sample_questions() -> list[str]:
    """Load one sample question per line from the project content file."""
    if not SAMPLE_QUESTIONS_PATH.exists():
        return []
    return [line.strip() for line in SAMPLE_QUESTIONS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_sample_question(question: str) -> None:
    """Populate the main input with a selected example and clear an old result."""
    st.session_state.policy_question_input = question
    st.session_state.selected_sample_question = question
    st.session_state.pop("result", None)


def featured_sample_questions(questions: list[str], offset: int, limit: int = 6) -> list[str]:
    """Select a small rotating, evenly distributed set from the sample-question file."""
    if len(questions) <= limit:
        return questions
    last_index = len(questions) - 1
    return [questions[(round(index * last_index / (limit - 1)) + offset) % len(questions)] for index in range(limit)]


def find_highlighted_document(result: FinalResponse, document: str) -> Path | None:
    """Find the highlighted PDF generated for one cited source document."""
    document_stem = Path(document).stem
    for output_path in result.highlighted_documents:
        path = Path(output_path)
        if path.exists() and path.suffix.lower() == ".pdf" and document_stem in path.stem:
            return path
    return None


def show_highlighted_pdf(result: FinalResponse) -> None:
    """Embed the first cited highlighted PDF at the page containing its evidence."""
    if not result.citations:
        return

    cited_documents = list(dict.fromkeys(citation.document for citation in result.citations))
    document = st.selectbox("Evidence document", cited_documents)
    citation = next(item for item in result.citations if item.document == document)
    highlighted_pdf = find_highlighted_document(result, document)

    if not highlighted_pdf:
        st.info("A highlighted PDF was not created for this source document.")
        return

    encoded_pdf = base64.b64encode(highlighted_pdf.read_bytes()).decode("utf-8")
    page = citation.page or 1
    st.caption(f"Opened at page {page}; matching evidence is highlighted in yellow.")
    components.html(
        f'<iframe src="data:application/pdf;base64,{encoded_pdf}#page={page}&zoom=page-width" '
        'width="100%" height="560" style="border: 1px solid #d0d7de; border-radius: 6px;"></iframe>',
        height=575,
    )
    st.download_button(
        "Download highlighted document",
        data=highlighted_pdf.read_bytes(),
        file_name=highlighted_pdf.name,
        mime="application/pdf",
    )


def show_compliance_summary(result: FinalResponse) -> None:
    """Render the most important decision as a prominent, scannable card."""
    decision = result.compliance_decision
    status_class = STATUS_CLASSES[decision.status]
    risk_class = f"risk-{decision.risk.lower()}"
    approvals = ", ".join(decision.approvals_required) or "No approval required"
    domains = ", ".join(finding.domain.upper() for finding in result.findings) or "General"
    st.markdown(
        f"""
        <div class="status-card {status_class}">
            <p class="status-label">Compliance decision</p>
            <p class="status-value">{html.escape(decision.status)}</p>
            <div class="status-meta">
                <span class="pill {risk_class}">Risk: {html.escape(decision.risk)}</span>
                <span class="pill">Domains: {html.escape(domains)}</span>
                <span class="pill">{html.escape(approvals)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_detailed_answer(result: FinalResponse) -> None:
    """Render the formatted answer with emphasized labels for quick scanning."""
    decision = result.compliance_decision
    approvals = ", ".join(decision.approvals_required) or "None"
    evidence_lines = []
    for citation in result.citations:
        page = f", page {citation.page}" if citation.page else ""
        section = f", {citation.section}" if citation.section else ""
        evidence_lines.append(f"[{citation.id}] {citation.document}{page}{section}")
    fields = [
        ("Compliance Status", decision.status),
        ("Reasoning", decision.reasoning),
        ("Risk", decision.risk),
        ("Recommended Next Action", decision.recommended_next_action),
        ("Approvals Required", approvals),
        ("Evidence", "<br>".join(html.escape(line) for line in evidence_lines) or "No citations available."),
    ]
    answer_html = "".join(
        f'<p class="answer-item"><span class="answer-heading">{label}:</span><br>{html.escape(value) if label != "Evidence" else value}</p>'
        for label, value in fields
    )
    st.markdown(f'<div class="detailed-answer">{answer_html}</div>', unsafe_allow_html=True)


def show_workflow_history() -> None:
    """Keep completed agent activity visible after a Streamlit page refresh."""
    workflow_steps = st.session_state.get("workflow_steps", [])
    if not workflow_steps:
        return
    with st.expander("Review process", expanded=False):
        for step in workflow_steps:
            st.write(f"[Done] {step}")


def scroll_to_result() -> None:
    """Bring the completed decision into view after Streamlit has painted it."""
    components.html(
        """
        <script>
            let attempts = 0;
            const scrollToDecision = () => {
                const appDocument = window.parent.document;
                const result = appDocument.getElementById('policy-result');
                if (result) {
                    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    return;
                }
                attempts += 1;
                if (attempts < 20) {
                    window.setTimeout(scrollToDecision, 150);
                }
            };
            window.setTimeout(scrollToDecision, 350);
        </script>
        """,
        height=1,
    )


def run_question(question: str) -> FinalResponse:
    """Run the LangGraph and show each completed workflow stage."""
    final_result: FinalResponse | None = None
    st.session_state.workflow_steps = []
    with st.status(NODE_MESSAGES["supervisor"], expanded=True) as status:
        for update in policy_graph.stream({"question": question, "domain_findings": []}, stream_mode="updates"):
            node_name, node_output = next(iter(update.items()))
            st.session_state.workflow_steps.append(NODE_MESSAGES[node_name])
            st.write(f"✓ {NODE_MESSAGES[node_name]}")
            if node_name == "supervisor":
                next_node = node_output["pending_agents"][0] if node_output["pending_agents"] else "merge"
                status.update(label=NODE_MESSAGES[next_node], state="running")
            elif node_name == "response":
                final_result = FinalResponse.model_validate(node_output["final_result"])
            else:
                pending_agents = node_output.get("pending_agents", [])
                next_node = pending_agents[0] if pending_agents else NEXT_NODES.get(node_name, "response")
                status.update(label=NODE_MESSAGES[next_node], state="running")
        status.update(label="Policy review complete", state="complete", expanded=False)

    if final_result is None:
        raise RuntimeError("The policy workflow did not produce a final response.")
    return final_result


def main() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>Enterprise Policy Compliance Assistant</h1>
            <p>Ask a policy question or check a proposed action against your indexed enterprise policies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    sample_offset = st.session_state.get("sample_question_offset", 0)
    sample_questions = featured_sample_questions(load_sample_questions(), sample_offset)
    question_column, sample_column = st.columns((2, 1), gap="large")
    with question_column:
        with st.form("policy_question"):
            question = st.text_area(
                "Your question",
                placeholder="Example: I lost my company laptop. What should I do?",
                height=155,
                key="policy_question_input",
            )
            submitted = st.form_submit_button("Check compliance", type="primary")

    with sample_column:
        if sample_questions:
            st.markdown(
                """
                <div class="sample-callout">
                    <h3>Try a sample question</h3>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                for index, sample_question in enumerate(sample_questions):
                    st.button(
                        sample_question,
                        key=f"sample_question_{index}",
                        on_click=choose_sample_question,
                        args=(sample_question,),
                        use_container_width=True,
                    )

    if submitted:
        with question_column:
            if not question.strip():
                st.warning("Enter a policy question first.")
            else:
                try:
                    st.session_state.result = run_question(question.strip())
                    st.session_state.scroll_to_result = True
                    if st.session_state.get("selected_sample_question") == question.strip():
                        st.session_state.sample_question_offset = sample_offset + 1
                        st.session_state.pop("selected_sample_question", None)
                        st.rerun()
                except Exception as error:
                    st.error(f"Unable to complete the policy review: {error}")

    if not submitted:
        with question_column:
            show_workflow_history()

    result = st.session_state.get("result")
    if result:
        st.markdown('<div id="policy-result"></div>', unsafe_allow_html=True)
        st.divider()
        answer_column, document_column = st.columns((1, 1))
        with answer_column:
            show_compliance_summary(result)
            st.markdown("#### Detailed answer")
            with st.container(border=True):
                show_detailed_answer(result)
            with st.expander("View full JSON result"):
                st.json(result.model_dump(mode="json"))
        with document_column:
            st.subheader("Highlighted policy evidence")
            show_highlighted_pdf(result)

        if st.button("Ask a new question"):
            st.session_state.pop("result", None)
            st.session_state.pop("workflow_steps", None)
            st.rerun()

        if st.session_state.pop("scroll_to_result", False):
            scroll_to_result()


if __name__ == "__main__":
    main()
