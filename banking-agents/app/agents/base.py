"""Agent base class. An agent never touches data directly: every action is a tool call through the registry."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..gateway.budget import BudgetExceeded
from ..state import RequestState
from ..tools import definitions  # noqa: F401  (registers the tools)
from ..tools.registry import ToolContext, ToolResult, call_tool


@dataclass
class AgentResult:
    agent: str
    task: str
    status: str = "ok"  # ok | needs_input | blocked | error
    message: str = ""
    facts: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)   # any one of these entities fills the gap
    proposed: list = field(default_factory=list)  # write actions waiting for human approval


class BaseAgent:
    name = "base"

    def __init__(self, state: RequestState):
        self.state = state
        self.session = state.session

    @property
    def cid(self) -> str:
        return self.session.customer_id

    def call(self, tool: str, **args) -> ToolResult:
        self.state.budget.tick()
        ctx = ToolContext(self.state.trace_id, self.name, self.session, None, self.state.emit)
        res = call_tool(ctx, tool, args)
        self.state.note_tool(self.name, tool, res.status)
        n = res.data.get("injection_flagged") if res.ok else 0
        if n:
            self.state.guard_notes.append(f"{n} text field(s) looked like instructions and were removed before use")
            self.state.emit("guardrail", kind="prompt_injection", tool=tool, removed=n)
        return res

    def fail(self, task: str, r: ToolResult) -> AgentResult:
        msg = {
            "forbidden": "I can only access records that belong to this customer.",
            "not_found": r.error or "I couldn't find that record.",
            "invalid_args": f"That request wasn't valid ({r.error}).",
            "permission_denied": "That action is outside what this assistant is allowed to do.",
        }.get(r.status, "Something went wrong while processing that. Nothing was changed.")
        return AgentResult(self.name, task, "error", msg, {"error": r.status, "detail": r.error})

    def run(self, task: str, entities: dict | None = None) -> AgentResult:
        self.state.note_agent(self.name)
        self.state.emit("agent", agent=self.name, task=task, phase="start")
        try:
            res = getattr(self, f"_{task}")(entities or {})
        except BudgetExceeded as e:
            res = AgentResult(self.name, task, "error", "This request needed more steps than allowed, so I stopped.", {"error": str(e)})
        self.state.emit("agent", agent=self.name, task=task, phase="end", status=res.status)
        return res
