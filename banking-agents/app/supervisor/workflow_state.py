"""Workflow state, task plans, and execution summary models.
Implements the Observe-Think-Act architecture with explicit workflow lifecycle states.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowState(str, Enum):
    RECEIVED = "RECEIVED"
    UNDERSTANDING = "UNDERSTANDING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    RECOVERING = "RECOVERING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


@dataclass
class ObserveResult:
    """Outcome of the OBSERVE phase: user goal, intent, entities, and ambiguity detection."""
    goal: str
    intent: str
    entities: dict[str, Any] = field(default_factory=dict)
    missing_entities: list[str] = field(default_factory=list)
    is_ambiguous: bool = False
    clarifying_question: str | None = None
    safety_concerns: list[str] = field(default_factory=list)
    context_notes: list[str] = field(default_factory=list)
    is_greeting: bool = False
    greeting_response: str | None = None
    selected_tools: list[dict[str, Any]] = field(default_factory=list)
    multi_intent: list[str] = field(default_factory=list)
    is_mock: bool = False


@dataclass
class PlannedTask:
    """A unit of work planned during the THINK phase."""
    id: str
    agent: str
    action: str
    inputs: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    can_parallel: bool = False
    requires_approval: bool = False
    validation_key: str | None = None


@dataclass
class TaskPlan:
    """Outcome of the THINK phase: complete workflow strategy."""
    goal: str
    required_agents: list[str] = field(default_factory=list)
    tasks: list[PlannedTask] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    approval_required: bool = False
    validation_rules: list[str] = field(default_factory=list)
    recovery_options: list[str] = field(default_factory=list)


@dataclass
class ToolExecutionResult:
    """A tool execution step during the ACT phase."""
    task_id: str
    agent: str
    tool: str
    inputs: dict[str, Any]
    status: str  # ok | error | approval_required
    data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    duration_ms: float = 0.0


@dataclass
class SelfEvaluationResult:
    """Outcome of the SELF-EVALUATE phase: data & policy validation."""
    is_valid: bool
    checks_passed: list[str] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    can_recover: bool = False
    recovery_strategy: str | None = None
    semantic_fidelity: bool = True


@dataclass
class SelfCorrectionAttempt:
    """Outcome of the SELF-CORRECT phase: recovery actions."""
    failure_category: str
    retry_count: int
    action_taken: str
    recovered: bool
    details: str = ""


@dataclass
class ExecutionSummary:
    """User-visible execution summary describing Observe-Think-Act steps."""
    workflow_state: WorkflowState
    observe: dict[str, Any]
    think: dict[str, Any]
    act: list[dict[str, Any]]
    self_evaluation: dict[str, Any]
    self_correction: dict[str, Any] | None = None
    approval_pending: dict[str, Any] | None = None
    latency_ms: float = 0.0
