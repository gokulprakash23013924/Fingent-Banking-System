"""Per-request state shared by the supervisor, agents and tool layer."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from .config import get_settings
from .gateway.budget import Budget

ROLES = ("customer", "rm", "supervisor", "system")


@dataclass(frozen=True)
class Session:
    customer_id: str
    role: str = "customer"  # customer: own data only | rm/supervisor: any customer | system: background jobs

    def can_access(self, customer_id: str | None) -> bool:
        if customer_id is None:
            return False
        return self.role in ("rm", "supervisor", "admin", "system") or customer_id == self.customer_id


@dataclass
class RequestState:
    session: Session
    conversation_id: str
    text_masked: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    budget: Budget = field(default=None)  # type: ignore[assignment]
    events: list = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)
    tier: int = 0
    tier_path: list = field(default_factory=list)
    llm_calls: int = 0
    routing_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    models: list = field(default_factory=list)
    fallback_used: bool = False
    agents: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    proposed: list = field(default_factory=list)
    guard_notes: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def new(cls, session: Session, conversation_id: str, text_masked: str) -> "RequestState":
        s = get_settings()
        st = cls(session=session, conversation_id=conversation_id, text_masked=text_masked)
        st.budget = Budget(s.max_tokens_per_request, s.max_llm_calls, s.max_iterations)
        return st

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000

    def emit(self, type: str, **data) -> None:
        with self.lock:
            self.events.append({"t_ms": round(self.elapsed_ms(), 1), "type": type, **data})

    def note_agent(self, name: str) -> None:
        with self.lock:
            if name not in self.agents:
                self.agents.append(name)

    def note_tool(self, agent: str, tool: str, status: str) -> None:
        with self.lock:
            self.tools.append({"agent": agent, "tool": tool, "status": status})

    def record_llm(self, tokens_in: int, tokens_out: int, model: str, fallback: bool, task: str = "") -> None:
        s = get_settings()
        with self.lock:
            self.llm_calls += 1
            if task == "classify":
                self.routing_calls += 1
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.cost += tokens_in / 1000 * s.price_in_per_1k + tokens_out / 1000 * s.price_out_per_1k
            self.models.append(model)
            self.fallback_used = self.fallback_used or fallback
