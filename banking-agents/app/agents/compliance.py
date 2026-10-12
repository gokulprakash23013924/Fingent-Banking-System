from __future__ import annotations

from ..util import fmt_ts
from .base import AgentResult, BaseAgent


class ComplianceAgent(BaseAgent):
    """KYC and AML gate. Screening outcomes are never disclosed to customers (policy); relationship managers see the detail."""
    name = "compliance"

    def _check(self, task: str, policy_query: str) -> AgentResult:
        k = self.call("get_kyc_status", customer_id=self.cid)
        if not k.ok:
            return self.fail(task, k)
        a = self.call("run_aml_check", customer_id=self.cid)
        p = self.call("retrieve_policy", query=policy_query, k=1)
        d = k.data
        verdict = d["verdict"]
        reasons = list(d["reasons"])
        if a.ok and not a.data["aml_clear"] and not any(r["code"] == "AML_FLAG" for r in reasons):
            verdict = "fail"
            reasons.append({"code": "AML_FLAG", "detail": "customer is flagged by AML screening"})
        shown = reasons
        if self.session.role == "customer":
            shown = [{"code": "COMPLIANCE_REVIEW", "detail": "a compliance review is needed before we can proceed"} if r["code"] == "AML_FLAG" else r
                     for r in reasons]
        cite = None
        if p.ok and p.data["snippets"]:
            s = p.data["snippets"][0]
            cite = f"{s['doc'].replace('.md', '').replace('_', ' ').title()} > {s['section']}"
        facts = {"verdict": verdict, "reasons": shown, "kyc_status": d["status"], "last_verified": d["last_verified"], "policy": cite}
        if verdict == "pass":
            msg = "Compliance: KYC verified and screening clear."
        else:
            txt = "; ".join(r["detail"] for r in shown)
            msg = "Compliance: on hold. " + txt[:1].upper() + txt[1:] + "."
        return AgentResult(self.name, task, "ok" if verdict == "pass" else "blocked", msg, facts)

    def _loan_gate(self, ent) -> AgentResult:
        return self._check("loan_gate", "KYC validity loan applications held pending expired")

    def _transfer_gate(self, ent) -> AgentResult:
        return self._check("transfer_gate", "large transfers need verified KYC explicit approval")

    def _kyc_status(self, ent) -> AgentResult:
        k = self.call("get_kyc_status", customer_id=self.cid)
        if not k.ok:
            return self.fail("kyc_status", k)
        d = k.data
        if d["verdict"] == "pass":
            msg = f"Your KYC is verified (last verified {fmt_ts(d['last_verified'])[:6]}). No action is needed."
        else:
            shown = [r for r in d["reasons"] if r["code"] != "AML_FLAG"] or [{"detail": "a compliance review is needed"}]
            msg = "Your KYC needs attention: " + "; ".join(r["detail"] for r in shown) + ". Please complete re-verification at a branch or by video KYC."
        return AgentResult(self.name, "kyc_status", "ok", msg,
                           {"status": d["status"], "verdict": d["verdict"], "last_verified": d["last_verified"]})
