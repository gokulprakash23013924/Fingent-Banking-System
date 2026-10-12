"""Append-only audit trail. Every tool call, allowed or refused, leaves a row with masked arguments."""
from __future__ import annotations

import json

from .. import db
from ..gateway.pii import mask_obj
from ..util import dumps, now_iso


def log(*, trace_id: str, agent: str, tool: str, args: dict, status: str, result, actor: str) -> None:
    args_masked = dumps(mask_obj(args))
    res = dumps(mask_obj(result)) if result is not None else ""
    db.execute("INSERT INTO audit_log (trace_id, ts, agent, tool, args_masked, status, result, actor) VALUES (?,?,?,?,?,?,?,?)",
               (trace_id, now_iso(), agent, tool, args_masked[:1000], status, res[:600], actor))


def for_trace(trace_id: str) -> list[dict]:
    rows = db.query("SELECT * FROM audit_log WHERE trace_id=? ORDER BY id", (trace_id,))
    for r in rows:
        try:
            r["args_masked"] = json.loads(r["args_masked"])
        except (TypeError, ValueError):
            pass
    return rows


def recent(limit: int = 50) -> list[dict]:
    return db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),))
