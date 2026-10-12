"""Tool registry: the permission boundary between agents and the bank.

Every call goes through the same pipeline, whatever the model said:
  allowlist -> schema validation -> ownership check -> approval gate -> execute -> audit
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ValidationError

from .. import services
from ..services import ServiceError
from ..state import Session
from . import approvals, audit


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: type[BaseModel]
    fn: Callable
    allowed_agents: frozenset
    scope: tuple | None = None  # (kind, argument name) used to find which customer owns the target
    requires_approval: bool | Callable = False
    describe: Callable | None = None


@dataclass
class ToolContext:
    trace_id: str
    agent: str
    session: Session
    approval_group: str | None = None
    emit: Callable | None = None


@dataclass
class ToolResult:
    ok: bool
    status: str  # ok | permission_denied | invalid_args | forbidden | not_found | approval_required | approval_invalid | error | ...
    data: dict = field(default_factory=dict)
    error: str | None = None
    ms: float = 0.0
    proposed: dict | None = None


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    REGISTRY[spec.name] = spec
    return spec


def tools_for(agent: str) -> list[str]:
    return sorted(n for n, s in REGISTRY.items() if agent in s.allowed_agents)


def _finish(ctx: ToolContext, spec_name: str, args: dict, res: ToolResult, t0: float, payload) -> ToolResult:
    res.ms = round((time.perf_counter() - t0) * 1000, 1)
    audit.log(trace_id=ctx.trace_id, agent=ctx.agent, tool=spec_name, args=args, status=res.status,
              result=payload if payload is not None else (res.error or res.data),
              actor=f"{ctx.session.role}:{ctx.session.customer_id}")
    if ctx.emit:
        ctx.emit("tool", agent=ctx.agent, tool=spec_name, status=res.status, ms=res.ms,
                 error=res.error if not res.ok else None)
    return res


def call_tool(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    t0 = time.perf_counter()
    spec = REGISTRY.get(name)
    if spec is None:
        return _finish(ctx, name, args, ToolResult(False, "unknown_tool", error=f"no such tool: {name}"), t0, None)

    # 1. allowlist: an agent can only use the tools it was given
    if ctx.agent not in spec.allowed_agents:
        return _finish(ctx, name, args, ToolResult(False, "permission_denied",
                       error=f"agent '{ctx.agent}' is not allowed to call '{name}'"), t0, None)

    # 2. schema validation
    try:
        model = spec.schema(**args)
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())[:300]
        return _finish(ctx, name, args, ToolResult(False, "invalid_args", error=msg), t0, None)
    clean = model.model_dump()

    try:
        # 3. ownership: a customer session can only touch its own records
        if spec.scope:
            kind, arg = spec.scope
            owner = services.customer_of(kind, str(clean[arg]))
            if owner is None:
                raise ToolError("not_found", f"{kind} {clean[arg]} not found")
            if not ctx.session.can_access(owner):
                raise ToolError("forbidden", "that record does not belong to this session")

        # 4. approval gate: write tools never run without a matching human approval
        row = None
        need = spec.requires_approval(model) if callable(spec.requires_approval) else spec.requires_approval
        if need:
            if not ctx.approval_group:
                desc = spec.describe(model) if spec.describe else f"{name} {clean}"
                proposed = {"agent": ctx.agent, "tool": name, "args": clean, "summary": desc}
                return _finish(ctx, name, args, ToolResult(False, "approval_required", proposed=proposed,
                               error="human approval required"), t0, {"proposed": desc})
            row = approvals.find_approved(ctx.approval_group, name, clean)
            if row is None:
                raise ToolError("approval_invalid", "no matching approved action (already used, rejected or different arguments)")

        # 5. execute
        data = spec.fn(ctx, model)
        if row is not None:
            approvals.mark(row["approval_id"], "executed", data)
        return _finish(ctx, name, args, ToolResult(True, "ok", data=data), t0, data)

    except ToolError as e:
        return _finish(ctx, name, args, ToolResult(False, e.code, error=e.message), t0, None)
    except ServiceError as e:
        return _finish(ctx, name, args, ToolResult(False, e.code.lower(), error=e.message), t0, None)
    except Exception as e:  # never let a tool crash the request
        if row is not None:
            approvals.mark(row["approval_id"], "failed", {"error": str(e)[:200]})
        return _finish(ctx, name, args, ToolResult(False, "error", error=f"{type(e).__name__}: {str(e)[:200]}"), t0, None)
