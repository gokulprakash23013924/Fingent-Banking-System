from __future__ import annotations

import threading


class BudgetExceeded(Exception):
    pass


class Budget:
    """Per-request caps on tokens, LLM calls and agent/tool iterations (hard stop, never a loop)."""

    def __init__(self, max_tokens: int, max_calls: int, max_iterations: int):
        self.max_tokens = max_tokens
        self.max_calls = max_calls
        self.max_iterations = max_iterations
        self.tokens = 0
        self.calls = 0
        self.iterations = 0
        self._lock = threading.Lock()

    def precheck(self) -> None:
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded("LLM call budget used up")
            if self.tokens >= self.max_tokens:
                raise BudgetExceeded("token budget used up")

    def charge(self, tokens_in: int, tokens_out: int) -> None:
        with self._lock:
            self.calls += 1
            self.tokens += tokens_in + tokens_out

    def tick(self) -> None:
        with self._lock:
            self.iterations += 1
            if self.iterations > self.max_iterations:
                raise BudgetExceeded("iteration cap reached")
