from __future__ import annotations

from ..util import fmt_inr, fmt_ts
from .base import AgentResult, BaseAgent


class FraudAgent(BaseAgent):
    """Locates and scores transactions, proposes blocking and disputes. Scoring is rules + a statistical model, never an LLM."""
    name = "fraud"

    def _report_fraud(self, ent) -> AgentResult:
        r = self.call("find_transaction", customer_id=self.cid, txn_id=ent.get("txn_id"), amount=ent.get("amount"))
        if not r.ok:
            return self.fail("report_fraud", r)
        d = r.data
        if not d["found"]:
            return AgentResult(self.name, "report_fraud", "needs_input",
                               "I couldn't find a recent debit matching that. Please give me the exact amount or the transaction ID (like T900001).",
                               {"searched": d["strategy"]}, missing=["txn_id", "amount"])
        t = d["transaction"]
        s = self.call("score_transaction", txn_id=t["txn_id"])
        if not s.ok:
            return self.fail("report_fraud", s)
        sc = s.data
        if d["strategy"] == "recent" and sc["decision"] == "allow":
            return AgentResult(self.name, "report_fraud", "needs_input",
                               "I checked your recent payments and nothing looks unusual. Tell me the amount or transaction ID of the one you don't recognise.",
                               {"checked": d["candidates"], "highest_score": sc["score"]}, missing=["txn_id", "amount"])
        dev = self.call("get_device_history", customer_id=self.cid)
        unregistered = dev.data.get("unregistered_devices", []) if dev.ok else []
        cards = self.call("get_card_status", customer_id=self.cid)
        card = None
        if cards.ok:
            active = [c for c in cards.data["cards"] if c["status"] == "active"]
            card = next((c for c in active if c["account_id"] == t["account_id"]), active[0] if active else None)

        proposed, steps = [], []
        if sc["decision"] != "allow" and card:
            b = self.call("block_card", card_id=card["card_id"], reason=f"suspected fraud on {t['txn_id']}")
            if b.status == "approval_required":
                proposed.append(b.proposed)
                steps.append(b.proposed["summary"])
        dsp = self.call("create_dispute", txn_id=t["txn_id"], reason="customer does not recognise the transaction")
        if dsp.status == "approval_required":
            proposed.append(dsp.proposed)
            steps.append(dsp.proposed["summary"])

        where = f" ({t['country']})" if t.get("country") and t["country"] != "IN" else ""
        lines = [f"I found it: {fmt_inr(t['amount'])} at {t['merchant']}{where} on {fmt_ts(t['ts'])}."]
        verdict = {"block": "high risk, blocking is recommended", "review": "elevated risk", "allow": "consistent with your usual activity"}[sc["decision"]]
        lines.append(f"Risk score: {sc['score']}/100 ({verdict}).")
        why = [x["detail"] for x in sc["reasons"] if x["code"] != "ANOMALY_MODEL"]
        if why:
            lines.append("Why: " + "; ".join(why) + ".")
        if steps:
            lines.append("Proposed (needs your confirmation): " + "; ".join(f"{i}) {x}" for i, x in enumerate(steps, 1)) + ".")
        facts = {"transaction": {k: t[k] for k in ("txn_id", "amount", "merchant", "country", "ts")}, "risk_score": sc["score"],
                 "decision": sc["decision"], "reasons": [{"code": x["code"], "detail": x["detail"], "points": x["points"]} for x in sc["reasons"]],
                 "matched_by": d["strategy"], "card_last4": card["last4"] if card else None,
                 "device_registered": t.get("device_id") not in unregistered}
        return AgentResult(self.name, "report_fraud", "ok", "\n".join(lines), facts, proposed=proposed)

    def _block_card(self, ent) -> AgentResult:
        cards = self.call("get_card_status", customer_id=self.cid)
        if not cards.ok:
            return self.fail("block_card", cards)
        lst = cards.data["cards"]
        last4 = ent.get("card_last4")
        card = next((c for c in lst if c["last4"] == last4), None) if last4 else None
        card = card or next((c for c in lst if c["status"] == "active"), None)
        if not card:
            blocked = [c for c in lst if c["status"] == "blocked"]
            msg = f"Your card ending {blocked[0]['last4']} is already blocked." if blocked else "I couldn't find a card on this profile."
            return AgentResult(self.name, "block_card", "ok", msg, {"cards": lst})
        if card["status"] == "blocked":
            return AgentResult(self.name, "block_card", "ok", f"Your card ending {card['last4']} is already blocked.", {"card": card})
        b = self.call("block_card", card_id=card["card_id"], reason="customer request")
        if b.status != "approval_required":
            return self.fail("block_card", b)
        return AgentResult(self.name, "block_card", "ok",
                           f"I can block your card ending {card['last4']}. Blocking stops all new card payments immediately; please confirm.",
                           {"card_last4": card["last4"]}, proposed=[b.proposed])

    def _assess_recent_risk(self, ent) -> AgentResult:
        r = self.call("assess_recent_risk", customer_id=self.cid)
        if not r.ok:
            return self.fail("assess_recent_risk", r)
        d = r.data
        if d["elevated"]:
            top = d["flagged"][0] if d["flagged"] else {}
            msg = (f"{d['flagged_count']} of the last {d['transactions_checked']} transactions ({d['lookback_days']} days) were flagged; "
                   f"highest risk score {d['max_score']}/100" + (f" ({fmt_inr(top['amount'])} at {top['merchant']})." if top else "."))
        else:
            msg = f"No elevated fraud signals in the last {d['lookback_days']} days ({d['transactions_checked']} transactions checked)."
        return AgentResult(self.name, "assess_recent_risk", "ok", msg, d)
