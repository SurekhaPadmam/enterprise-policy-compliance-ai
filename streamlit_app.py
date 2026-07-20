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
        .hero { padding: 1.8rem 2rem; border-radius: 18px; color: #ffffff;
                background: linear-gradient(115deg, #123a63, #176b68); box-shadow: 0 14px 30px #123a6330; }
        .hero h1 { margin: 0; font-size: 2rem; }
        .hero p { margin: .55rem 0 0; color: #dceefa; font-size: 1.05rem; }
        #policy-result { scroll-margin-top: 1rem; }
        .status-card { border-radius: 16px; padding: 1.35rem 1.5rem; margin-bottom: 1rem;
                       border: 1px solid; box-shadow: 0 7px 18px #172b4d12; }
        .status-label { margin: 0 0 .35rem; font-size: .78rem; font-weight: 700;
                        letter-spacing: .08em; text-transform: uppercase; opacity: .78; }
        .status-value { margin: 0; font-size: 1.7rem; font-weight: 750; }
        .status-meta { display: flex; gap: .65rem; flex-wrap: wrap; margin-top: 1rem; }
        .pill { padding: .3rem .65rem; border-radius: 999px; background: #ffffffa8; font-size: .87rem; font-weight: 600; }
        .allowed { background: #e9f8ef; border-color: #6bc98b; color: #145a32; }
        .conditional, .approval { background: #fff7df; border-color: #e8bf50; color: #79550a; }
        .not-compliant { background: #fff0f0; border-color: #df7474; color: #9e2424; }
        .insufficient { background: #edf1f7; border-color: #94a3b8; color: #334155; }
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
    approvals = ", ".join(decision.approvals_required) or "No approval required"
    domains = ", ".join(finding.domain.upper() for finding in result.findings) or "General"
    st.markdown(
        f"""
        <div class="status-card {status_class}">
            <p class="status-label">Compliance decision</p>
            <p class="status-value">{html.escape(decision.status)}</p>
            <div class="status-meta">
                <span class="pill">Risk: {html.escape(decision.risk)}</span>
                <span class="pill">Domains: {html.escape(domains)}</span>
                <span class="pill">{html.escape(approvals)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    with st.status(NODE_MESSAGES["supervisor"], expanded=True) as status:
        for update in policy_graph.stream({"question": question, "domain_findings": []}, stream_mode="updates"):
            node_name, node_output = next(iter(update.items()))
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

    with st.form("policy_question"):
        question = st.text_area(
            "Your question",
            placeholder="Example: Can I paste customer data into a public AI tool?",
            height=100,
        )
        submitted = st.form_submit_button("Check compliance", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Enter a policy question first.")
        else:
            try:
                st.session_state.result = run_question(question.strip())
                st.session_state.scroll_to_result = True
            except Exception as error:
                st.error(f"Unable to complete the policy review: {error}")

    result = st.session_state.get("result")
    if result:
        st.markdown('<div id="policy-result"></div>', unsafe_allow_html=True)
        st.divider()
        answer_column, document_column = st.columns((1, 1))
        with answer_column:
            show_compliance_summary(result)
            st.markdown("#### Detailed answer")
            with st.container(border=True):
                st.text(result.formatted_answer)
            with st.expander("View full JSON result"):
                st.json(result.model_dump(mode="json"))
        with document_column:
            st.subheader("Highlighted policy evidence")
            show_highlighted_pdf(result)

        if st.button("Ask a new question"):
            st.session_state.pop("result", None)
            st.rerun()

        if st.session_state.pop("scroll_to_result", False):
            scroll_to_result()


if __name__ == "__main__":
    main()
