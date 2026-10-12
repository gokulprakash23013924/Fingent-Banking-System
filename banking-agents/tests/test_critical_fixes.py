"""Automated Regression Suite for Fingent Critical Fixes.

Covers:
- Test 1: Authentication & Role-Based Access Isolation
- Test 2: Credit Score Retrieval ("What is my credit score?")
- Test 3: Supervisor Asking About Another Customer ("What is the bank account balance of Rohan Dass?")
- Test 4: Missing Customer Handling (No Active Customer Substitution)
- Test 5: Customer Isolation (Cross-Customer Access Blocked)
- Test 6: Ordinary Balance Enquiry (No Unnecessary Approval)
- Test 7: Protected Operations & Approval Lifecycle
- Test 8: Honest Execution Status on Failure (Not Falsely Marked Completed)
- Test 9: Customer Identity Mismatch Protection (Data Integrity Gate)
- Test 10: Natural-Language Variations (Greetings, Paraphrases, Multi-Step)
"""
from __future__ import annotations

import pytest
from app import auth, handlers, services
from app.handlers import chat
from app.supervisor.orchestrator import SupervisorOrchestrator
from app.supervisor.workflow_state import ToolExecutionResult, WorkflowState


@pytest.fixture(autouse=True)
def ensure_db():
    from data.seed import seed
    seed(reset=True)
    auth.init_auth_db()


# -----------------------------------------------------------------------------
# Test 1: Login & Role-Based Access Isolation
# -----------------------------------------------------------------------------
def test_1_login_and_role_access():
    # Customer login
    cust_res = handlers.login("C001", "password123")
    assert cust_res["ok"] is True
    assert cust_res["user"]["role"] == "customer"
    cust_token = cust_res["token"]

    # Supervisor login
    sup_res = handlers.login("supervisor", "admin123")
    assert sup_res["ok"] is True
    assert sup_res["user"]["role"] == "supervisor"
    sup_token = sup_res["token"]

    # Customer token cannot view another customer's data
    with pytest.raises(handlers.HandlerError) as exc:
        handlers.customer("C002", cust_token)
    assert exc.value.status == 403

    # Supervisor token CAN view any customer's data
    c2 = handlers.customer("C002", sup_token)
    assert c2["customer_id"] == "C002"


# -----------------------------------------------------------------------------
# Test 2: Credit Score ("What is my credit score?")
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "What is my credit score?",
    "Can you check my CIBIL score?",
    "Do you know my current credit rating?",
    "What score do I have on my credit profile?"
])
def test_2_credit_score_retrieval(query):
    # Customer C001 (Aarav Mehta - Score 780)
    res = chat({"message": query, "customer_id": "C001", "role": "customer"})
    assert res["status"] == "completed"
    answer = res["answer"]

    # Must NOT return the generic "Request processed."
    assert "Request processed." not in answer, "Generic unhelpful response returned!"
    assert "780" in answer, "Actual credit score 780 missing from response!"
    assert any(term in answer.lower() for term in ["cibil", "credit", "rating", "score", "prime", "excellent"])

    # Customer C003 (Rohan Das - Score 580)
    res_c3 = chat({"message": query, "customer_id": "C003", "role": "customer"})
    assert res_c3["status"] == "completed"
    assert "580" in res_c3["answer"], "Rohan's credit score 580 missing!"


# -----------------------------------------------------------------------------
# Test 3: Supervisor Asks About Another Customer
# -----------------------------------------------------------------------------
def test_3_supervisor_asks_about_rohan_dass_while_viewing_aarav():
    # Supervisor is currently viewing Aarav Mehta (C001) in dashboard
    # Supervisor asks for Rohan Dass's balance
    res = chat({
        "message": "What is the bank account balance of Rohan Dass?",
        "customer_id": "C001",
        "role": "supervisor"
    })

    assert res["status"] == "completed"
    answer = res["answer"]

    # Must return Rohan Das's balances (A1003: ₹42,000)
    assert "42,000" in answer or "42000" in answer, "Rohan's balance ₹42,000 not returned!"
    # Must NEVER return Aarav Mehta's balance (₹2,44,501 / ₹80,000)
    assert "2,44,501" not in answer, "Silently leaked Aarav Mehta's balance!"
    assert "245000" not in answer


