"""Simulated real-time transaction feed. Scoring is the deterministic fraud scorer: no LLM is involved at any point."""
from __future__ import annotations

import math
import random
import threading
from datetime import datetime

from . import db, services
from .agents.fraud import FraudAgent
from .agents.notification import NotificationAgent
from .state import RequestState, Session
from .util import fmt_inr, now_iso

NORMAL = [("Swiggy", "food"), ("Zomato", "food"), ("Amazon", "shopping"), ("Uber", "transport"), ("Big Bazaar", "grocery"),
          ("Netflix", "entertainment"), ("HP Petrol Pump", "fuel"), ("Airtel Recharge", "utilities")]
ODD = [("GLOBALTECH ELECTRONICS", "electronics", "SG"), ("LUXE WATCHES DXB", "luxury", "AE"),
       ("SIAM GADGETS", "electronics", "TH"), ("LONDON LUXURY GOODS", "luxury", "GB")]


def simulate_transaction(customer_id: str | None = None, anomalous: bool | None = None, rng: random.Random | None = None) -> str:
    """Insert one synthetic debit and return its id."""
    rng = rng or random.Random()
    custs = [c["customer_id"] for c in services.list_customers()]
    cid = customer_id or rng.choice(custs)
    acct = next(a for a in services.get_accounts(cid) if a["type"] == "savings")
    odd = rng.random() < 0.25 if anomalous is None else anomalous
    if odd:
        m, cat, country = rng.choice(ODD)
        amount, device = float(rng.randrange(25, 90) * 1000), f"D-UNK-{rng.randint(1000, 9999)}"
    else:
        m, cat = rng.choice(NORMAL)
        country = "IN"
        row = db.query_one("SELECT AVG(amount) AS a FROM transactions WHERE account_id=? AND type='debit'", (acct["account_id"],))
        amount = max(50.0, round(rng.lognormvariate(math.log(max(row["a"] or 1000, 200) * 0.6), 0.4)))
        device = f"D-{cid}-{rng.choice([1, 2])}"
    tid = services.insert_transaction(account_id=acct["account_id"], type="debit", amount=amount, merchant=m, category=cat,
                                      country=country, device_id=device, ts=now_iso(), description="Simulated stream payment")
    db.execute("UPDATE accounts SET balance=balance-? WHERE account_id=?", (amount, acct["account_id"]))
    return tid


def process_transaction(txn_id: str) -> dict:
    """Score a transaction as the system and raise an alert if it is flagged. Returns an event for the UI."""
    t = services.get_transaction(txn_id)
    state = RequestState.new(Session(t["customer_id"], "system"), "stream", f"[stream {txn_id}]")
    r = FraudAgent(state).call("score_transaction", txn_id=txn_id)
    if not r.ok:
        return {"txn_id": txn_id, "error": r.error}
    s = r.data
    alert_id = None
    if s["decision"] != "allow":
        where = f" ({t['country']})" if t["country"] != "IN" else ""
        msg = f"Unusual card payment of {fmt_inr(t['amount'])} at {t['merchant']}{where} was flagged (risk {s['score']}/100)."
        a = NotificationAgent(state).send(msg, "high" if s["decision"] == "block" else "medium", txn_id)
        alert_id = a.data.get("alert_id") if a.ok else None
    return {"txn_id": txn_id, "customer_id": t["customer_id"], "amount": t["amount"], "merchant": t["merchant"],
            "country": t["country"], "ts": t["ts"], "score": s["score"], "decision": s["decision"],
            "reasons": [x["code"] for x in s["reasons"]], "alert_id": alert_id, "trace_id": state.trace_id}


class StreamRunner:
    def __init__(self, interval: float = 5.0, seed: int | None = None):
        self.interval = interval
        self.rng = random.Random(seed)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.events: list[dict] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="txn-stream")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                ev = process_transaction(simulate_transaction(rng=self.rng))
                self.events.append(ev)
                del self.events[:-200]
            except Exception as e:  # keep the feed alive
                self.events.append({"error": f"{type(e).__name__}: {e}", "ts": datetime.now().isoformat()})
