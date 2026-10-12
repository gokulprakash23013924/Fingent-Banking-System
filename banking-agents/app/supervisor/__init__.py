"""Supervisor and Orchestrator package for multi-agent banking.
Implements Observe-Think-Act architecture with structured workflow state tracking.
"""
from __future__ import annotations

from .orchestrator import AGENTS_MAP, SupervisorOrchestrator
from .planner import WorkflowPlanner
from .recovery import RecoveryController
from .self_evaluator import SelfEvaluator
from .workflow_state import (
    ExecutionSummary,
    ObserveResult,
    PlannedTask,
    SelfCorrectionAttempt,
    SelfEvaluationResult,
    ToolExecutionResult,
    WorkflowState,
)

# Export SupervisorOrchestrator as Supervisor for backwards compatibility
Supervisor = SupervisorOrchestrator
AGENTS = AGENTS_MAP

__all__ = [
    "Supervisor",
    "SupervisorOrchestrator",
    "WorkflowState",
    "ObserveResult",
    "TaskPlan",
    "PlannedTask",
    "ToolExecutionResult",
    "SelfEvaluationResult",
    "SelfCorrectionAttempt",
    "ExecutionSummary",
    "WorkflowPlanner",
    "SelfEvaluator",
    "RecoveryController",
    "AGENTS",
]
