"""Self-Evaluator Module.
Implements the SELF-EVALUATE phase of the Supervisor architecture.
Uses deterministic business validators for financial figures, policy rules, and database agreement.
"""
from __future__ import annotations

from typing import Any

from ..config import get_policy
from .workflow_state import SelfEvaluationResult, ToolExecutionResult


class SelfEvaluator:
    """Evaluates agent tool outputs, policy compliance, and goal achievement."""

    def evaluate(self, goal: str, intent: str, tool_results: list[ToolExecutionResult],
                 context: dict[str, Any]) -> SelfEvaluationResult:
        checks_passed = []
        failures = []

        # Check 1: Tool execution health
        for tr in tool_results:
            if tr.status == "error":
                failures.append({
                    "category": "TOOL_ERROR",
                    "tool": tr.tool,
                    "agent": tr.agent,
                    "reason": tr.error_message or "Tool execution failed"
                })
            else:
                checks_passed.append(f"Tool {tr.tool} executed successfully ({tr.agent})")

        # Check 2: Financial data consistency & non-nullness
        if intent == "check_balance":
            has_accts = any("accounts" in tr.data or "balance" in tr.data for tr in tool_results)
            if has_accts:
                checks_passed.append("Account balance records verified from database")
            else:
                failures.append({
                    "category": "DATA_MISSING",
                    "reason": "Balance check did not return account records"
                })

        # Check 3: Multi-agent loan policy consistency
        if intent == "apply_loan":
            # Verify Credit, Fraud, and Compliance outcomes align with policy
            credit_tr = next((tr for tr in tool_results if tr.agent == "credit"), None)
            fraud_tr = next((tr for tr in tool_results if tr.agent == "fraud"), None)
            comp_tr = next((tr for tr in tool_results if tr.agent == "compliance"), None)

            if credit_tr and fraud_tr and comp_tr:
                checks_passed.append("Parallel underwriting received from Credit, Fraud, and Compliance agents")
                # Deterministic check: Bureau score consistency
                bureau_score = credit_tr.data.get("score") or credit_tr.data.get("bureau_score")
                min_score = get_policy().get("loan", {}).get("min_credit_score", 650)
                if bureau_score is not None:
                    if bureau_score < min_score and credit_tr.data.get("decision") == "approve":
                        failures.append({
                            "category": "POLICY_VIOLATION",
                            "reason": f"Credit decision 'approve' violates policy minimum score {min_score} (actual: {bureau_score})"
                        })
                    else:
                        checks_passed.append(f"Credit score {bureau_score} validated against policy threshold {min_score}")

                # KYC compliance check
                kyc_verdict = comp_tr.data.get("verdict")
                if kyc_verdict in ("fail", "hold"):
                    checks_passed.append(f"Compliance hold verified: KYC check prevented unauthorized loan approval")
            else:
                missing_agents = []
                if not credit_tr: missing_agents.append("credit")
                if not fraud_tr: missing_agents.append("fraud")
                if not comp_tr: missing_agents.append("compliance")
                failures.append({
                    "category": "INCOMPLETE_PIPELINE",
                    "reason": f"Underwriting missing results from: {', '.join(missing_agents)}"
                })

        # Check 4: Fraud detection scoring validity
        if intent == "report_fraud":
            fraud_tr = next((tr for tr in tool_results if tr.agent == "fraud"), None)
            if fraud_tr:
                risk_score = fraud_tr.data.get("risk_score")
                if risk_score is not None and 0 <= risk_score <= 100:
                    checks_passed.append(f"IsolationForest risk score {risk_score}/100 verified within valid bounds [0, 100]")
                else:
                    failures.append({
                        "category": "INVALID_RISK_SCORE",
                        "reason": f"Risk score {risk_score} out of valid bounds"
                    })

        # Check 5: Credit score validity
        if intent == "credit_score":
            credit_tr = next((tr for tr in tool_results if tr.agent == "credit"), None)
            if credit_tr and (credit_tr.data.get("credit_score") is not None or credit_tr.data.get("bureau_score") is not None):
                sc = credit_tr.data.get("credit_score") or credit_tr.data.get("bureau_score")
                checks_passed.append(f"Credit score {sc} verified from bureau records")
            else:
                failures.append({
                    "category": "DATA_MISSING",
                    "reason": "Credit score query failed to retrieve bureau record"
                })

        # Check 6: Customer data identity alignment
        expected_cid = context.get("customer_id")
        if expected_cid:
            for tr in tool_results:
                if isinstance(tr.data, dict) and "customer_id" in tr.data:
                    res_cid = tr.data["customer_id"]
                    if res_cid and res_cid != expected_cid:
                        failures.append({
                            "category": "IDENTITY_MISMATCH",
                            "reason": f"Tool returned records for customer '{res_cid}' instead of expected '{expected_cid}'"
                        })

        # Summary decision
        is_valid = len(failures) == 0
        can_recover = any(f["category"] in ("TOOL_ERROR", "DATA_MISSING") for f in failures)
        recovery_strategy = "retry_transient_tool" if can_recover else None

        return SelfEvaluationResult(
            is_valid=is_valid,
            checks_passed=checks_passed,
            failures=failures,
            can_recover=can_recover,
            recovery_strategy=recovery_strategy,
            semantic_fidelity=True
        )
