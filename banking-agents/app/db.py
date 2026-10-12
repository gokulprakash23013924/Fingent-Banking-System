"""SQLite helpers. One short-lived connection per call keeps threads (stream, parallel agents) safe."""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, income REAL NOT NULL,
  segment TEXT, city TEXT, home_country TEXT DEFAULT 'IN'
);
CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, type TEXT NOT NULL,
  balance REAL NOT NULL, status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS cards (
  card_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, last4 TEXT NOT NULL,
  status TEXT DEFAULT 'active', limit_amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
  txn_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, type TEXT NOT NULL,
  amount REAL NOT NULL, merchant TEXT, category TEXT, country TEXT DEFAULT 'IN',
  device_id TEXT, ts TEXT NOT NULL, status TEXT DEFAULT 'posted', description TEXT,
  risk_score REAL, risk_decision TEXT
);
CREATE INDEX IF NOT EXISTS idx_txn_account_ts ON transactions(account_id, ts);
CREATE TABLE IF NOT EXISTS devices (
  device_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, label TEXT,
  first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS bureau (
  customer_id TEXT PRIMARY KEY, score INTEGER NOT NULL, existing_emi REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kyc_records (
  customer_id TEXT PRIMARY KEY, status TEXT NOT NULL, last_verified TEXT, aml_flag INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS loan_applications (
  app_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, amount REAL NOT NULL,
  tenure_months INTEGER NOT NULL, rate REAL, emi REAL, status TEXT NOT NULL,
  decision_reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disputes (
  dispute_id TEXT PRIMARY KEY, txn_id TEXT NOT NULL, customer_id TEXT NOT NULL,
  reason TEXT, status TEXT DEFAULT 'open', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
  alert_id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT NOT NULL, txn_id TEXT,
  severity TEXT, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, ts TEXT NOT NULL, agent TEXT,
  tool TEXT, args_masked TEXT, status TEXT, result TEXT, actor TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_log(trace_id);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, group_id TEXT NOT NULL, trace_id TEXT, customer_id TEXT,
  role TEXT, agent TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL,
  description TEXT, followups TEXT, status TEXT NOT NULL, result TEXT,
  created_at TEXT NOT NULL, resolved_at TEXT
);
"""


def connect() -> sqlite3.Connection:
    path = get_settings().db_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    path = get_settings().db_path
    if reset and os.path.exists(path):
        os.remove(path)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    conn = connect()
    try:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn = connect()
    try:
        conn.executemany(sql, [tuple(r) for r in rows])
        conn.commit()
    finally:
        conn.close()


def execute_count(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write and return how many rows it changed (used for compare-and-set updates)."""
    conn = connect()
    try:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
