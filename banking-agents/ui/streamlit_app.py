"""Streamlit User Interface for Intelligent Multi-Agent Banking Simulator.
Implements the Observe–Think–Act Architecture with tier-free natural-language processing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from app import handlers, services
from app.supervisor import Supervisor, WorkflowState

st.set_page_config(
    page_title="Fingent · Multi-Agent Banking Simulator",
    page_icon="🏦",
    layout="wide"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .stApp {
        background-color: #0b0f19;
        color: #f1f5f9;
    }
    .ota-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-state {
        background: #0284c7;
        color: white;
        padding: 3px 8px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-family: monospace;
        font-weight: bold;
    }
    .badge-completed { background: #059669; }
    .badge-approval { background: #d97706; }
    .badge-clarification { background: #4f46e5; }
    .badge-escalated { background: #e11d48; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_supervisor():
    handlers.startup()
    return Supervisor()


sup = get_supervisor()

# --- Sidebar: Persona & Controls ---
with st.sidebar:
    st.title("🏦 Fingent Simulator")
    st.caption("Observe–Think–Act Multi-Agent Architecture")

    customers = handlers.list_customers()
    cust_options = {f"{c['customer_id']} · {c['name']} ({c['city']})": c['customer_id'] for c in customers}
    selected_label = st.selectbox("Active Customer Persona", list(cust_options.keys()))
    customer_id = cust_options[selected_label]

    role = st.radio("Access Role", ["customer", "rm"], index=0, format_func=lambda x: "Customer Mode" if x == "customer" else "Relationship Manager (RM)")

    st.markdown("---")
    st.subheader("Simulated Backend Ledger")
    try:
        cust_profile = handlers.customer(customer_id)
        st.write(f"**Income:** ₹{cust_profile.get('income', 0):,.0f}/mo")
        for acc in cust_profile.get("accounts", []):
            st.metric(f"{acc['type'].title()} ({acc['account_id']})", f"₹{acc['balance']:,.0f}")
        for card in cust_profile.get("cards", []):
            st.write(f"💳 Card ending **{card['last4']}** — `{card['status'].upper()}`")
    except Exception as e:
        st.error(f"Ledger error: {e}")

    st.markdown("---")
    if st.button("Reset Conversation Context"):
        st.session_state.messages = []
        st.rerun()

# --- Main Layout: Tabs ---
tab_chat, tab_approvals, tab_fraud_stream, tab_audit = st.tabs([
    "💬 AI Banking Assistant",
    "🛡️ Human Approval Gate",
    "⚡ Live Fraud Monitoring",
    "📜 Audit Trail"
])

# Initialize session state for chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- TAB 1: Chat & Observe-Think-Act ---
with tab_chat:
    st.subheader("Intelligent Natural-Language Banking Assistant")
    st.caption("Tier-free natural-language understanding with Observe–Think–Act loop & self-evaluation.")

    # Suggested Prompts
    st.markdown("**Sample Banking Queries:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("What is my account balance?"):
            st.session_state.preset_prompt = "What is my account balance?"
        if st.button("Show my last 5 transactions"):
            st.session_state.preset_prompt = "Show my last 5 transactions"
    with col2:
        if st.button("I did not make this ₹48,000 payment"):
            st.session_state.preset_prompt = "I did not make this ₹48,000 payment"
        if st.button("Can I get a ₹5 lakh loan for 3 years?"):
            st.session_state.preset_prompt = "Can I get a ₹5 lakh loan for 3 years?"
    with col3:
        if st.button("I want to apply for a personal loan of ₹5 lakh"):
            st.session_state.preset_prompt = "I want to apply for a personal loan of ₹5 lakh"
        if st.button("Help me with my money (Ambiguous test)"):
            st.session_state.preset_prompt = "Help me with my money"

    # Display Conversation History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                state = msg.get("workflow_state", "COMPLETED")
                state_cls = "badge-completed"
                if state == "AWAITING_APPROVAL": state_cls = "badge-approval"
                elif state == "NEEDS_CLARIFICATION": state_cls = "badge-clarification"
                elif state == "ESCALATED": state_cls = "badge-escalated"

                st.markdown(f'<span class="badge-state {state_cls}">{state}</span>', unsafe_allow_html=True)
                st.markdown(msg["content"])

                # Observe-Think-Act Execution Summary
                summary = msg.get("execution_summary")
                if summary:
                    with st.expander("🔍 Observe–Think–Act Execution Summary"):
                        c_obs, c_think, c_act = st.columns(3)
                        with c_obs:
                            st.markdown("**👁️ OBSERVE**")
                            st.write(f"Goal: {summary.get('observe', {}).get('goal')}")
                            st.write(f"Intent: `{summary.get('observe', {}).get('intent')}`")
                            st.write(f"Entities: {summary.get('observe', {}).get('entities')}")
                        with c_think:
                            st.markdown("**🧠 THINK (Plan)**")
                            st.write(f"Agents: {summary.get('think', {}).get('required_agents')}")
                            st.write(f"Parallel Steps: {summary.get('think', {}).get('parallel_groups')}")
                            st.write(f"Approval Required: {summary.get('think', {}).get('approval_required')}")
                        with c_act:
                            st.markdown("**⚡ ACT & EVALUATE**")
                            st.write(f"Tools Executed: {summary.get('act', [])}")
                            st.write(f"Validations: {summary.get('self_evaluation', {}).get('checks_passed')}")
                            st.write(f"Latency: {summary.get('latency_ms', 0):.1f} ms")

                # Approval card if present
                if msg.get("approval"):
                    appr = msg["approval"]
                    st.warning(f"⚠️ **Approval Required:** {appr['description']}")
                    c_appr, c_rej = st.columns(2)
                    if c_appr.button(f"Approve & Execute ({appr['group_id']})", key=f"appr_{appr['group_id']}"):
                        res = sup.decide_approval(appr["group_id"], True, customer_id, role)
                        st.success(f"Executed: {res['answer']}")
                        st.rerun()
                    if c_rej.button(f"Reject Action", key=f"rej_{appr['group_id']}"):
                        res = sup.decide_approval(appr["group_id"], False, customer_id, role)
                        st.info("Action canceled.")
                        st.rerun()
            else:
                st.markdown(msg["content"])

    # Chat Input
    prompt_val = st.session_state.pop("preset_prompt", None)
    user_input = st.chat_input("Ask about balances, transfers, loans, fraud or card controls...") or prompt_val

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            res = sup.handle(user_input, customer_id=customer_id, role=role, conversation_id=f"conv-{customer_id}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": res["answer"],
                "workflow_state": res.get("workflow_state", "COMPLETED"),
                "execution_summary": res.get("execution_summary"),
                "approval": res.get("approval")
            })
            st.rerun()

# --- TAB 2: Approvals Gate ---
with tab_approvals:
    st.subheader("Human-in-the-Loop Approval Gate")
    st.caption("High-risk and money-moving tools are proposed first and must be authorized by a human.")
    pending = handlers.pending_approvals(customer_id if role == "customer" else None)
    if pending:
        for p in pending:
            with st.container():
                st.markdown(f"### Approval Group `{p['group_id']}`")
                st.write(f"**Customer:** {p['customer_id']} · **Created:** {p['created_at']}")
                st.info(p["description"])
                st.write("**Proposed Tool Actions:**", p["actions"])
                c1, c2 = st.columns([1, 4])
                if c1.button("Confirm & Execute", key=f"tab_appr_{p['group_id']}"):
                    dec = sup.decide_approval(p["group_id"], True, customer_id, role)
                    st.success(dec["answer"])
                    st.rerun()
                if c2.button("Reject", key=f"tab_rej_{p['group_id']}"):
                    dec = sup.decide_approval(p["group_id"], False, customer_id, role)
                    st.info("Action canceled.")
                    st.rerun()
    else:
        st.success("No pending approvals awaiting authorization.")

# --- TAB 3: Live Fraud Stream ---
with tab_fraud_stream:
    st.subheader("Live Transaction Stream & Fraud Simulator (Use Case 5)")
    st.caption("Deterministic IsolationForest risk scoring on synthetic payments without calling an LLM.")
    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("Inject Normal Transaction"):
        sim = handlers.simulate(customer_id, False)
        st.success(f"Normal payment processed: ₹{sim['amount']:,.0f} at {sim['merchant']} (Risk Score: {sim['score']}/100 - {sim['decision'].upper()})")
    if c_btn2.button("Inject Anomalous Fraud Payment"):
        sim = handlers.simulate(customer_id, True)
        st.error(f"Suspicious payment intercepted! ₹{sim['amount']:,.0f} at {sim['merchant']} (Risk Score: {sim['score']}/100 - {sim['decision'].upper()})")
        st.write(f"Reasons: `{sim['reasons']}` · Alert Generated ID: `{sim['alert_id']}`")

    st.markdown("---")
    st.write("**Recent Alerts Feed:**")
    alerts_feed = handlers.alerts(customer_id if role == "customer" else None, limit=10)
    for al in alerts_feed:
        st.write(f"🔔 **[{al.get('severity', 'alert').upper()}]** {al.get('title')}: {al.get('details')} (Customer: {al.get('customer_id')})")

# --- TAB 4: Audit Trail ---
with tab_audit:
    st.subheader("Immutable Audit Trail")
    st.caption("Every tool execution and permission check is logged with PII redaction.")
    audits = handlers.get_audit(None, limit=25)
    st.dataframe(audits, use_container_width=True)