# -----------------------------------------------------------------------------
# Test 4: Missing Customer
# -----------------------------------------------------------------------------
def test_4_supervisor_missing_customer():
    res = chat({
        "message": "What is the balance of John Doe?",
        "customer_id": "C001",
        "role": "supervisor"
    })

    assert res["status"] in ("failed", "error")
    answer = res["answer"]
    # Must return clear not-found message, without substituting Aarav
    assert "No customer record found matching 'John Doe'" in answer or "not found" in answer.lower()
    assert "2,44,501" not in answer, "Substituted active customer instead of failing!"


# -----------------------------------------------------------------------------
# Test 5: Customer Isolation (Cross-Customer Access Blocked)
# -----------------------------------------------------------------------------
def test_5_customer_cannot_ask_for_rohan_dass_balance():
    # Customer Aarav Mehta (C001) tries to ask for Rohan Dass's balance
    res = chat({
        "message": "What is the bank account balance of Rohan Dass?",
        "customer_id": "C001",
        "role": "customer"
    })

    # Must be denied
    assert res["status"] in ("failed", "error")
    assert "Access denied" in res["answer"] or "Cross-customer" in res["answer"]
    # Must NOT disclose Rohan's balance (42000) or Aarav's balance
    assert "42,000" not in res["answer"]


# -----------------------------------------------------------------------------
# Test 6: Ordinary Balance Enquiry
# -----------------------------------------------------------------------------
def test_6_ordinary_balance_enquiry_requires_no_approval():
    res = chat({
        "message": "What is my balance?",
        "customer_id": "C001",
        "role": "customer"
    })

    assert res["status"] == "completed"
    assert res.get("approval") is None, "Ordinary balance enquiry erroneously sent to approval queue!"
    assert "2,44,501" in res["answer"] or "245000" in res["answer"]


# -----------------------------------------------------------------------------
# Test 7: Protected Operation Approval Lifecycle
# -----------------------------------------------------------------------------
def test_7_protected_operation_requires_approval_and_rejected_never_runs():
    # Customer C002 asks to dispute fraudulent payment
    res = chat({
        "message": "I didn't make this payment of 48000, please open a dispute",
        "customer_id": "C002",
        "role": "customer"
    })

    assert res["status"] == "awaiting_approval"
    approval = res.get("approval")
    assert approval is not None
    group_id = approval["group_id"]

    # Rejecting the approval must not execute the write action
    rej = handlers.decide_approval(group_id, {"approve": False, "role": "supervisor", "customer_id": "C002"}, token=None)
    assert rej["status"] == "rejected"
    assert "rejected" in rej["answer"].lower()

    # Verify dispute was not created in database
    disputes = services.db.query("SELECT * FROM disputes WHERE customer_id='C002'")
    assert len(disputes) == 0, "Rejected dispute action was executed!"


# -----------------------------------------------------------------------------
# Test 8: Honest Execution Status on Tool Failure
# -----------------------------------------------------------------------------
def test_8_honest_execution_status_on_failure(monkeypatch):
    sup = SupervisorOrchestrator()

    # Simulate a tool failure in BankingAgent
    from app.agents.banking import BankingAgent
    def broken_run(self, action, inputs):
        from app.agents.base import AgentResult
        return AgentResult("banking", action, "error", "Simulated core banking gateway failure", {})

    monkeypatch.setattr(BankingAgent, "run", broken_run)

    res = sup.handle("What is my balance?", "C001", "customer")
    assert res["status"] == "failed", "Failed tool execution was falsely marked completed!"
    assert res["workflow_state"].lower() == "failed"
    assert "Simulated core banking gateway failure" in res["answer"] or "failed" in res["answer"].lower()


