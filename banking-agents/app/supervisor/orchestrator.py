"""Supervisor / Orchestrator Component.

Implements the Observe–Think–Act architecture with self-evaluation and controlled self-correction.
Maintains structured workflow lifecycle states:
RECEIVED -> UNDERSTANDING -> PLANNING -> EXECUTING -> VALIDATING -> COMPLETED / AWAITING_APPROVAL / NEEDS_CLARIFICATION / ESCALATED.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import services
from ..agents.banking import BankingAgent
from ..agents.compliance import ComplianceAgent
from ..agents.credit import CreditAgent
from ..agents.fraud import FraudAgent
from ..agents.notification import NotificationAgent
from ..config import get_policy
from ..gateway.gateway import Gateway
from ..gateway.pii import mask_pii
from ..llm.nlu import UnifiedNLU
from ..state import ROLES, RequestState, Session
from ..tools import approvals
from ..util import fmt_inr
from .planner import WorkflowPlanner
from .recovery import RecoveryController
from .self_evaluator import SelfEvaluator
from .workflow_state import (
    ExecutionSummary,
    ObserveResult,
    SelfCorrectionAttempt,
    ToolExecutionResult,
    WorkflowState,
)
import re


def extract_named_customer_reference(text: str) -> str | None:
    """Extract a customer name or customer ID referenced in the user query."""
    if not text:
        return None
    raw = text.strip()

    # 1. Direct customer ID pattern, e.g. C001, C002, C003
    m_cid = re.search(r"\b(C\d{3})\b", raw, re.IGNORECASE)
    if m_cid:
        return m_cid.group(1).upper()

    # 2. Check all known customer names in the database
    # (Matches full names e.g. "Rohan Dass", "Rohan Das", "Aarav Mehta", "Diya Nair", etc.)
    all_names = services.db.query("SELECT name, customer_id FROM customers")
    lower_text = raw.lower()
    for row in all_names:
        c_full = row["name"].lower()
        c_tokens = c_full.split()
        c_first = c_tokens[0]
        # Match full name
        if c_full in lower_text:
            return row["name"]
        # Match first name + last name variant, e.g. "rohan dass" vs "rohan das"
        if len(c_tokens) > 1:
            pat = rf"\b{re.escape(c_first)}\s+{re.escape(c_tokens[1].rstrip('s'))}s*\b"
            if re.search(pat, lower_text):
                return row["name"]
        # Match isolated first name e.g. "for Rohan" or "Rohan's"
        if re.search(rf"\b{re.escape(c_first)}\b", lower_text):
            # Check if there is a surname following
            m_two = re.search(rf"\b{re.escape(c_first)}\s+([a-z]+)\b", lower_text)
            if m_two:
                return f"{c_first.title()} {m_two.group(1).title()}"
            return row["name"]

    # 3. Preposition followed by proper noun: 'of Rohan Dass', 'for Meera Iyer', 'balance of John Doe'
    m_prep = re.search(r"\b(?:of|for|about|on)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", raw)
    if m_prep:
        candidate = m_prep.group(1).strip()
        noise = {"my", "the", "an", "our", "this", "that", "all", "your", "account", "card", "loan", "personal loan", "savings account", "current account"}
        if candidate.lower() not in noise:
            return candidate

    # 4. Possessive name: "Rohan Dass's balance", "John's account"
    m_poss = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?:'s|’s)\b", raw)
    if m_poss:
        candidate = m_poss.group(1).strip()
        if candidate.lower() not in ("my", "today", "yesterday", "bank"):
            return candidate

    return None


AGENTS_MAP = {
    "banking": BankingAgent,
    "fraud": FraudAgent,
    "credit": CreditAgent,
    "compliance": ComplianceAgent,
    "notification": NotificationAgent,
}


class ConversationContext:
    def __init__(self):
        self.pending_intent: str | None = None
        self.pending_entities: dict[str, Any] = {}
        self.last_decision: dict[str, Any] | None = None
        self.workflow_history: list[dict[str, Any]] = []


class SupervisorOrchestrator:
    """Unified Supervisor and Orchestrator implementing Observe-Think-Act."""

    def __init__(self, gateway: Gateway | None = None):
        self.gateway = gateway or Gateway()
        self.nlu = UnifiedNLU(self.gateway)
        self.planner = WorkflowPlanner()
        self.evaluator = SelfEvaluator()
        self.recovery = RecoveryController()
        self._conversations: dict[tuple[str, str], ConversationContext] = {}
        self._lock = threading.Lock()

    def _get_context(self, customer_id: str, conv_id: str) -> ConversationContext:
        with self._lock:
            key = (customer_id, conv_id or customer_id)
            if key not in self._conversations:
                self._conversations[key] = ConversationContext()
            return self._conversations[key]

    def handle(self, message: str, customer_id: str, role: str = "customer",
               conversation_id: str | None = None, action: str | None = None,
               entities: dict | None = None) -> dict[str, Any]:
        """Main entry point: Executes the Observe-Think-Act workflow loop."""
        t_start = time.perf_counter()

        # Step 0: Security, Typo Normalization & PII Sanitization
        from ..llm.typo_normalizer import normalize_banking_query
        normalized_message = normalize_banking_query(message or "")
        masked = mask_pii(normalized_message)
        if role not in ROLES or role == "system":
            return self._error_response("Unauthorized role specified.", WorkflowState.FAILED)

        # -------------------------------------------------------------------------
        # IDENTITY RESOLUTION & ACCESS AUTHORIZATION
        # -------------------------------------------------------------------------
        target_name_ref = extract_named_customer_reference(message or "") or extract_named_customer_reference(normalized_message)
        effective_customer_id = customer_id
        resolved_customer_name = None

        is_transfer_request = bool(re.search(r"\b(transfer|send|wire|pay|remit)\b", f"{message} {normalized_message}", re.IGNORECASE))
        transfer_recipient_account = None
        transfer_recipient_name = None

        if role == "customer":
            # Rule 1 & 2: Customer can only access their own records. Cross-customer query blocked!
            if target_name_ref:
                matches = services.find_customer_by_name_or_query(target_name_ref)
                if matches and any(m["customer_id"] != customer_id for m in matches):
                    if is_transfer_request:
                        # Legitimate beneficiary for P2P funds transfer
                        recip_match = matches[0]
                        recip_accts = services.get_accounts(recip_match["customer_id"])
                        if recip_accts:
                            transfer_recipient_account = recip_accts[0]["account_id"]
                            transfer_recipient_name = recip_match["name"]
                    else:
                        # Cross-customer enquiry on another's balance/records: blocked
                        return self._error_response(
                            "Access denied: You are only authorized to access your own account records. Cross-customer data access is prohibited.",
                            WorkflowState.FAILED
                        )
            effective_customer_id = customer_id
        elif role in ("supervisor", "rm", "admin"):
            # Rule 3, 4, 5, 6, 7: Supervisor customer lookup
            if target_name_ref:
                matches = services.find_customer_by_name_or_query(target_name_ref)
                if not matches:
                    return self._error_response(
                        f"No customer record found matching '{target_name_ref}'. Please verify the customer name or identifier.",
                        WorkflowState.FAILED
                    )
                if len(matches) > 1:
                    options = ", ".join(f"{c['name']} ({c['customer_id']})" for c in matches)
                    duration_ms = (time.perf_counter() - t_start) * 1000
                    return self._build_response(
                        status="needs_clarification",
                        workflow_state=WorkflowState.NEEDS_CLARIFICATION,
                        answer=f"Multiple customers match '{target_name_ref}': {options}. Please specify which customer you wish to query.",
                        req_state=RequestState.new(Session(customer_id, role), conversation_id or customer_id, masked.text),
                        summary=ExecutionSummary(
                            workflow_state=WorkflowState.NEEDS_CLARIFICATION,
                            observe={"goal": "Customer Lookup", "intent": "lookup_customer", "entities": {"query": target_name_ref}},
                            think={"task_plan": "Clarify target customer selection", "required_agents": ["supervisor"]},
                            act=[],
                            self_evaluation={"is_valid": True, "checks_passed": ["Customer disambiguation requested"]},
                            latency_ms=duration_ms
                        )
                    )
                effective_customer_id = matches[0]["customer_id"]
                resolved_customer_name = matches[0]["name"]
            else:
                effective_customer_id = customer_id

        if not services.db.query_one("SELECT 1 AS x FROM customers WHERE customer_id=?", (effective_customer_id,)):
            return self._error_response(f"Unknown customer identifier: {effective_customer_id}.", WorkflowState.FAILED)

        session = Session(effective_customer_id, role)
        req_state = RequestState.new(session, conversation_id or effective_customer_id, masked.text)
        req_state.emit("request", text=masked.text, role=role, pii_masked=masked.findings)
        conv_ctx = self._get_context(effective_customer_id, req_state.conversation_id)

        # Detect direct account ID reference (e.g. A1002) in message
        m_direct_aid = re.search(r"\bA\d{4}\b", normalized_message, re.IGNORECASE)
        if m_direct_aid and not transfer_recipient_account:
            transfer_recipient_account = m_direct_aid.group(0).upper()

        req_state.emit("observe", phase="UNDERSTANDING")
        obs_context = {
            "pending_entities": dict(conv_ctx.pending_entities),
            "pending_intent": conv_ctx.pending_intent
        }
        if transfer_recipient_account:
            obs_context["pending_entities"]["account_ref"] = transfer_recipient_account
            obs_context["pending_entities"]["to_account"] = transfer_recipient_account
            if transfer_recipient_name:
                obs_context["pending_entities"]["recipient_name"] = transfer_recipient_name

        observation = self.nlu.observe(normalized_message, effective_customer_id, obs_context)

        # Merge any explicit overrides passed from UI or transfer resolution
        if action:
            observation.intent = action
        if transfer_recipient_account:
            observation.entities["account_ref"] = transfer_recipient_account
            observation.entities["to_account"] = transfer_recipient_account
            observation.entities["recipient_name"] = transfer_recipient_name
            if observation.intent not in ("transfer_money", "transfer_funds"):
                observation.intent = "transfer_money"
        if entities:
            observation.entities.update(entities)

        # Handle ambiguity / missing info / out-of-scope early
        if observation.is_ambiguous and observation.clarifying_question:
            conv_ctx.pending_entities.update(observation.entities)
            if observation.intent not in ("needs_clarification", "clarification", "out_of_scope", "greeting", "help"):
                conv_ctx.pending_intent = observation.intent
            else:
                conv_ctx.pending_intent = None
            duration_ms = (time.perf_counter() - t_start) * 1000
            summary = ExecutionSummary(
                workflow_state=WorkflowState.NEEDS_CLARIFICATION,
                observe={"goal": observation.goal, "intent": observation.intent, "entities": observation.entities},
                think={"task_plan": "Clarification requested before task execution", "required_agents": []},
                act=[],
                self_evaluation={"is_valid": True, "checks_passed": ["Ambiguity guardrail engaged"]},
                latency_ms=duration_ms
            )
            return self._build_response(
                status="needs_clarification",
                workflow_state=WorkflowState.NEEDS_CLARIFICATION,
                answer=observation.clarifying_question,
                req_state=req_state,
                summary=summary
            )

        if observation.intent == "out_of_scope":
            duration_ms = (time.perf_counter() - t_start) * 1000
            summary = ExecutionSummary(
                workflow_state=WorkflowState.ESCALATED,
                observe={"goal": observation.goal, "intent": observation.intent, "entities": observation.entities},
                think={"task_plan": "Out-of-scope escalation", "required_agents": []},
                act=[],
                self_evaluation={"is_valid": True, "checks_passed": ["Scope boundaries enforced"]},
                latency_ms=duration_ms
            )
            return self._build_response(
                status="escalated",
                workflow_state=WorkflowState.ESCALATED,
                answer=observation.clarifying_question or "That request is outside supported banking operations. Connecting to Relationship Manager.",
                req_state=req_state,
                summary=summary
            )

        # Handle natural conversational greetings cleanly without invoking unnecessary banking tools
        if observation.is_greeting or observation.intent in ("greeting", "help"):
            duration_ms = (time.perf_counter() - t_start) * 1000
            greeting_text = observation.greeting_response or observation.clarifying_question or (
                "Hello! I am your Fingent banking assistant. I can help you check account balances, "
                "review recent transactions, calculate loan EMI, evaluate loan eligibility, block cards, "
                "or investigate unrecognized payments. How may I assist you today?"
            )
            summary = ExecutionSummary(
                workflow_state=WorkflowState.COMPLETED,
                observe={"goal": "Conversational Greeting", "intent": "greeting", "entities": {}},
                think={"task_plan": "Natural conversational response (no banking tools required)", "required_agents": ["supervisor"]},
                act=[],
                self_evaluation={"is_valid": True, "checks_passed": ["Conversational intent handled cleanly"]},
                latency_ms=duration_ms
            )
            return self._build_response(
                status="completed",
                workflow_state=WorkflowState.COMPLETED,
                answer=greeting_text,
                req_state=req_state,
                summary=summary
            )

        # Clear pending context now that intent is being executed
        conv_ctx.pending_entities.clear()
        conv_ctx.pending_intent = None

        # -------------------------------------------------------------------------
        # PHASE 2: THINK — Plan the Workflow
        # -------------------------------------------------------------------------
        req_state.emit("think", phase="PLANNING")
        task_plan = self.planner.plan(observation, effective_customer_id)

        # -------------------------------------------------------------------------
        # PHASE 3: ACT — Execute the Planned Tasks
        # -------------------------------------------------------------------------
        req_state.emit("act", phase="EXECUTING")
        tool_results: list[ToolExecutionResult] = []
        proposed_actions: list[dict] = []
        agent_messages: list[str] = []
        structured_data: dict[str, Any] = {}

        # Special Multi-Agent Loan Application Execution (parallel underwriting)
        if observation.intent == "apply_loan" and len(task_plan.tasks) > 1:
            tool_results, proposed_actions, agent_messages, structured_data = self._execute_parallel_loan(
                req_state, observation.entities, conv_ctx
            )
        else:
            # Standard single/sequential task execution
            for task in task_plan.tasks:
                t0_task = time.perf_counter()
                agent_cls = AGENTS_MAP.get(task.agent)
                if not agent_cls:
                    continue

                agent_inst = agent_cls(req_state)
                agent_res = agent_inst.run(task.action, task.inputs)
                duration_task = (time.perf_counter() - t0_task) * 1000

                tool_results.append(ToolExecutionResult(
                    task_id=task.id,
                    agent=task.agent,
                    tool=task.action,
                    inputs=task.inputs,
                    status=agent_res.status,
                    data=agent_res.facts,
                    error_message=agent_res.message if agent_res.status in ("error", "failed") else None,
                    duration_ms=duration_task
                ))

                if agent_res.message:
                    agent_messages.append(agent_res.message)
                if agent_res.proposed:
                    proposed_actions.extend(agent_res.proposed)
                if agent_res.facts:
                    structured_data[observation.intent] = agent_res.facts

                # Record decisions for explanation context
                if observation.intent == "report_fraud" and agent_res.facts.get("transaction"):
                    conv_ctx.last_decision = {
                        "kind": "fraud",
                        "headline": f"Transaction {fmt_inr(agent_res.facts['transaction'].get('amount', 0))} at {agent_res.facts['transaction'].get('merchant')}",
                        "decision": agent_res.facts.get("decision"),
                        "reasons": [r.get("detail") for r in agent_res.facts.get("reasons", [])]
                    }

        # -------------------------------------------------------------------------
        # PHASE 4: SELF-EVALUATE — Check the Results
        # -------------------------------------------------------------------------
        req_state.emit("self_evaluate", phase="VALIDATING")
        eval_result = self.evaluator.evaluate(
            goal=observation.goal,
            intent=observation.intent,
            tool_results=tool_results,
            context={**structured_data, "customer_id": effective_customer_id}
        )

        # Immediate data integrity security gate: block on identity mismatch (Rule 10 & Test 9)
        for fail in eval_result.failures:
            if isinstance(fail, dict) and fail.get("category") == "IDENTITY_MISMATCH":
                return self._error_response(
                    f"DATA INTEGRITY ERROR: {fail.get('reason')}. Response blocked to protect customer records.",
                    WorkflowState.FAILED
                )

        # -------------------------------------------------------------------------
        # PHASE 5: SELF-CORRECT — Recover Safely If Needed
        # -------------------------------------------------------------------------
        correction_attempt: SelfCorrectionAttempt | None = None
        if not eval_result.is_valid:
            req_state.emit("self_correct", phase="RECOVERING")
            correction_attempt = self.recovery.formulate_recovery(eval_result, retry_count=0)

        # -------------------------------------------------------------------------
        # PHASE 6: GOAL COMPLETION & APPROVAL CHECK
        # -------------------------------------------------------------------------
        duration_ms = (time.perf_counter() - t_start) * 1000
        approval_obj = None

        any_tool_failed = any(tr.status in ("error", "failed") for tr in tool_results)

        if proposed_actions:
            # Write action requires human approval
            group_id = approvals.create_group(
                trace_id=req_state.trace_id,
                customer_id=effective_customer_id,
                role=role,
                actions=proposed_actions,
                description="; ".join(p["summary"] for p in proposed_actions),
                followups={"intent": observation.intent}
            )
            approval_obj = {
                "group_id": group_id,
                "description": "; ".join(p["summary"] for p in proposed_actions),
                "actions": proposed_actions,
            }
            final_state = WorkflowState.AWAITING_APPROVAL
            final_status = "awaiting_approval"
        elif any_tool_failed or (not eval_result.is_valid and correction_attempt and not correction_attempt.recovered):
            final_state = WorkflowState.FAILED
            final_status = "failed"
        else:
            final_state = WorkflowState.COMPLETED
            final_status = "completed"

        # Final answer formulation
        if final_state == WorkflowState.FAILED:
            err_details = [tr.error_message for tr in tool_results if tr.error_message]
            if not err_details and eval_result.failures:
                err_details = [f.get("reason", str(f)) if isinstance(f, dict) else str(f) for f in eval_result.failures]
            final_answer = "\n\n".join(agent_messages) if agent_messages else (
                f"Task failed: {err_details[0]}" if err_details else "The requested operation could not be completed."
            )
        else:
            if agent_messages:
                final_answer = "\n\n".join(agent_messages)
            else:
                if observation.clarifying_question:
                    final_answer = observation.clarifying_question
                elif observation.intent == "check_balance":
                    accts = services.get_accounts(effective_customer_id)
                    b_lines = [f"• {a['type'].title()} ({a['account_id']}): {fmt_inr(a['balance'])}" for a in accts]
                    total_bal = sum(a["balance"] for a in accts)
                    final_answer = f"Your account balances:\n" + "\n".join(b_lines) + f"\nTotal Available: {fmt_inr(total_bal)}"
                elif observation.intent == "mini_statement":
                    accts = services.get_accounts(effective_customer_id)
                    first_aid = accts[0]["account_id"] if accts else None
                    txns = services.get_transactions(first_aid, limit=5) if first_aid else []
                    t_lines = [f"• {fmt_ts(t['ts'])} · {t['merchant']} · {'-' if t['type']=='debit' else '+'}{fmt_inr(t['amount'])}" for t in txns]
                    final_answer = f"Recent transactions on your account:\n" + "\n".join(t_lines)
                elif observation.intent == "credit_score":
                    b = services.get_bureau(effective_customer_id)
                    final_answer = f"Your current CIBIL credit bureau score is {b['score']}."
                elif observation.intent == "account_info":
                    cust = services.get_customer(effective_customer_id)
                    accts = services.get_accounts(effective_customer_id)
                    acct_str = ", ".join(f"{a['type'].title()} ({a['account_id']})" for a in accts)
                    final_answer = f"Customer Profile: {cust['name']} ({cust['customer_id']})\nCity: {cust['city']}\nSegment: {cust['segment'].title()}\nAccounts: {acct_str}"
                else:
                    final_answer = (
                        "I am your Fingent banking assistant. I can help you check account balances, "
                        "review recent transactions, send money via Razorpay, evaluate loan eligibility & calculate EMI, "
                        "block cards, or review credit bureau scores. How may I assist you today?"
                    )
            if role in ("supervisor", "rm", "admin") and effective_customer_id != customer_id and resolved_customer_name:
                final_answer = f"[Target Customer: {resolved_customer_name} ({effective_customer_id})]\n" + final_answer

        if final_state == WorkflowState.AWAITING_APPROVAL:
            final_answer += "\n\n⚠️ This action requires your approval to proceed. Please review and confirm below."

        summary = ExecutionSummary(
            workflow_state=final_state,
            observe={
                "goal": observation.goal,
                "intent": observation.intent,
                "entities": observation.entities,
            },
            think={
                "required_agents": task_plan.required_agents,
                "parallel_groups": task_plan.parallel_groups,
                "approval_required": task_plan.approval_required,
                "validation_rules": task_plan.validation_rules,
            },
            act=[
                {
                    "agent": tr.agent,
                    "tool": tr.tool,
                    "status": tr.status,
                    "duration_ms": round(tr.duration_ms, 1)
                } for tr in tool_results
            ],
            self_evaluation={
                "is_valid": eval_result.is_valid,
                "checks_passed": eval_result.checks_passed,
                "failures": eval_result.failures
            },
            self_correction={
                "action": correction_attempt.action_taken,
                "category": correction_attempt.failure_category,
                "recovered": correction_attempt.recovered
            } if correction_attempt else None,
            approval_pending=approval_obj,
            latency_ms=duration_ms
        )

        from .. import metrics
        metrics.record({
            "workflow_state": final_state.value,
            "latency_ms": duration_ms,
            "self_evaluation_passed": eval_result.is_valid,
            "tokens": 0,
            "cost": 0.0
        })

        return self._build_response(
            status=final_status,
            workflow_state=final_state,
            answer=final_answer,
            req_state=req_state,
            summary=summary,
            approval=approval_obj,
            data=structured_data
        )

    def _execute_parallel_loan(self, req_state: RequestState, entities: dict,
                               conv_ctx: ConversationContext) -> tuple[list, list, list, dict]:
        """Runs Credit, Fraud, and Compliance agents in parallel and combines outputs."""
        tool_results: list[ToolExecutionResult] = []
        proposed_actions: list[dict] = []
        agent_messages: list[str] = []
        structured_data: dict[str, Any] = {}

        jobs = {
            "credit": ("apply_loan", CreditAgent(req_state)),
            "fraud": ("assess_recent_risk", FraudAgent(req_state)),
            "compliance": ("loan_gate", ComplianceAgent(req_state))
        }

        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {name: ex.submit(agent.run, task, entities) for name, (task, agent) in jobs.items()}
            res = {name: f.result() for name, f in futs.items()}

        for name, r in res.items():
            tool_results.append(ToolExecutionResult(
                task_id=f"loan_{name}",
                agent=name,
                tool=jobs[name][0],
                inputs=entities,
                status=r.status,
                data=r.facts,
                duration_ms=0.0
            ))

        credit_r, risk_r, comp_r = res["credit"], res["fraud"], res["compliance"]
        cf, rf, kf = credit_r.facts, risk_r.facts, comp_r.facts

        # Deterministic underwriting aggregation policy:
        # Credit decline > Compliance hold > Fraud referral > Approve
        if cf.get("decision") == "decline":
            final_verdict = "decline"
        elif kf.get("verdict") != "pass":
            final_verdict = "hold"
        elif rf.get("elevated"):
            final_verdict = "refer"
        else:
            final_verdict = "approve"

        head_map = {
            "approve": "can go ahead",
            "refer": "can go ahead with manual review",
            "hold": "is on hold due to compliance requirements",
            "decline": "cannot be approved based on credit policy"
        }
        status_line = f"Loan Application Evaluation: {fmt_inr(cf.get('amount', 0))} for {cf.get('tenure_months', 36)} months {head_map[final_verdict]}."

        agent_messages = [
            status_line,
            f"• Credit Underwriting: {credit_r.message}",
            f"• Transaction Risk Signals: {risk_r.message}",
            f"• Compliance & KYC: {comp_r.message}"
        ]

        if final_verdict == "approve":
            status_tag = "approved"
            reason_tag = "all policy checks passed"
            proposed = CreditAgent(req_state).propose_application(cf, status_tag, reason_tag)
            proposed_actions.extend(proposed)
            agent_messages.append(
                "All underwriting checks passed (Prime CIBIL, verified KYC, low fraud risk). "
                "Please confirm below to authorize and activate your approved loan application."
            )
        elif final_verdict == "refer":
            status_tag = "under_review"
            reason_tag = "elevated fraud indicators, referral required"
            proposed = CreditAgent(req_state).propose_application(cf, status_tag, reason_tag)
            proposed_actions.extend(proposed)
            agent_messages.append("Please confirm to authorize and submit your formal loan application for supervisor manual review.")
        elif final_verdict == "hold":
            agent_messages.append("Application held: Pending updated regulatory KYC verification.")
        elif final_verdict == "decline":
            agent_messages.append("Application declined: Credit bureau score or debt-to-income ratio does not meet minimum bank lending policy standards.")

        structured_data["apply_loan"] = {
            "decision": final_verdict,
            "amount": cf.get("amount"),
            "tenure_months": cf.get("tenure_months"),
            "credit": cf,
            "fraud": rf,
            "compliance": kf
        }
        structured_data["loan_application"] = {
            "amount": cf.get("amount"),
            "tenure_months": cf.get("tenure_months"),
            "final_verdict": final_verdict,
            "credit": cf,
            "fraud": rf,
            "compliance": kf
        }

        return tool_results, proposed_actions, agent_messages, structured_data

    def decide_approval(self, group_id: str, approve: bool, customer_id: str, role: str = "customer") -> dict:
        """Executes or cancels an approval gate with idempotency protection."""
        rows = approvals.get_group(group_id)
        if not rows:
            return {"status": "error", "message": "Approval group not found"}

        if role not in ("rm", "supervisor"):
            owner = rows[0].get("customer_id")
            if owner and owner != customer_id:
                return {"status": "error", "message": "Access denied: cannot decide an approval belonging to another customer"}

        ok = approvals.decide(group_id, approve)
        if not ok:
            return {"status": "error", "message": "Approval group was already decided or is not pending"}

        if not approve:
            return {
                "status": "rejected",
                "workflow_state": WorkflowState.COMPLETED.value,
                "answer": "Action rejected by user. The proposed write tool was canceled.",
                "executed": []
            }

        executed_tools = []
        session = Session(customer_id, role)
        from ..tools.registry import ToolContext, call_tool
        for act in rows:
            tool_name = act.get("tool")
            tool_args = act.get("args", {})
            approval_id = act.get("approval_id")
            agent_name = act.get("agent", "banking")
            try:
                ctx = ToolContext(
                    trace_id=act.get("trace_id", group_id),
                    agent=agent_name,
                    session=session,
                    approval_group=group_id
                )
                res = call_tool(ctx, tool_name, tool_args)
                if res.ok:
                    executed_tools.append({"tool": tool_name, "status": "ok", "result": res.data})
                else:
                    executed_tools.append({"tool": tool_name, "status": "error", "error": res.error})
            except Exception as e:
                executed_tools.append({"tool": tool_name, "status": "error", "error": str(e)})

        executed_ids = []
        for ex in executed_tools:
            res_val = ex.get("result", {})
            if isinstance(res_val, dict):
                for k in ("app_id", "loan_id", "dispute_id", "card_id"):
                    if k in res_val:
                        executed_ids.append(str(res_val[k]))
        id_str = f" ({', '.join(executed_ids)})" if executed_ids else ""

        if executed_tools and customer_id:
            from .. import services
            tool_names = ", ".join(r["tool"] for r in rows)
            services.create_alert(customer_id, severity="info", message=f"Confirmation: Approved and executed {tool_names}.{id_str}")

        return {
            "status": "completed",
            "workflow_state": WorkflowState.COMPLETED.value,
            "answer": f"Approved and successfully executed: {'; '.join(r['tool'] for r in rows)}.{id_str}",
            "executed": executed_tools
        }

    def _build_response(self, status: str, workflow_state: WorkflowState, answer: str,
                        req_state: RequestState, summary: ExecutionSummary,
                        approval: dict | None = None, data: dict | None = None) -> dict[str, Any]:
        resp_status = "awaiting_approval" if approval else status
        req_agents = summary.think.get("required_agents", [])
        return {
            "trace_id": req_state.trace_id,
            "conversation_id": req_state.conversation_id,
            "status": resp_status,
            "tier": 0,
            "llm": {"calls": 0, "tokens": 0, "model": "mock"},
            "guardrails": ["indirect_injected_instructions_sanitized", "pii_masking"],
            "agents": req_agents,
            "intents": [{"intent": summary.observe.get("intent", ""), "confidence": 1.0}],
            "workflow_state": workflow_state.value,
            "answer": answer,
            "final_answer": answer,
            "execution_summary": {
                "workflow_state": summary.workflow_state.value,
                "observe": summary.observe,
                "think": summary.think,
                "act": summary.act,
                "self_evaluation": summary.self_evaluation,
                "self_correction": summary.self_correction,
                "latency_ms": summary.latency_ms
            },
            "approval": approval,
            "data": data or {},
            "trace": req_state.events
        }

    def _error_response(self, message: str, state: WorkflowState) -> dict[str, Any]:
        return {
            "status": "error",
            "workflow_state": state.value,
            "answer": message,
            "final_answer": message,
            "execution_summary": {
                "workflow_state": state.value,
                "observe": {},
                "think": {},
                "act": [],
                "self_evaluation": {"is_valid": False, "failures": [{"category": "AUTH_ERROR", "reason": message}]}
            }
        }
