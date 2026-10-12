"""Fraud scoring: deterministic rules + an IsolationForest anomaly signal. The LLM never decides this."""
from __future__ import annotations

import os
import threading
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from .. import db, services
from ..config import get_policy, get_settings
from ..rules import compute_features, fraud_decision, rule_score
from ..util import parse_ts

_lock = threading.RLock()
_cache: dict[str, IsolationForest] = {}


def vectorize(f: dict) -> list[float]:
    return [max(-5.0, min(10.0, f["amount_z"])), f["hour"] / 23.0, f["foreign"], f["new_device"], f["new_merchant"], min(f["velocity"], 5)]


def model_path() -> str:
    return os.path.join(get_settings().models_dir, "fraud_iforest.joblib")


def _training_matrix() -> np.ndarray:
    pol = get_policy()["fraud"]
    rows = db.query(
        "SELECT t.txn_id, t.amount, t.merchant, t.country, t.device_id, t.ts, a.customer_id, c.home_country "
        "FROM transactions t JOIN accounts a ON a.account_id=t.account_id JOIN customers c ON c.customer_id=a.customer_id "
        "WHERE t.type='debit' ORDER BY a.customer_id, t.ts")
    devices: dict[str, set[str]] = {}
    for d in db.query("SELECT customer_id, device_id FROM devices"):
        devices.setdefault(d["customer_id"], set()).add(d["device_id"])
    vecs: list[list[float]] = []
    cur, hist = None, []
    for r in rows:
        if r["customer_id"] != cur:
            cur, hist = r["customer_id"], []
        ts = parse_ts(r["ts"])
        if hist:
            f = compute_features(amount=r["amount"], ts=ts, country=r["country"], home_country=r["home_country"],
                                 device_id=r["device_id"], merchant=r["merchant"], history=hist[-200:],
                                 known_devices=devices.get(cur, set()), window_minutes=pol["velocity_window_minutes"])
            vecs.append(vectorize(f))
        hist.append({"amount": r["amount"], "merchant": r["merchant"], "ts": ts})
    return np.array(vecs, dtype=float)


def train_and_save() -> dict:
    X = _training_matrix()
    if len(X) < 20:
        raise RuntimeError("not enough transaction history to train the fraud model; run `python -m data.seed` first")
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=0).fit(X)
    os.makedirs(get_settings().models_dir, exist_ok=True)
    joblib.dump(model, model_path())
    with _lock:
        _cache.pop(model_path(), None)
    return {"samples": int(len(X)), "path": model_path()}


def get_model() -> IsolationForest:
    path = model_path()
    with _lock:
        if path not in _cache:
            if not os.path.exists(path):
                train_and_save()
            _cache[path] = joblib.load(path)
        return _cache[path]


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def anomaly_norm(f: dict) -> float:
    s = -float(get_model().score_samples(np.array([vectorize(f)]))[0])
    return float(min(1.0, max(0.0, (s - 0.5) / 0.3)))


def score_transaction(txn_id: str, persist: bool = True) -> dict:
    pol = get_policy()["fraud"]
    txn = services.get_transaction(txn_id)
    if txn["type"] != "debit":
        out = {"txn_id": txn_id, "score": 0, "decision": "allow", "reasons": [], "features": {}, "anomaly": 0.0}
        if persist:
            services.set_txn_risk(txn_id, 0, "allow")
        return out
    cust = services.get_customer(txn["customer_id"])
    known = {d["device_id"] for d in services.get_devices(cust["customer_id"])}
    history = services.debit_history(cust["customer_id"], txn["ts"], days=90, exclude_txn=txn_id)
    f = compute_features(amount=txn["amount"], ts=parse_ts(txn["ts"]), country=txn["country"], home_country=cust["home_country"],
                         device_id=txn["device_id"], merchant=txn["merchant"], history=history, known_devices=known,
                         window_minutes=pol["velocity_window_minutes"])
    pts, reasons = rule_score(f)
    anomaly = anomaly_norm(f)
    bonus = int(round(pol["anomaly_weight"] * anomaly))
    if bonus > 0:
        reasons.append({"code": "ANOMALY_MODEL", "detail": "statistical outlier against this customer's normal pattern", "points": bonus})
    score = min(100, pts + bonus)
    decision = fraud_decision(score)
    if persist:
        services.set_txn_risk(txn_id, score, decision)
    return {"txn_id": txn_id, "score": score, "decision": decision, "reasons": reasons, "features": f,
            "anomaly": round(anomaly, 3), "amount": txn["amount"], "merchant": txn["merchant"],
            "country": txn["country"], "ts": txn["ts"], "account_id": txn["account_id"], "customer_id": txn["customer_id"]}
