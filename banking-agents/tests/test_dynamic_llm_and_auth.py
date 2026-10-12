"""Comprehensive Tests for LLM-Driven Dynamic Tool Selection, Multi-Agent Collaboration,
Authentication, Customer Data Isolation, and Human Approval Gate.
"""
import pytest
from app.handlers import startup, chat, decide_approval, pending_approvals, login, customer, balance, HandlerError
from app.supervisor.workflow_state import WorkflowState
from tests import helpers


@pytest.fixture(scope="module", autouse=True)
def init_suite():
    helpers.setup()
    startup(seed_if_missing=True)


class TestGreetingsAndDialogue:
    """Verifies requirement: Simple greetings receive natural conversational responses

    without invoking unnecessary banking tools or being rejected by restrictive classifiers.
    """

    @pytest.mark.parametrize("greeting", [
        "Hi",
        "Hey",
        "Hello",
        "Good morning",
        "How are you?",
    ])
    def test_greetings_return_conversational_response_without_tools(self, greeting: str):
        res = chat({"message": greeting, "customer_id": "C001", "role": "customer"})
        answer = res.get("answer") or res.get("final_answer") or ""
        assert len(answer) > 10, f"Greeting '{greeting}' returned empty or short answer"
        assert "Fingent" in answer or "assist" in answer or "Hello" in answer or "Good" in answer
        
        # Verify 0 banking tools were invoked for a greeting
        summary = res.get("execution_summary", {})
        acts = summary.get("act", [])
        assert len(acts) == 0, f"Greeting '{greeting}' unexpectedly invoked banking tools: {acts}"
        assert res.get("workflow_state") == WorkflowState.COMPLETED.value


class TestDynamicToolSelectionAndParaphrasing:
    """Verifies requirement: LLM dynamically selects tools from intent and entities,

    supports varied paraphrasing, and handles multi-intent compound requests.
    """

    def test_multi_intent_compound_request(self):
        """Use Case 1: Balance and Mini-Statement in a single query."""
        res = chat({
            "message": "What is my balance, and show me my last five transactions?",
            "customer_id": "C001",
            "role": "customer"
        })
        summary = res.get("execution_summary", {})
        executed_tools = [a.get("tool") for a in summary.get("act", [])]
        
        # Both tools must be invoked dynamically
        assert "check_balance" in executed_tools, "check_balance tool not invoked"
        assert "mini_statement" in executed_tools, "mini_statement tool not invoked"
        
        answer = res.get("answer") or res.get("final_answer") or ""
        assert "balance" in answer.lower()
        assert "transaction" in answer.lower()

    def test_paraphrased_balance_query(self):
        """Paraphrase: 'Can you check how much money I have left?'"""
        res = chat({
            "message": "Can you check how much money I have left?",
            "customer_id": "C001",
            "role": "customer"
        })
        executed_tools = [a.get("tool") for a in res.get("execution_summary", {}).get("act", [])]
        assert "check_balance" in executed_tools
        answer = res.get("answer", "")
        assert "savings" in answer.lower() or "balance" in answer.lower()

    def test_paraphrased_recent_spending_query(self):
        """Paraphrase: 'Show me what I spent recently.'"""
        res = chat({
            "message": "Show me what I spent recently.",
            "customer_id": "C001",
            "role": "customer"
        })
        executed_tools = [a.get("tool") for a in res.get("execution_summary", {}).get("act", [])]
        assert "mini_statement" in executed_tools

    def test_emi_calculation_with_varied_phrasing(self):
        """Use Case 3: Loan eligibility and EMI calculation."""
        res = chat({
            "message": "Can I apply for a 500000 loan over 36 months? What would the EMI be?",
            "customer_id": "C001",
            "role": "customer"
        })
        executed_tools = [a.get("tool") for a in res.get("execution_summary", {}).get("act", [])]
        assert "loan_eligibility" in executed_tools
        assert "calculate_emi" in executed_tools
        answer = res.get("answer", "")
        assert "16,251" in answer or "emi" in answer.lower()