# -----------------------------------------------------------------------------
# Test 9: Customer Identity Mismatch (Data Integrity Gate)
# -----------------------------------------------------------------------------
def test_9_customer_identity_mismatch_blocks_response(monkeypatch):
    sup = SupervisorOrchestrator()

    # Simulate a compromised or buggy tool that returns C002's data when C001 was requested
    from app.agents.banking import BankingAgent
    def leaky_run(self, action, inputs):
        from app.agents.base import AgentResult
        return AgentResult("banking", action, "ok", "Leaked data", {"customer_id": "C002", "balance": 999999})

    monkeypatch.setattr(BankingAgent, "run", leaky_run)

    res = sup.handle("What is my balance?", "C001", "customer")
    # Must immediately block response and flag DATA INTEGRITY ERROR
    assert res["status"] in ("failed", "error")
    assert "DATA INTEGRITY ERROR" in res["answer"]
    assert "999999" not in res["answer"], "Mismatched customer data was leaked to user!"


# -----------------------------------------------------------------------------
# Test 10: Natural-Language Variations
# -----------------------------------------------------------------------------
def test_10_natural_language_variations():
    # Greeting with zero banking tools
    res_greet = chat({"message": "Good morning! Can you help me?", "customer_id": "C001", "role": "customer"})
    assert res_greet["status"] == "completed"
    act_tools = [a["tool"] for a in res_greet.get("execution_summary", {}).get("act", [])]
    assert len(act_tools) == 0, "Greeting unexpectedly triggered banking tools!"

    # Multi-step balance + statement query
    res_multi = chat({
        "message": "What is my balance and show me my last five transactions?",
        "customer_id": "C001",
        "role": "customer"
    })
    assert res_multi["status"] == "completed"
    multi_tools = [a["tool"] for a in res_multi.get("execution_summary", {}).get("act", [])]
    assert "check_balance" in multi_tools
    assert "mini_statement" in multi_tools


# -----------------------------------------------------------------------------
# Test 11: P2P Money Transfer via Razorpay (Dual Ledger Update)
# -----------------------------------------------------------------------------
def test_11_p2p_razorpay_transfer_updates_both_histories():
    # Record starting balances
    aarav_acc_before = services.get_account("A1001")["balance"]
    diya_acc_before = services.get_account("A1002")["balance"]

    # Aarav Mehta sends money to Diya Nair
    res = chat({
        "message": "i wanted to send money to diya nair 5000",
        "customer_id": "C001",
        "role": "customer"
    })

    assert res["status"] == "completed"
    answer = res["answer"]
    assert "5,000" in answer or "5000" in answer
    assert "Diya Nair" in answer or "A1002" in answer
    assert "Razorpay" in answer

    # Verify sender balance debited
    aarav_acc_after = services.get_account("A1001")["balance"]
    assert aarav_acc_after == aarav_acc_before - 5000

    # Verify recipient balance credited
    diya_acc_after = services.get_account("A1002")["balance"]
    assert diya_acc_after == diya_acc_before + 5000

    # Verify sender transaction history has debit record
    aarav_txns = services.get_transactions("A1001", limit=5)
    sender_txn = aarav_txns[0]
    assert sender_txn["type"] == "debit"
    assert sender_txn["amount"] == 5000
    assert "RAZORPAY TRANSFER TO Diya Nair" in sender_txn["merchant"]
    assert "pay_rzp_" in sender_txn["description"]

    # Verify recipient transaction history has credit record
    diya_txns = services.get_transactions("A1002", limit=5)
    recip_txn = diya_txns[0]
    assert recip_txn["type"] == "credit"
    assert recip_txn["amount"] == 5000
    assert "RAZORPAY TRANSFER FROM Aarav Mehta" in recip_txn["merchant"]
    assert "pay_rzp_" in recip_txn["description"]

