"""Self-Correction and Recovery Module.
Implements bounded, safe recovery when validation checks or tool execution fail.
Enforces strict financial safety: Never blind-retry writes, preserves idempotency, respects compliance gates.
"""
from __future__ import annotations

import logging
from typing import Any

from .workflow_state import SelfCorrectionAttempt, SelfEvaluationResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class RecoveryController:
    """Manages controlled self-correction and recovery within bounded limits."""

    def __init__(self, max_retries: int = MAX_RETRIES):
        self.max_retries = max_retries
        self._idempotency_keys: set[str] = set()

    def can_safely_retry(self, tool_name: str, retry_count: int, failure_category: str) -> bool:
        """Determines if a retry is safe and permitted."""
        # Rule 1: Exceeded bounded retry limit
        if retry_count >= self.max_retries:
            return False

        # Rule 2: NEVER retry a financial write tool blindly
        write_tools = {"transfer_funds", "block_card", "create_dispute", "create_loan_application"}
        if tool_name in write_tools:
            logger.warning("Recovery refused blind retry on financial write tool: %s", tool_name)
            return False

        # Rule 3: Policy violations cannot be retried away
        if failure_category == "POLICY_VIOLATION":
            return False

        return True

    def register_idempotency_key(self, key: str) -> bool:
        """Register an idempotency key to prevent duplicate writes. Returns False if already used."""
        if key in self._idempotency_keys:
            return False
        self._idempotency_keys.add(key)
        return True

    def formulate_recovery(self, eval_result: SelfEvaluationResult, retry_count: int) -> SelfCorrectionAttempt:
        """Formulate a structured recovery attempt."""
        if not eval_result.failures:
            return SelfCorrectionAttempt(
                failure_category="NONE",
                retry_count=retry_count,
                action_taken="No recovery needed",
                recovered=True
            )

        primary_failure = eval_result.failures[0]
        category = primary_failure.get("category", "UNKNOWN")

        if category == "POLICY_VIOLATION":
            return SelfCorrectionAttempt(
                failure_category=category,
                retry_count=retry_count,
                action_taken="Enforce regulatory compliance gate; explain policy limitation to user without retrying.",
                recovered=False,
                details=primary_failure.get("reason", "")
            )

        if category == "DATA_MISSING":
            return SelfCorrectionAttempt(
                failure_category=category,
                retry_count=retry_count,
                action_taken="Formulate targeted clarifying question for missing customer details.",
                recovered=False,
                details=primary_failure.get("reason", "")
            )

        if category == "TOOL_ERROR" and retry_count < self.max_retries:
            return SelfCorrectionAttempt(
                failure_category=category,
                retry_count=retry_count + 1,
                action_taken="Transient error detected. Executing bounded retry with verified parameters.",
                recovered=True,
                details=f"Retrying tool: {primary_failure.get('tool')}"
            )

        return SelfCorrectionAttempt(
            failure_category=category,
            retry_count=retry_count,
            action_taken="Escalate to human support / relationship manager.",
            recovered=False,
            details="Bounded retry limit reached or unrecoverable system state."
        )
