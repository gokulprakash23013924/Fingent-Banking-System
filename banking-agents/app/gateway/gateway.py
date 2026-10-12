"""AI Gateway: the only door to a model. Masks PII, enforces budgets, routes tiers to models, falls back."""
from __future__ import annotations

from ..config import get_settings
from ..llm.client import LLMError, LLMResult, LLMUnavailable, get_client
from ..state import RequestState
from .pii import mask_pii


class Gateway:
    def __init__(self, client=None):
        self._client = client

    def _c(self):
        return self._client or get_client(get_settings())

    def available(self) -> bool:
        return get_settings().llm_enabled and self._c().available()

    def call(self, *, state: RequestState, tier: int, task: str, system: str, user: str,
             max_tokens: int = 400, json_mode: bool = True) -> LLMResult:
        """Raises LLMUnavailable (no model), BudgetExceeded (caps hit) or LLMError (every model failed)."""
        s = get_settings()
        if not s.llm_enabled:
            raise LLMUnavailable("LLM is switched off")
        client = self._c()
        if not client.available():
            raise LLMUnavailable("no LLM provider configured")
        state.budget.precheck()
        user_masked = mask_pii(user).text  # belt and braces: callers already pass masked text
        primary = s.tier2_model if tier == 2 else s.tier3_model
        models = [primary]
        if s.fallback_model and s.fallback_model != primary:
            models.append(s.fallback_model)
        last: Exception | None = None
        for i, model in enumerate(models):
            try:
                res = client.complete(task=task, system=system, user=user_masked, model=model,
                                      max_tokens=max_tokens, json_mode=json_mode)
            except LLMUnavailable:
                raise
            except LLMError as e:
                last = e
                state.emit("llm_error", tier=tier, model=model, error=str(e)[:160])
                continue
            res.fallback_used = i > 0
            state.budget.charge(res.tokens_in, res.tokens_out)
            state.record_llm(res.tokens_in, res.tokens_out, model, res.fallback_used, task)
            state.emit("llm", tier=tier, task=task, model=model, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                       ms=round(res.latency_ms, 1), fallback=res.fallback_used)
            return res
        raise LLMError(f"all models failed: {last}")
