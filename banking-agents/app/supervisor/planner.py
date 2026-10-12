"""Supervisor Task Planner (THINK phase).
Plans the structured multi-agent workflow, dependencies, parallel groups, and validation requirements.
"""
from __future__ import annotations

from typing import Any

from .workflow_state import ObserveResult, PlannedTask, TaskPlan

INTENT_AGENT_MAP = {
    "check_balance": ("banking", "check_balance"),
    "mini_statement": ("banking", "mini_statement"),
    "card_status": ("banking", "card_status"),
    "account_info": ("banking", "account_info"),
    "report_fraud": ("fraud", "report_fraud"),
    "block_card": ("fraud", "block_card"),
    "loan_eligibility": ("credit", "loan_eligibility"),
    "calculate_emi": ("credit", "calculate_emi"),
    "loan_status": ("credit", "loan_status"),
    "view_alerts": ("notification", "view_alerts"),
    "kyc_status": ("compliance", "kyc_status"),
    "transfer_money": ("banking", "transfer_money"),
    "apply_loan": ("credit", "apply_loan"),
    "credit_score": ("credit", "credit_score"),
}


class WorkflowPlanner:
    """Creates structured task plans for the Supervisor/Orchestrator."""

    def plan(self, observation: ObserveResult, customer_id: str) -> TaskPlan:
        intent = observation.intent
        entities = observation.entities

        # Multi-Agent Loan Application Workflow
        if intent == "apply_loan":
            return self._plan_loan_application(observation, customer_id)

        # Large Money Transfer Workflow
        if intent == "transfer_money":
            return self._plan_transfer(observation, customer_id)

        # Suspicious Transaction / Fraud Investigation Workflow
        if intent == "report_fraud":
            return self._plan_fraud_investigation(observation, customer_id)

        # Multi-Intent Handling (e.g. balance inquiry + mini-statement, or eligibility + EMI)
        if len(observation.multi_intent) > 1 and intent != "apply_loan":
            tasks = []
            agents = []
            for idx, sub_intent in enumerate(observation.multi_intent, start=1):
                if sub_intent in INTENT_AGENT_MAP:
                    ag, act = INTENT_AGENT_MAP[sub_intent]
                    if ag not in agents:
                        agents.append(ag)
                    tasks.append(PlannedTask(
                        id=f"task_{idx}",
                        agent=ag,
                        action=act,
                        inputs=entities,
                        dependencies=[],
                        can_parallel=True,
                        requires_approval=False,
                        validation_key=sub_intent
                    ))
            if tasks:
                return TaskPlan(
                    goal=observation.goal,
                    required_agents=agents,
                    tasks=tasks,
                    parallel_groups=[[t.id for t in tasks]],
                    approval_required=False,
                    validation_rules=[f"verify_{t.validation_key}_facts" for t in tasks],
                    recovery_options=["retry_with_fallback", "ask_clarification"]
                )

        # Standard Single-Agent Workflow
        if intent in INTENT_AGENT_MAP:
            agent, action = INTENT_AGENT_MAP[intent]
            task = PlannedTask(
                id="task_1",
                agent=agent,
                action=action,
                inputs=entities,
                dependencies=[],
                can_parallel=False,
                requires_approval=False,
                validation_key=intent
            )
            return TaskPlan(
                goal=observation.goal,
                required_agents=[agent],
                tasks=[task],
                parallel_groups=[["task_1"]],
                approval_required=False,
                validation_rules=[f"verify_{intent}_facts"],
                recovery_options=["retry_with_fallback", "ask_clarification"]
            )

        # Fallback plan for unknown or informational requests
        return TaskPlan(
            goal=observation.goal,
            required_agents=[],
            tasks=[],
            parallel_groups=[],
            approval_required=False,
            validation_rules=[],
            recovery_options=[]
        )

    def _plan_loan_application(self, observation: ObserveResult, customer_id: str) -> TaskPlan:
        """Plans parallel underwriting across Credit, Fraud, and Compliance agents."""
        task_credit = PlannedTask(
            id="credit_assessment",
            agent="credit",
            action="apply_loan",
            inputs=observation.entities,
            dependencies=[],
            can_parallel=True,
            requires_approval=False,
            validation_key="credit_policy_rules"
        )

        task_fraud = PlannedTask(
            id="fraud_risk_signals",
            agent="fraud",
            action="assess_recent_risk",
            inputs=observation.entities,
            dependencies=[],
            can_parallel=True,
            requires_approval=False,
            validation_key="transaction_risk_thresholds"
        )

        task_compliance = PlannedTask(
            id="compliance_kyc_aml",
            agent="compliance",
            action="loan_gate",
            inputs=observation.entities,
            dependencies=[],
            can_parallel=True,
            requires_approval=False,
            validation_key="kyc_aml_regulations"
        )

        return TaskPlan(
            goal=observation.goal,
            required_agents=["credit", "fraud", "compliance"],
            tasks=[task_credit, task_fraud, task_compliance],
            # All 3 underwriting tasks execute concurrently
            parallel_groups=[["credit_assessment", "fraud_risk_signals", "compliance_kyc_aml"]],
            approval_required=True,  # Submitting the actual application requires user authorization
            validation_rules=["verify_credit_score_match", "verify_kyc_not_expired", "verify_isolation_forest_score"],
            recovery_options=["prompt_missing_documents", "offer_smaller_loan", "escalate_to_underwriter"]
        )

    def _plan_transfer(self, observation: ObserveResult, customer_id: str) -> TaskPlan:
        """Plans funds transfer with compliance gate for high amounts."""
        amount = observation.entities.get("amount", 0.0)
        tasks = []
        parallel_groups = []
        approval_req = amount >= 50000.0 or not observation.entities.get("pre_approved", False)

        if amount >= 50000.0:
            task_gate = PlannedTask(
                id="compliance_gate",
                agent="compliance",
                action="transfer_gate",
                inputs=observation.entities,
                dependencies=[],
                can_parallel=False,
                requires_approval=False
            )
            tasks.append(task_gate)
            parallel_groups.append(["compliance_gate"])

        task_transfer = PlannedTask(
            id="banking_transfer",
            agent="banking",
            action="transfer_money",
            inputs=observation.entities,
            dependencies=["compliance_gate"] if amount >= 50000.0 else [],
            can_parallel=False,
            requires_approval=approval_req,
            validation_key="account_balance_sufficient"
        )
        tasks.append(task_transfer)
        parallel_groups.append(["banking_transfer"])

        return TaskPlan(
            goal=observation.goal,
            required_agents=["banking", "compliance"] if amount >= 50000.0 else ["banking"],
            tasks=tasks,
            parallel_groups=parallel_groups,
            approval_required=approval_req,
            validation_rules=["verify_sender_balance", "verify_daily_transfer_limit"],
            recovery_options=["request_smaller_amount", "notify_insufficient_funds"]
        )

    def _plan_fraud_investigation(self, observation: ObserveResult, customer_id: str) -> TaskPlan:
        """Plans fraud assessment and proposed card block/dispute."""
        task_fraud = PlannedTask(
            id="fraud_score_investigation",
            agent="fraud",
            action="report_fraud",
            inputs=observation.entities,
            dependencies=[],
            can_parallel=False,
            requires_approval=True,  # Write tools (block_card, dispute) require human authorization
            validation_key="isolation_forest_risk_match"
        )

        return TaskPlan(
            goal=observation.goal,
            required_agents=["fraud"],
            tasks=[task_fraud],
            parallel_groups=[["fraud_score_investigation"]],
            approval_required=True,
            validation_rules=["verify_transaction_ownership", "verify_anomaly_reasons"],
            recovery_options=["confirm_transaction_id", "escalate_to_fraud_analyst"]
        )
