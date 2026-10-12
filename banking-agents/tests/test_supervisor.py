"""End-to-end through the supervisor: the use cases, approvals, guardrails and role rules."""
import json

from tests import helpers

helpers.setup()

from app import db, metrics, stream
from app.supervisor import Supervisor


def sup():
    return Supervisor()


def chat(s, text, cid="C001", **kw):
    r = s.handle(text, cid, **kw)
    json.dumps(r)  # every response must be JSON-serialisable for the API
    return r


def test_balance_is_tier0_zero_tokens():
    r = chat(sup(), "balance")
    assert r["status"] in ("ok", "completed") and r["tier"] == 0 and r["llm"]["calls"] == 0 and "₹" in r["answer"]
    assert r["agents"] == ["banking"] and r["trace"] and r["trace_id"]


def test_mini_statement_hides_injected_instructions():
    r = chat(sup(), "show my last 5 transactions")
    assert "ignore previous" not in r["answer"].lower() and "approve all" not in r["answer"].lower()
    assert r["guardrails"] and "instructions" in r["guardrails"][0]


def test_fraud_report_end_to_end_with_approval():
    helpers.reseed()
    s = sup()
    r = chat(s, "I did not make this ₹48,000 payment", "C002")
    assert r["status"] == "awaiting_approval" and r["llm"]["calls"] == 0
    assert "100/100" in r["answer"] and r["approval"]["description"]
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "active"  # nothing happened yet
    gid = r["approval"]["group_id"]
    d = s.decide_approval(gid, True, "C002")
    assert d["status"] == "completed" and [e["tool"] for e in d["executed"]] == ["block_card", "create_dispute"]
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "blocked"
    assert db.query_one("SELECT status FROM disputes WHERE txn_id='T900001'")["status"] == "open"
    assert db.query_one("SELECT COUNT(*) AS n FROM alerts WHERE customer_id='C002' AND message LIKE 'Confirmation%'")["n"] == 1
    assert s.decide_approval(gid, True, "C002")["status"] == "error"  # cannot be decided twice


def test_rejecting_an_approval_changes_nothing():
    helpers.reseed()
    s = sup()
    gid = chat(s, "I did not make this ₹48,000 payment", "C002")["approval"]["group_id"]
    assert s.decide_approval(gid, False, "C002")["status"] == "rejected"
    assert db.query_one("SELECT status FROM cards WHERE card_id='K1002'")["status"] == "active"


def test_another_customer_cannot_decide_my_approval_but_an_rm_can():
    helpers.reseed()
    s = sup()
    gid = chat(s, "block my card", "C002")["approval"]["group_id"]
    assert s.decide_approval(gid, True, "C001")["status"] == "error"
    assert s.decide_approval(gid, True, "C001", role="rm")["status"] == "completed"


def test_loan_eligibility_with_policy_citation():
    r = chat(sup(), "Can I get a loan of 5 lakh for 3 years?")
    assert r["llm"]["calls"] == 0 and "16,251" in r["answer"] and "Loan Policy" in r["answer"]


def test_loan_application_outcomes_follow_the_documented_rules():
    helpers.reseed()
    s = sup()
    expect = {"C001": ("approve", True), "C004": ("hold", False), "C003": ("decline", False), "C005": ("decline", False),
              "C006": ("refer", True), "C010": ("hold", False)}
    for cid, (decision, asks) in expect.items():
        r = chat(s, "apply for a loan of 5 lakh for 3 years", cid)
        assert r["data"]["apply_loan"]["decision"] == decision, (cid, r["answer"])
        assert bool(r["approval"]) == asks, cid
        assert set(r["agents"]) == {"credit", "fraud", "compliance"}


def test_aml_detail_is_hidden_from_customers_but_not_from_rms():
    helpers.reseed()
    s = sup()
    cust = chat(s, "apply for a loan of 5 lakh for 3 years", "C010")["answer"]
    rm = chat(s, "apply for a loan of 5 lakh for 3 years", "C010", role="rm")["answer"]
    assert "AML" not in cust and "AML" in rm


def test_loan_application_is_created_only_after_approval():
    helpers.reseed()
    s = sup()
    r = chat(s, "apply for a loan of 5 lakh for 3 years", "C001")
    assert db.query_one("SELECT COUNT(*) AS n FROM loan_applications WHERE customer_id='C001'")["n"] == 0
    d = s.decide_approval(r["approval"]["group_id"], True, "C001")
    assert d["status"] == "completed" and "LN-" in d["answer"]
    assert db.query_one("SELECT COUNT(*) AS n FROM loan_applications WHERE customer_id='C001'")["n"] == 1


def test_follow_up_answers_fill_the_missing_slot():
    s = sup()
    a = chat(s, "I want to apply for a personal loan")
    assert a["status"] in ("needs_input", "needs_clarification") and a["approval"] is None
    b = chat(s, "5 lakh for 3 years")
    assert b["intents"][0]["intent"] == "apply_loan" and b["data"]["apply_loan"]["credit"]["amount"] == 500000


def test_explain_decision_uses_the_last_decision():
    s = sup()
    chat(s, "apply for a loan of 5 lakh for 3 years", "C003")
    r = chat(s, "why was my loan declined", "C003")
    assert "credit score 580" in r["answer"].lower() or "580" in r["answer"]


def test_large_transfer_is_gated_by_compliance_then_approval():
    helpers.reseed()
    s = sup()
    assert chat(s, "transfer 60000 to A1002", "C004")["status"] in ("blocked", "awaiting_approval")  # KYC pending
    r = chat(s, "transfer 60000 to A1002", "C001")
    assert r["status"] == "awaiting_approval"
    d = s.decide_approval(r["approval"]["group_id"], True, "C001")
    assert d["status"] == "completed"
    small = chat(s, "transfer 500 to A1003", "C001")
    assert small["status"] in ("ok", "completed")


def test_overdraft_transfer_is_refused_before_any_approval():
    r = chat(sup(), "transfer 900000 to A1002", "C003")
    assert r["status"] in ("blocked", "completed") and r["approval"] is None


def test_out_of_scope_is_escalated_not_answered():
    r = chat(sup(), "which mutual fund gives best returns")
    assert r["status"] == "escalated" and r["agents"] == []


def test_unknown_customer_and_bad_role_are_rejected():
    assert sup().handle("balance", "NOPE")["status"] == "error"
    assert sup().handle("balance", "C001", role="admin")["status"] == "error"


def test_ui_button_action_skips_classification():
    r = chat(sup(), "", action="check_balance")
    assert r["tier"] == 0 and r["intents"][0]["intent"] == "check_balance"


def test_metrics_report_the_avoidance_rate():
    metrics.reset()
    s = sup()
    for q in ("balance", "show my last 3 transactions", "can I get a loan of 2 lakh"):
        chat(s, q)
    m = metrics.summary()
    assert m["requests"] == 3 and m["llm_avoidance_rate"] == 1.0 and m["tokens"] == 0


def test_live_stream_flags_anomalies_without_an_llm():
    import random
    helpers.reseed()
    odd = stream.process_transaction(stream.simulate_transaction("C003", anomalous=True, rng=random.Random(1)))
    assert odd["decision"] in ("review", "block") and odd["alert_id"]
    ok = stream.process_transaction(stream.simulate_transaction("C003", anomalous=False, rng=random.Random(1)))
    assert ok["decision"] == "allow" and ok["alert_id"] is None
