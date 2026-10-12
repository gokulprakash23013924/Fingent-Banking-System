"""The LLM-last ladder: cheap tiers first, LLM only when unsure, graceful when there is no LLM."""
from tests import helpers

helpers.setup()

from app import config
from app.gateway.gateway import Gateway
from app.ladder import Ladder
from app.llm.client import BaseClient, LLMResult
from app.state import RequestState, Session


def run(text, gateway=None, unsure=False):
    st = RequestState.new(Session("C001"), "t", text)
    ladder = UnsureLadder(gateway or Gateway()) if unsure else Ladder(gateway or Gateway())
    return ladder.classify(text, st), st


class UnsureLadder(Ladder):
    """Forces tier 1 to be unsure so these tests do not depend on what the trained classifier happens to say."""

    def _tier1(self, raw):
        return "help", 0.10, {"help": 0.10}


class Scripted(BaseClient):
    """Small model is vague, strong model is sure."""
    name = "scripted"

    def complete(self, **kw):
        if kw["model"] == "mock-small":
            body = '{"intents":[{"intent":"block_card","confidence":0.3}],"clarification":null}'
        else:
            body = '{"intents":[{"intent":"block_card","confidence":0.9}],"clarification":null}'
        return LLMResult(body, kw["model"], 10, 5, 1.0)


class Garbage(BaseClient):
    name = "garbage"

    def complete(self, **kw):
        return LLMResult("this is not json", kw["model"], 10, 5, 1.0)


def test_exact_commands_use_tier_0_and_no_llm():
    res, st = run("balance")
    assert res.tier == 0 and res.items[0].intent == "check_balance" and st.llm_calls == 0


def test_normal_phrasing_is_resolved_by_the_classifier_with_entities():
    res, st = run("Can I get a loan of 5 lakh for 3 years?")
    it = res.items[0]
    assert res.tier == 1 and it.intent == "loan_eligibility" and st.llm_calls == 0
    assert it.entities["amount"] == 500000 and it.entities["tenure_months"] == 36


def test_two_requests_in_one_message_are_split():
    res, st = run("Can I get a loan? I also see a transaction I don't recognize")
    assert [i.intent for i in res.items] == ["loan_eligibility", "report_fraud"] and st.llm_calls == 0


def test_unsure_requests_climb_to_an_llm():
    res, st = run("my card was stolen so make it stop working", unsure=True)
    assert res.tier == 2 and res.items[0].intent == "block_card" and st.routing_calls == 1


def test_a_vague_small_model_escalates_to_the_strong_model():
    res, st = run("my card was stolen so make it stop working", Gateway(client=Scripted()), unsure=True)
    assert res.tier == 3 and st.routing_calls == 2 and [p["tier"] for p in st.tier_path] == [1, 2, 3]


def test_without_an_llm_unsure_requests_become_a_clarifying_question():
    config.runtime["llm_enabled"] = False
    try:
        res, st = run("asdf qwerty")
        assert not res.items and res.clarification and st.llm_calls == 0
    finally:
        config.runtime.pop("llm_enabled", None)


def test_malformed_model_output_is_survived():
    res, st = run("zzz qqq www", Gateway(client=Garbage()))
    assert not res.items and res.clarification  # no crash, no guess


def test_failing_primary_model_falls_back():
    import os
    old = os.environ["LLM_TIER2_MODEL"]
    os.environ["LLM_TIER2_MODEL"] = "mock-fail"
    try:
        res, st = run("my card was stolen so make it stop working", unsure=True)
        assert st.fallback_used and st.models == ["mock-small"] and res.items
    finally:
        os.environ["LLM_TIER2_MODEL"] = old


def test_budget_caps_llm_calls():
    st = RequestState.new(Session("C001"), "t", "x")
    st.budget.max_calls = 0
    res = Ladder(Gateway()).classify("asdf qwerty", st)
    assert st.llm_calls == 0 and not res.items


def test_llm_only_mode_skips_the_cheap_tiers():
    import os
    os.environ["PIPELINE_MODE"] = "llm_only"
    try:
        res, st = run("what is my balance")
        assert st.llm_calls >= 1 and res.tier >= 2
    finally:
        os.environ["PIPELINE_MODE"] = "ladder"