class TestAmbiguityAndOutOfScopeSafeguards:
    """Verifies requirement: Ambiguous requests ask clarification; out-of-scope requests

    honestly decline and escalate without fabricating financial actions.
    """

    def test_ambiguous_help_request(self):
        res = chat({"message": "Help me with my money.", "customer_id": "C001", "role": "customer"})
        assert res.get("status") == "needs_clarification"
        assert res.get("workflow_state") == WorkflowState.NEEDS_CLARIFICATION.value
        answer = res.get("answer", "")
        assert "clarify" in answer.lower() or "assist with" in answer.lower()
        acts = res.get("execution_summary", {}).get("act", [])
        assert len(acts) == 0

    def test_out_of_scope_investment_request(self):
        res = chat({"message": "Invest all my savings for me.", "customer_id": "C001", "role": "customer"})
        assert res.get("status") == "escalated"
        assert res.get("workflow_state") == WorkflowState.ESCALATED.value
        answer = res.get("answer", "")
        assert "investment" in answer.lower() or "outside supported" in answer.lower()
        acts = res.get("execution_summary", {}).get("act", [])
        assert len(acts) == 0


class TestAuthenticationAndCustomerIsolation:
    """Verifies requirement: Server-side authentication and customer data isolation."""

    def test_customer_login_and_valid_session(self):
        auth_res = login("C001", "password123")
        assert auth_res.get("ok") is True
        token = auth_res.get("token")
        assert token and token.startswith("nxt_")
        assert auth_res.get("user", {}).get("customer_id") == "C001"

    def test_invalid_login_rejected(self):
        with pytest.raises(HandlerError) as exc_info:
            login("C001", "wrongpassword")
        assert exc_info.value.status == 401

    def test_customer_isolation_blocks_cross_customer_access(self):
        auth_res = login("C001", "password123")
        token = auth_res["token"]

        # C001 can access own data
        cust1 = customer("C001", token=token)
        assert cust1["customer_id"] == "C001"

        # C001 cannot access C002's data
        with pytest.raises(HandlerError) as exc_info:
            customer("C002", token=token)
        assert exc_info.value.status == 403
        assert "Access denied" in exc_info.value.message

    def test_supervisor_accesses_all_customer_records(self):
        auth_res = login("supervisor", "admin123")
        token = auth_res["token"]
        assert auth_res.get("user", {}).get("role") == "supervisor"

        # Supervisor can view C001 and C002
        cust1 = customer("C001", token=token)
        cust2 = customer("C002", token=token)
        assert cust1["customer_id"] == "C001"
        assert cust2["customer_id"] == "C002"


class TestHumanApprovalWorkflowAndIdempotency:
    """Verifies requirement: Sensitive write operations gate behind approvals,

    execute strictly once upon approval, and reject duplicate execution attempts.
    """

    def test_dispute_approval_gate_lifecycle(self):
        helpers.reseed()
        # Trigger an investigation for an existing transaction
        res = chat({
            "message": "I do not recognise transaction T000150 of 2243. Please investigate it.",
            "customer_id": "C001",
            "role": "customer"
        })
        approval = res.get("approval")
        assert approval is not None, "Expected approval gate for disputing transaction"
        group_id = approval.get("group_id")
        assert group_id and group_id.startswith("APR-")

        # Verify it appears in pending approvals
        pending = pending_approvals("C001")
        pending_ids = [p["group_id"] for p in pending]
        assert group_id in pending_ids

        # Decision: Approve the action
        dec_res = decide_approval(group_id, {"approve": True, "customer_id": "C001", "role": "customer"})
        assert dec_res.get("status") == "completed"
        executed = dec_res.get("executed", [])
        assert len(executed) > 0
        assert executed[0].get("tool") == "create_dispute"
        assert executed[0].get("status") == "ok"

        # Verify it is no longer pending
        pending_after = pending_approvals("C001")
        assert group_id not in [p["group_id"] for p in pending_after]

        # Verify idempotency: duplicate decision is rejected
        dup_res = decide_approval(group_id, {"approve": True, "customer_id": "C001", "role": "customer"})
        assert dup_res.get("status") == "error"
        assert "already decided" in dup_res.get("message", "")


class TestMultiAgentLoanWorkflow:
    """Verifies Use Case 4: Coordinated Credit, Fraud, and Compliance specialist agents."""

    def test_multi_agent_loan_application_workflow(self):
        res = chat({
            "message": "Check my eligibility and prepare a loan application for 500000 over 36 months.",
            "customer_id": "C001",
            "role": "customer"
        })
        summary = res.get("execution_summary", {})
        executed_tools = [a.get("tool") for a in summary.get("act", [])]

        # Verify Credit agent, Fraud agent, and Compliance agent tools executed
        assert "apply_loan" in executed_tools
        assert "assess_recent_risk" in executed_tools
        assert "loan_gate" in executed_tools

        # Verify approval gate required before formal write submission
        assert res.get("approval") is not None
        assert "create_loan_application" in [a.get("tool") for a in res["approval"].get("actions", [])]
