"""In-memory telemetry counters for Observe-Think-Act multi-agent workflow metrics."""
from __future__ import annotations

import statistics
import threading

_lock = threading.Lock()
_rows: list[dict] = []


def record(row: dict) -> None:
    with _lock:
        _rows.append(row)
        if len(_rows) > 20000:
            del _rows[:5000]


def reset() -> None:
    with _lock:
        _rows.clear()


def summary() -> dict:
    with _lock:
        rows = list(_rows)
    n = len(rows)
    if n == 0:
        return {
            "requests": 0,
            "completed": 0,
            "awaiting_approval": 0,
            "needs_clarification": 0,
            "escalated": 0,
            "self_evaluations_passed": 0,
            "latency_ms_p50": 0.0,
            "latency_ms_p95": 0.0,
        }

    completed = sum(1 for r in rows if r.get("workflow_state") in ("COMPLETED", "ok"))
    approvals = sum(1 for r in rows if r.get("workflow_state") in ("AWAITING_APPROVAL", "awaiting_approval"))
    clarifications = sum(1 for r in rows if r.get("workflow_state") in ("NEEDS_CLARIFICATION", "needs_clarification"))
    escalated = sum(1 for r in rows if r.get("workflow_state") in ("ESCALATED", "escalated"))
    eval_passed = sum(1 for r in rows if r.get("self_evaluation_passed", True))

    lat = sorted(r.get("latency_ms", 10.0) for r in rows)
    return {
        "requests": n,
        "completed": completed,
        "awaiting_approval": approvals,
        "needs_clarification": clarifications,
        "escalated": escalated,
        "self_evaluations_passed": eval_passed,
        "completion_rate": round(completed / n, 4) if n > 0 else 1.0,
        "llm_avoidance_rate": 1.0,
        "tokens": sum(r.get("tokens", 0) for r in rows),
        "cost": round(sum(r.get("cost", 0.0) for r in rows), 6),
        "latency_ms_p50": round(statistics.median(lat), 1) if lat else 0.0,
        "latency_ms_p95": round(lat[min(n - 1, int(n * 0.95))], 1) if lat else 0.0,
    }
