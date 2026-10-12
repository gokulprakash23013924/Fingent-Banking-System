"""Human-in-the-loop store. A write tool cannot run unless an approved row matches its exact tool and arguments.

One group is what the customer sees (one card); each action inside it is one row, executed at most once.
"""
from __future__ import annotations

import json

from .. import db
from ..util import dumps, now_iso, short_id


def create_group(*, trace_id: str, customer_id: str, role: str, actions: list[dict], description: str,
                 followups: dict | None = None) -> str:
    gid = short_id("APR-").upper()
    for a in actions:
        db.execute(
            "INSERT INTO approvals (approval_id, group_id, trace_id, customer_id, role, agent, tool, args, description, followups, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (short_id("ACT-").upper(), gid, trace_id, customer_id, role, a["agent"], a["tool"],
             json.dumps(a["args"], sort_keys=True, default=str), description, dumps(followups or {}), "pending", now_iso()))
    return gid


def _parse(r: dict) -> dict:
    r = dict(r)
    r["args"] = json.loads(r["args"])
    r["followups"] = json.loads(r["followups"] or "{}")
    r["result"] = json.loads(r["result"]) if r.get("result") else None
    return r


def get_group(gid: str) -> list[dict]:
    return [_parse(r) for r in db.query("SELECT * FROM approvals WHERE group_id=? ORDER BY rowid", (gid,))]


def pending_for(customer_id: str | None = None) -> list[dict]:
    sql = "SELECT DISTINCT group_id FROM approvals WHERE status='pending'"
    params: tuple = ()
    if customer_id:
        sql += " AND customer_id=?"
        params = (customer_id,)
    return [summarize(get_group(r["group_id"])) for r in db.query(sql + " ORDER BY created_at", params)]


def summarize(rows: list[dict]) -> dict:
    first = rows[0]
    return {"group_id": first["group_id"], "customer_id": first["customer_id"], "description": first["description"],
            "status": first["status"], "created_at": first["created_at"],
            "actions": [{"tool": r["tool"], "agent": r["agent"], "args": r["args"], "status": r["status"]} for r in rows]}


def decide(gid: str, approve: bool) -> bool:
    """Compare-and-set: only a group that is still pending can be decided, and only once."""
    new = "approved" if approve else "rejected"
    n = db.execute_count("UPDATE approvals SET status=?, resolved_at=? WHERE group_id=? AND status='pending'", (new, now_iso(), gid))
    return n > 0


def find_approved(gid: str, tool: str, args: dict) -> dict | None:
    want = json.loads(json.dumps(args, sort_keys=True, default=str))
    for r in get_group(gid):
        if r["status"] == "approved" and r["tool"] == tool and r["args"] == want:
            return r
    return None


def mark(approval_id: str, status: str, result=None) -> None:
    db.execute("UPDATE approvals SET status=?, result=?, resolved_at=? WHERE approval_id=?",
               (status, dumps(result) if result is not None else None, now_iso(), approval_id))
