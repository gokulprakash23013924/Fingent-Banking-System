import re

from .. import services
from ..util import fmt_inr, fmt_ts
from .base import AgentResult, BaseAgent


class BankingAgent(BaseAgent):
    """Profile, accounts, balances, statements, cards and transfers."""
    name = "banking"

    def _accounts_or_fail(self, task):
        r = self.call("get_accounts", customer_id=self.cid)
        return (None, self.fail(task, r)) if not r.ok else (r.data["accounts"], None)

    @staticmethod
    def _pick(ent, accts):
        ref = ent.get("account_ref")
        for a in accts:
            if a["account_id"] == ref:
                return a
        for a in accts:
            if a["type"] == "savings":
                return a
        return accts[0] if accts else None

    def _check_balance(self, ent) -> AgentResult:
        accts, err = self._accounts_or_fail("check_balance")
        if err:
            return err
        ref = ent.get("account_ref")
        chosen = [a for a in accts if a["account_id"] == ref] or [a for a in accts if a["status"] == "active"]
        rows = []
        for a in chosen:
            r = self.call("get_balance", account_id=a["account_id"])
            if not r.ok:
                return self.fail("check_balance", r)
            rows.append(r.data)
        if not rows:
            return AgentResult(self.name, "check_balance", "ok", "I couldn't find an active account.", {"accounts": []})
        if len(rows) == 1:
            b = rows[0]
            msg = f"Your {b['type']} account {b['account_id']} has a balance of {fmt_inr(b['balance'])}."
        else:
            msg = "Your balances:\n" + "\n".join(f"• {b['type'].title()} ({b['account_id']}): {fmt_inr(b['balance'])}" for b in rows)
        return AgentResult(self.name, "check_balance", "ok", msg,
                           {"accounts": [{"account_id": b["account_id"], "type": b["type"], "balance": b["balance"]} for b in rows]})

    def _mini_statement(self, ent) -> AgentResult:
        accts, err = self._accounts_or_fail("mini_statement")
        if err:
            return err
        a = self._pick(ent, accts)
        if not a:
            return AgentResult(self.name, "mini_statement", "ok", "I couldn't find an account to show.", {})
        n = max(1, min(int(ent.get("count") or 5), 20))
        r = self.call("get_transactions", account_id=a["account_id"], limit=n)
        if not r.ok:
            return self.fail("mini_statement", r)
        tx = r.data["transactions"]
        if not tx:
            return AgentResult(self.name, "mini_statement", "ok", f"No transactions found on {a['account_id']}.", {"transactions": []})
        lines = [f"• {fmt_ts(t['ts'])} · {t['merchant'] or t['category']} · {'-' if t['type'] == 'debit' else '+'}{fmt_inr(t['amount'])}" for t in tx]
        msg = f"Last {len(tx)} transactions on your {a['type']} account {a['account_id']}:\n" + "\n".join(lines)
        return AgentResult(self.name, "mini_statement", "ok", msg,
                           {"account_id": a["account_id"], "count": len(tx),
                            "transactions": [{"txn_id": t["txn_id"], "ts": t["ts"], "type": t["type"], "amount": t["amount"], "merchant": t["merchant"]} for t in tx]})

    def _card_status(self, ent) -> AgentResult:
        r = self.call("get_card_status", customer_id=self.cid)
        if not r.ok:
            return self.fail("card_status", r)
        cards = r.data["cards"]
        last4 = ent.get("card_last4")
        if last4:
            cards = [c for c in cards if c["last4"] == last4] or cards
        if not cards:
            return AgentResult(self.name, "card_status", "ok", "I couldn't find a card on this profile.", {"cards": []})
        msg = "\n".join(f"• Card ending {c['last4']} ({c['account_id']}): {c['status']}, limit {fmt_inr(c['limit'])}" for c in cards)
        return AgentResult(self.name, "card_status", "ok", msg, {"cards": cards})

    def _account_info(self, ent) -> AgentResult:
        r = self.call("get_customer_profile", customer_id=self.cid)
        if not r.ok:
            return self.fail("account_info", r)
        p = r.data
        accts = ", ".join(f"{a['type']} {a['account_id']} ({a['status']})" for a in p["accounts"])
        msg = f"{p['name']} · {p['segment']} · {p['city']}\nAccounts: {accts}"
        return AgentResult(self.name, "account_info", "ok", msg, p)

    def _transfer_money(self, ent) -> AgentResult:
        amt = ent.get("amount")
        to = ent.get("account_ref") or ent.get("to_account") or ent.get("recipient") or ent.get("recipient_name")

        # Resolve named customer or recipient to an account
        if to and not re.match(r"^A\d{4}$", str(to).strip(), re.IGNORECASE):
            matches = services.find_customer_by_name_or_query(str(to).strip())
            if matches:
                target_cid = matches[0]["customer_id"]
                target_accts = services.get_accounts(target_cid)
                if target_accts:
                    to = target_accts[0]["account_id"]
                    ent["recipient_name"] = matches[0]["name"]

        if not amt or not to:
            return AgentResult(self.name, "transfer_money", "needs_input",
                               "Who should I send it to and how much? For example: transfer 5000 to Diya Nair or A1002.",
                               {"have": {k: v for k, v in ent.items() if k in ("amount", "account_ref", "to_account")}},
                               missing=["amount", "account_ref"])
        accts, err = self._accounts_or_fail("transfer_money")
        if err:
            return err
        src = self._pick({}, accts)
        bal = self.call("get_balance", account_id=src["account_id"])
        if not bal.ok:
            return self.fail("transfer_money", bal)
        if bal.data["balance"] < amt:
            return AgentResult(self.name, "transfer_money", "blocked",
                               f"Your balance of {fmt_inr(bal.data['balance'])} is not enough for a {fmt_inr(amt)} transfer.",
                               {"error": "INSUFFICIENT_FUNDS", "balance": bal.data["balance"]})
        r = self.call("transfer_funds", from_account=src["account_id"], to_account=to, amount=float(amt))
        if r.status == "approval_required":
            return AgentResult(self.name, "transfer_money", "ok",
                               f"This is a large transfer: {fmt_inr(amt)} from {src['account_id']} to {to}. I need your confirmation before sending it.",
                               {"amount": amt, "to_account": to, "from_account": src["account_id"]}, proposed=[r.proposed])
        if not r.ok:
            return self.fail("transfer_money", r)
        d = r.data
        rzp_id = d.get("razorpay_payment_id", "rzp_test_Fingent2026")
        recip_label = d.get("recipient_name") or d.get("to_account")
        msg = f"Successfully transferred {fmt_inr(d['amount'])} to {recip_label} ({d['to_account']}) via Razorpay Gateway (Ref: {rzp_id}). Your new balance is {fmt_inr(d['new_balance'])}."
        return AgentResult(self.name, "transfer_money", "ok", msg, d)
