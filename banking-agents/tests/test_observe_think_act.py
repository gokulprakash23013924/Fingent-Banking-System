"""Comprehensive test suite for the Observe-Think-Act multi-agent banking simulator.
Validates all six required banking use cases, workflow state transitions,
self-evaluation, controlled self-correction, approvals, and permissions.
"""
import pytest
from app import handlers, services
from app.supervisor import Supervisor, WorkflowState


def test_use_case_1_balance_and_statement():
    """UC1: Account balance and mini-statement."""
    sup = Supervisor()

    # Balance check
    r1 = sup.handle("What is my account balance?", "C001")
    assert r1["status"] == "completed"
    assert r1["workflow_state"] == WorkflowState.COMPLETED.value
    assert "₹" in r1["answer"]
    assert "A1001" in r1["answer"]
    assert r1["execution_summary"]["observe"]["intent"] == "check_balance"
    assert r1["execution_summary"]["self_evaluation"]["is_valid"] is True

    # Mini-statement
    r2 = sup.handle("Show my last 5 transactions", "C001")
    assert r2["status"] == "completed"
    assert r2["workflow_state"] == WorkflowState.COMPLETED.value
    assert "Last 5 transactions" in r2["answer"] or "transactions on your" in r2["answer"]
    assert r2["execution_summary"]["observe"]["intent"] == "mini_statement"


def test_use_case_2_suspicious_transaction_detection():
    """UC2: Suspicious transaction detection, risk score, and proposed dispute/card block."""
    sup = Supervisor()
    res = sup.handle("I did not make this ₹48,000 payment", "C002")

    assert res["status"] == "awaiting_approval"
    assert res["workflow_state"] == WorkflowState.AWAITING_APPROVAL.value
    assert res["approval"] is not None
    assert "APR-" in res["approval"]["group_id"]
    assert res["execution_summary"]["observe"]["intent"] == "report_fraud"
    assert any(act["tool"] in ("create_dispute", "block_card") for act in res["approval"]["actions"])

    # Test approval execution
    gid = res["approval"]["group_id"]
    dec = sup.decide_approval(gid, True, "C002")
    assert dec["status"] == "completed"
    assert dec["workflow_state"] == WorkflowState.COMPLETED.value
    assert len(dec["executed"]) > 0


def test_use_case_3_loan_eligibility_and_emi():
    """UC3: Loan eligibility and monthly EMI calculation."""
    sup = Supervisor()
    res = sup.handle("Can I get a ₹5 lakh loan for three years?", "C001")

    assert res["status"] == "completed"
    assert res["workflow_state"] == WorkflowState.COMPLETED.value
    assert "eligible" in res["answer"].lower()
    assert "emi" in res["answer"].lower()
    assert res["execution_summary"]["observe"]["intent"] == "loan_eligibility"
    assert res["execution_summary"]["self_evaluation"]["is_valid"] is True


def test_use_case_4_multi_agent_loan_application():
    """UC4: Multi-agent loan underwriting coordinating Credit, Fraud, and Compliance agents."""
    sup = Supervisor()

    # Step 1: Missing tenure triggers clarifying question
    turn1 = sup.handle("I want to apply for a personal loan of ₹5 lakh", "C001", conversation_id="conv-uc4")
    assert turn1["status"] == "needs_clarification"
    assert turn1["workflow_state"] == WorkflowState.NEEDS_CLARIFICATION.value
    assert "tenure" in turn1["answer"].lower()

    # Step 2: Follow-up with tenure triggers parallel underwriting & approval gate
    turn2 = sup.handle("for 3 years", "C001", conversation_id="conv-uc4")
    assert turn2["status"] == "awaiting_approval"
    assert turn2["workflow_state"] == WorkflowState.AWAITING_APPROVAL.value
    assert turn2["approval"] is not None
    assert "loan application" in turn2["approval"]["description"].lower()

    # Verify parallel agents executed
    act_agents = [a["agent"] for a in turn2["execution_summary"]["act"]]
    assert "credit" in act_agents
    assert "fraud" in act_agents
    assert "compliance" in act_agents


def test_use_case_4_compliance_kyc_hold():
    """UC4: Multi-agent loan underwriting holds application when KYC is pending."""
    sup = Supervisor()
    res = sup.handle("apply for a loan of 5 lakh for 3 years", "C004")  # C004 has KYC pending

    assert res["status"] == "completed"
    assert "on hold" in res["answer"].lower()
    assert "kyc" in res["answer"].lower()
    assert res["approval"] is None  # Gate prevented application submission


def test_use_case_5_live_fraud_monitoring():
    """UC5: Synthetic transaction generation and deterministic IsolationForest scoring."""
    # Normal transaction
    norm = handlers.simulate("C001", False)
    assert norm["score"] < 50
    assert norm["decision"] == "allow"

    # Anomalous transaction
    anom = handlers.simulate("C002", True)
    assert anom["score"] >= 70
    assert anom["decision"] in ("review", "block")
    assert anom["alert_id"] is not None


def test_use_case_6_ambiguous_and_unsupported_requests():
    """UC6: Ambiguous queries ask clarification; unsupported advice is escalated."""
    sup = Supervisor()

    # Ambiguous money request
    r_amb = sup.handle("Help me with my money", "C001")
    assert r_amb["status"] == "needs_clarification"
    assert r_amb["workflow_state"] == WorkflowState.NEEDS_CLARIFICATION.value
    assert "?" in r_amb["answer"]

    # Unsupported investment advice
    r_inv = sup.handle("Invest my savings in mutual funds", "C001")
    assert r_inv["status"] == "escalated"
    assert r_inv["workflow_state"] == WorkflowState.ESCALATED.value
    assert "investment advice" in r_inv["answer"].lower()


def test_self_evaluation_and_recovery_safety():
    """Verifies that recovery controller protects against blind retries on financial writes."""
    from app.supervisor.recovery import RecoveryController

    rc = RecoveryController(max_retries=2)
    # Write tools can NEVER be blind-retried
    assert rc.can_safely_retry("transfer_funds", 0, "TOOL_ERROR") is False
    assert rc.can_safely_retry("block_card", 0, "TOOL_ERROR") is False
    assert rc.can_safely_retry("create_dispute", 0, "TOOL_ERROR") is False

    # Read tools can safely be retried within limit
    assert rc.can_safely_retry("get_balance", 0, "TOOL_ERROR") is True
    assert rc.can_safely_retry("get_balance", 2, "TOOL_ERROR") is False

    # Policy violations cannot be retried away
    assert rc.can_safely_retry("get_balance", 0, "POLICY_VIOLATION") is False


def test_customer_data_access_isolation():
    """Verifies customer ownership checks prevent accessing another customer's data."""
    sup = Supervisor()
    # Aarav (C001) cannot operate on Rohan's (C003) account A1003
    r = sup.handle("What is the balance of A1003?", "C001")
    # Should only return A1001 / A2001 or explain ownership restriction
    assert "A1003" not in r["answer"] or "belong to this customer" in r["answer"] or "only access" in r["answer"]
