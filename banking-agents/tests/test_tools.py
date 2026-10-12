"""The permission boundary: allowlist, schema, ownership, approval gate, replay protection, audit."""
from tests import helpers

helpers.setup()

from app import db
from app.state import Session
from app.tools import approvals, audit, definitions  # noqa: F401
from app.tools.registry import ToolContext, call_tool, tools_for


def ctx(agent, cid="C002", role="customer", group=None, trace="t-test"):
    return ToolContext(trace, agent, Session(cid, role), group)


def test_agent_cannot_call_tools_outside_its_allowlist():
    r = call_tool(ctx("fraud"), "get_balance", {"account_id": "A1002"})
    assert r.status == "permission_denied"
    assert call_tool(ctx("banking"), "block_card", {"card_id": "K1002"}).status == "permission_denied"
    assert "create_loan_application" not in tools_for("fraud") and "block_card" not in tools_for("credit")


def test_customer_cannot_read_another_customers_records():
    assert call_tool(ctx("banking", "C002"), "get_balance", {"account_id": "A1001"}).status == "forbidden"
    assert call_tool(ctx("banking", "C002", role="rm"), "get_balance", {"account_id": "A1001"}).ok


def test_schema_rejects_bad_and_extra_arguments():
    assert call_tool(ctx("credit"), "calculate_emi", {"amount": -5, "annual_rate": 10, "tenure_months": 12}).status == "invalid_args"
    assert call_tool(ctx("banking"), "get_balance", {"account_id": "A1002", "sneaky": 1}).status == "invalid_args"


def test_write_tool_needs_approval_and_has_no_side_effect_without_it():
    helpers.reseed()
    r = call_tool(ctx("fraud"), "block_card", {"card_id": "K1002"})
    assert r.status == "approval_required" and r.proposed["tool"] == "block_card"
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "active"


def test_approved_action_runs_once_and_only_with_exact_arguments():
    helpers.reseed()
    prop = call_tool(ctx("fraud"), "block_card", {"card_id": "K1002"}).proposed
    gid = approvals.create_group(trace_id="t", customer_id="C002", role="customer", actions=[prop], description="d")
    assert call_tool(ctx("fraud", group=gid), "block_card", {"card_id": "K1002"}).status == "approval_invalid"  # still pending
    assert approvals.decide(gid, True) and not approvals.decide(gid, True)  # decided exactly once
    assert call_tool(ctx("fraud", group=gid), "block_card", {"card_id": "K1002", "reason": "other"}).status == "approval_invalid"
    assert call_tool(ctx("fraud", group=gid), "block_card", {"card_id": "K1002"}).ok
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "blocked"
    assert call_tool(ctx("fraud", group=gid), "block_card", {"card_id": "K1002"}).status == "approval_invalid"  # replay refused


def test_rejected_action_never_runs():
    helpers.reseed()
    prop = call_tool(ctx("fraud"), "block_card", {"card_id": "K1002"}).proposed
    gid = approvals.create_group(trace_id="t", customer_id="C002", role="customer", actions=[prop], description="d")
    approvals.decide(gid, False)
    assert call_tool(ctx("fraud", group=gid), "block_card", {"card_id": "K1002"}).status == "approval_invalid"
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "active"


def test_small_transfer_runs_but_large_needs_approval():
    helpers.reseed()
    assert call_tool(ctx("banking", "C001"), "transfer_funds", {"from_account": "A1001", "to_account": "A1002", "amount": 1000}).ok
    big = call_tool(ctx("banking", "C001"), "transfer_funds", {"from_account": "A1001", "to_account": "A1002", "amount": 60000})
    assert big.status == "approval_required"


def test_every_call_is_audited_with_masked_arguments():
    call_tool(ctx("banking", trace="t-audit"), "get_balance", {"account_id": "A1002"})
    call_tool(ctx("fraud", trace="t-audit"), "get_balance", {"account_id": "A1002"})  # refused calls are logged too
    rows = audit.for_trace("t-audit")
    assert [r["status"] for r in rows] == ["ok", "permission_denied"]
    call_tool(ctx("notification", trace="t-pii"), "send_alert", {"customer_id": "C002", "message": "acct 123456789012 flagged"})
    assert "123456789012" not in str(audit.for_trace("t-pii"))
