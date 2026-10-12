from __future__ import annotations

from ..config import get_policy
from ..util import fmt_inr, fmt_ts
from .base import AgentResult, BaseAgent


def _rs(x: float) -> str:
    return fmt_inr(round(x))


def _reasons_text(reasons: list[dict]) -> str:
    t = "; ".join(r["detail"] for r in reasons)
    return t[:1].upper() + t[1:]


class CreditAgent(BaseAgent):
    """Bureau data, rule-engine eligibility, EMI and offers. Decisions are deterministic and reproducible."""
    name = "credit"

    def _assess(self, amount, tenure):
        """Shared by eligibility and application: bureau + rule engine + offers + policy citation."""
        b = self.call("get_bureau_score", customer_id=self.cid)
        if not b.ok:
            return None, self.fail("loan", b)
        e = self.call("check_eligibility", customer_id=self.cid, amount=amount, tenure_months=tenure)
        if not e.ok:
            return None, self.fail("loan", e)
        o = self.call("get_loan_offers", customer_id=self.cid, amount=amount if e.data["decision"] == "approve" else None)
        p = self.call("retrieve_policy", query="loan eligibility credit score affordability foir", k=1)
        cite = None
        if p.ok and p.data["snippets"]:
            s = p.data["snippets"][0]
            cite = f"{s['doc'].replace('.md', '').replace('_', ' ').title()} > {s['section']}"
        return {"bureau": b.data, "elig": e.data, "offers": o.data.get("offers", []) if o.ok else [], "policy": cite}, None

    def _loan_eligibility(self, ent) -> AgentResult:
        amount, tenure = ent.get("amount"), ent.get("tenure_months")
        a, err = self._assess(amount, tenure)
        if err:
            return err
        e, cite = a["elig"], a["policy"]
        facts = {**{k: e[k] for k in ("decision", "rate", "emi", "foir", "max_eligible_amount", "score", "amount", "tenure_months")},
                 "reasons": e["reasons"], "offers": a["offers"][:3], "policy": cite}
        tail = f" (Policy: {cite})" if cite else ""
        if amount is None:
            if e["max_eligible_amount"] > 0 and not e["reasons"]:
                best = next((o for o in a["offers"] if o["tenure_months"] == (tenure or get_policy()["loan"]["default_tenure_months"])), None)
                msg = (f"With a credit score of {e['score']} you can borrow up to {fmt_inr(e['max_eligible_amount'])} at {e['rate']:g}% a year"
                       + (f" (about {_rs(best['emi'])} a month over {best['tenure_months']} months)" if best else "") + f".{tail}")
            else:
                msg = f"You're not eligible for a personal loan right now: {_reasons_text(e['reasons'])}.{tail}"
            return AgentResult(self.name, "loan_eligibility", "ok", msg, facts)
        if e["decision"] == "approve":
            msg = (f"Yes, {fmt_inr(amount)} over {e['tenure_months']} months looks eligible: EMI {_rs(e['emi'])} at {e['rate']:g}% a year, "
                   f"and your obligations would be {e['foir'] * 100:.0f}% of income.{tail}")
        else:
            msg = f"{fmt_inr(amount)} over {e['tenure_months']} months isn't eligible: {_reasons_text(e['reasons'])}."
            if e["max_eligible_amount"] > 0:
                msg += f" You could qualify for up to {fmt_inr(e['max_eligible_amount'])} instead."
            msg += tail
        return AgentResult(self.name, "loan_eligibility", "ok", msg, facts)

    def _apply_loan(self, ent) -> AgentResult:
        """Credit leg of the loan application playbook: assess only. The supervisor combines it with Fraud and Compliance."""
        amount = ent.get("amount")
        if not amount:
            return AgentResult(self.name, "apply_loan", "needs_input",
                               "How much would you like to borrow, and for how long? For example: 5 lakh for 3 years.",
                               {}, missing=["amount"])
        tenure = ent.get("tenure_months") or get_policy()["loan"]["default_tenure_months"]
        a, err = self._assess(amount, tenure)
        if err:
            return err
        e = a["elig"]
        facts = {**{k: e[k] for k in ("decision", "rate", "emi", "foir", "max_eligible_amount", "score", "amount", "tenure_months")},
                 "reasons": e["reasons"], "policy": a["policy"]}
        if e["decision"] == "approve":
            msg = f"Credit: eligible. EMI {_rs(e['emi'])} at {e['rate']:g}% for {e['tenure_months']} months (score {e['score']})."
        else:
            msg = f"Credit: not eligible. {_reasons_text(e['reasons'])}."
            if e["max_eligible_amount"] > 0:
                msg += f" Up to {fmt_inr(e['max_eligible_amount'])} would fit."
        return AgentResult(self.name, "apply_loan", "ok", msg, facts)

    def propose_application(self, facts: dict, status: str, reason: str) -> list:
        r = self.call("create_loan_application", customer_id=self.cid, amount=float(facts["amount"]),
                      tenure_months=int(facts["tenure_months"]), rate=facts.get("rate"), emi=facts.get("emi"),
                      status=status, reason=reason[:200])
        return [r.proposed] if r.status == "approval_required" else []

    def _calculate_emi(self, ent) -> AgentResult:
        amount = ent.get("amount")
        if not amount:
            return AgentResult(self.name, "calculate_emi", "needs_input",
                               "For which loan amount and tenure? For example: EMI for 5 lakh over 3 years.", {}, missing=["amount"])
        tenure = ent.get("tenure_months") or get_policy()["loan"]["default_tenure_months"]
        rate, source = ent.get("rate"), "your rate"
        if rate is None:
            b = self.call("get_bureau_score", customer_id=self.cid)
            from ..rules import rate_for_score
            rate = rate_for_score(b.data["score"]) if b.ok else None
            source = "the rate for your credit score"
            if rate is None:
                rate, source = 14.0, "the standard rate"
        r = self.call("calculate_emi", amount=float(amount), annual_rate=float(rate), tenure_months=int(tenure))
        if not r.ok:
            return self.fail("calculate_emi", r)
        d = r.data
        msg = (f"EMI for {fmt_inr(d['amount'])} over {d['tenure_months']} months at {d['annual_rate']:g}% a year ({source}): "
               f"{_rs(d['emi'])} a month. Total payable {_rs(d['total_payable'])}, of which interest is {_rs(d['total_interest'])}.")
        return AgentResult(self.name, "calculate_emi", "ok", msg, d)

    def _loan_status(self, ent) -> AgentResult:
        r = self.call("list_loan_applications", customer_id=self.cid)
        if not r.ok:
            return self.fail("loan_status", r)
        apps = r.data["applications"]
        if not apps:
            return AgentResult(self.name, "loan_status", "ok", "You have no loan applications yet.", {"applications": []})
        lines = [f"• {a['app_id']}: {fmt_inr(a['amount'])} over {a['tenure_months']} months, {a['status'].replace('_', ' ')} (submitted {fmt_ts(a['created_at'])})" for a in apps[:5]]
        return AgentResult(self.name, "loan_status", "ok", "Your loan applications:\n" + "\n".join(lines), {"applications": apps[:5]})

    def _credit_score(self, ent) -> AgentResult:
        b = self.call("get_credit_profile", customer_id=self.cid)
        if not b.ok:
            # Fallback to get_bureau_score
            b = self.call("get_bureau_score", customer_id=self.cid)
        if not b.ok:
            return AgentResult(self.name, "credit_score", "error", f"Credit score record is currently unavailable for customer {self.cid}.", {})

        score = b.data.get("credit_score") or b.data.get("score")
        existing_emi = b.data.get("existing_monthly_emi") or b.data.get("existing_emi", 0)

        p = self.call("retrieve_policy", query="loan eligibility credit score affordability", k=1)
        cite = None
        if p.ok and p.data.get("snippets"):
            s = p.data["snippets"][0]
            cite = f"{s['doc'].replace('.md', '').replace('_', ' ').title()} > {s['section']}"
        tail = f" (Policy: {cite})" if cite else ""

        if score >= 750:
            rating = "Prime / Excellent"
            band_info = "You qualify for preferred lending rates starting at 10.5% p.a."
        elif score >= 700:
            rating = "Good"
            band_info = "You qualify for standard competitive rates at 12.0% p.a."
        elif score >= 650:
            rating = "Fair"
            band_info = "You meet the minimum lending threshold (policy min: 650) at 14.0% p.a."
        else:
            rating = "Below Policy Minimum"
            band_info = "Your score is below the 650 threshold required by bank policy for personal loans."

        msg = (
            f"Your current credit bureau (CIBIL) score is {score}.\n"
            f"• Bureau Rating: {rating}\n"
            f"• Existing Monthly Obligations: {fmt_inr(existing_emi)}\n"
            f"• Lending Policy Minimum: 650\n"
            f"• Status: {band_info}{tail}"
        )
        facts = {
            "customer_id": self.cid,
            "credit_score": score,
            "bureau_score": score,
            "rating": rating,
            "existing_emi": existing_emi,
            "policy": cite,
            "loan_eligible": score >= 650
        }
        return AgentResult(self.name, "credit_score", "ok", msg, facts)
