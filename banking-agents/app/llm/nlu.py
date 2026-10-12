"""Unified Natural-Language Understanding (NLU) and Dynamic Tool Selection Engine.

Combines dynamic LLM-driven intent interpretation, tool selection from registry schemas,
multi-intent detection, slot validation, and natural dialogue handling.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from ..gateway.gateway import Gateway
from ..intents import INTENTS, extract_entities
from .client import get_client

# Required entities for specific intents
INTENT_REQUIRED_ENTITIES: dict[str, list[str]] = {
    "calculate_emi": ["amount", "tenure_months"],
    "transfer_money": ["amount", "account_ref"],
    "apply_loan": ["amount", "tenure_months"],
}

# Conversational greetings pattern
GREETING_PATTERN = re.compile(
    r"^(?:hi|hey|hello|good\s+(?:morning|afternoon|evening)|howdy|greetings|can you help(?: me)?|how are you|who are you)\b",
    re.IGNORECASE
)

# Ambiguous or out-of-scope patterns
AMBIGUOUS_PATTERNS = [
    (re.compile(r"help me with my money|manage my finances|what should i do with my money|what should i do next", re.IGNORECASE),
     "clarification",
     "I can assist with checking your account balances, viewing recent transactions, or reviewing loan options. Could you clarify which of these you would like help with?"),
    (re.compile(r"\b(?:invest|investing|investment)(?: my (?:savings|money))?\b|\bmutual funds?\b|\bstock market\b|\bcrypto\b|\bbitcoin\b|\btrading\b|\bshares?\b", re.IGNORECASE),
     "out_of_scope",
     "I cannot provide investment advice or trade securities/crypto because Fingent is restricted to regulated commercial banking operations. I can connect you with a relationship manager, or help you with your account balances, card controls, or loan eligibility."),
    (re.compile(r"\b(weather|temperature|forecast|cricket|football|movie|song|joke|president|prime minister)\b", re.IGNORECASE),
     "out_of_scope",
     "I cannot answer general trivia, entertainment, or weather questions. As your Fingent AI Banking Assistant, my capabilities are specialized in banking services: checking balances, transaction history, funds transfers, card controls, and loan processing."),
    (re.compile(r"\b(dispense\s+(?:\d+\s+)?cash|cash\s+from\s+(?:the\s+)?chat|withdraw\s+cash\s+here)\b", re.IGNORECASE),
     "out_of_scope",
     "Physical cash cannot be dispensed through digital chat. You can withdraw cash using your active debit card at any Fingent ATM or partner banking network across India."),
    (re.compile(r"\b(ignore previous|system prompt|jailbreak|developer mode|reveal prompt|system instructions)\b", re.IGNORECASE),
     "out_of_scope",
     "I cannot disclose internal system instructions or bypass security boundaries. Fingent operates under strict audit logging and customer data isolation protections."),
    (re.compile(r"\b(0 (?:percent|%)|zero interest|no documents|without documents)\b", re.IGNORECASE),
     "out_of_scope",
     "Fingent cannot offer loans with zero percent interest or without standard KYC documentation. Under bank lending policy, all loans require verified KYC and adhere to regulatory rate cards (min 10.5% p.a.)."),
]


# Core banking capabilities exposed to the LLM (streamlined from internal micro-tools)
CORE_SUPERVISOR_TOOLS = {
    "get_balance",
    "get_transactions",
    "transfer_funds",
    "block_card",
    "find_transaction",
    "get_credit_profile",
    "get_customer_profile",
    "check_eligibility",
    "calculate_emi",
}


def _tool_catalogue() -> list[dict]:
    from ..tools.registry import REGISTRY
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "agent": list(spec.allowed_agents)[0] if spec.allowed_agents else "banking",
            "parameters": spec.schema.model_json_schema()
        } for name, spec in REGISTRY.items()
        if name in CORE_SUPERVISOR_TOOLS
    ]


class UnifiedNLU:
    """Unified natural-language understanding with dynamic LLM-driven tool selection."""

    def __init__(self, gateway: Gateway | None = None):
        self.gateway = gateway or Gateway()

    def observe(self, message: str, customer_id: str, context: dict[str, Any] | None = None) -> Any:
        """OBSERVE phase: Understand intent, extract entities, select tools, and detect ambiguity."""
        from ..supervisor.workflow_state import ObserveResult
        text = (message or "").strip()
        context = context or {}
        settings = get_settings()

        # -------------------------------------------------------------
        # 1. Natural Greetings (No unnecessary banking tools invoked)
        # -------------------------------------------------------------
        has_banking_words = any(
            w in text.lower() for w in [
                "balance", "transaction", "payment", "loan", "fraud", "card",
                "statement", "emi", "transfer", "kyc", "alert", "lakh", "spend",
                "credit", "cibil", "score", "rating"
            ]
        )
        if GREETING_PATTERN.search(text) and not has_banking_words:
            return ObserveResult(
                goal="Natural conversational greeting",
                intent="greeting",
                entities={},
                is_greeting=True,
                greeting_response=(
                    "Hello! I am your Fingent banking assistant. I can help you check account balances, "
                    "review recent transactions, calculate loan EMI, evaluate loan eligibility, block cards, "
                    "or investigate unrecognized payments. How may I assist you today?"
                ),
                is_ambiguous=False,
                clarifying_question=None
            )

        # -------------------------------------------------------------
        # 2. Ambiguity & Out-of-Scope Detection
        # -------------------------------------------------------------
        for pattern, intent_type, response_text in AMBIGUOUS_PATTERNS:
            if pattern.search(text):
                if intent_type == "clarification":
                    return ObserveResult(
                        goal="Ambiguous financial request",
                        intent="needs_clarification",
                        entities={},
                        is_ambiguous=True,
                        clarifying_question=response_text
                    )
                elif intent_type == "out_of_scope":
                    return ObserveResult(
                        goal="Unsupported financial advisory / investment request",
                        intent="out_of_scope",
                        entities={},
                        is_ambiguous=False,
                        clarifying_question=response_text
                    )

        # -------------------------------------------------------------
        # 3. Dynamic Tool Selection via LLM or Intelligent Mock Engine
        # -------------------------------------------------------------
        client = get_client(settings)
        catalogue = _tool_catalogue()
        sys_prompt = (
            f"You are the intelligent Banking Supervisor for Fingent. Customer ID: {customer_id}. "
            "Select the minimum required tools to satisfy the user's intent. "
            "If the request involves multiple tasks (e.g. balance and mini-statement), select all required tools."
        )

        selected_tools = []
        is_greeting = False
        greeting_reply = None
        clarification_q = None
        is_out_of_scope = False

        try:
            tool_res = client.call_tools(
                system=sys_prompt,
                user=text,
                tools=catalogue,
                model=settings.tier2_model
            )
            selected_tools = tool_res.tool_calls
            is_greeting = tool_res.is_greeting
            greeting_reply = tool_res.reply
            clarification_q = tool_res.clarification
            is_out_of_scope = tool_res.out_of_scope
        except Exception:
            # Seamless graceful fallback to offline intelligence engine if external LLM quota/network fails
            try:
                from .mock import MockClient
                mock_res = MockClient().call_tools(
                    system=sys_prompt,
                    user=text,
                    tools=catalogue,
                    model="mock"
                )
                selected_tools = mock_res.tool_calls
                is_greeting = mock_res.is_greeting
                greeting_reply = mock_res.reply
                clarification_q = mock_res.clarification
                is_out_of_scope = mock_res.out_of_scope
            except Exception:
                pass

        if not selected_tools and not is_out_of_scope and not is_greeting:
            lower_txt = text.lower()
            has_bal = any(w in lower_txt for w in ["balance", "how much money", "how much do i have", "funds"])
            has_tx = any(w in lower_txt for w in ["transaction", "statement", "spent", "spending", "recent payment", "last 5", "last five"])
            if has_bal and has_tx:
                selected_tools = [
                    {"tool": "get_balance", "agent": "banking", "args": {}},
                    {"tool": "get_transactions", "agent": "banking", "args": {"limit": 5}}
                ]
            elif ("loan" in lower_txt or "eligible" in lower_txt or "apply" in lower_txt) and "emi" in lower_txt:
                selected_tools = [
                    {"tool": "check_eligibility", "agent": "credit", "args": {}},
                    {"tool": "calculate_emi", "agent": "credit", "args": {}}
                ]

        if (is_greeting or (not selected_tools and greeting_reply and not is_out_of_scope)) and greeting_reply:
            return ObserveResult(
                goal="Natural conversational dialogue",
                intent="greeting",
                entities={},
                is_greeting=True,
                greeting_response=greeting_reply,
                is_ambiguous=False
            )

        if is_out_of_scope:
            return ObserveResult(
                goal="Unsupported financial advisory request",
                intent="out_of_scope",
                entities={},
                is_ambiguous=False,
                clarifying_question=greeting_reply or "That operation is outside supported banking policies. Escalating to Relationship Manager."
            )

        if clarification_q and not context.get("pending_intent"):
            return ObserveResult(
                goal="Ambiguous financial request",
                intent="needs_clarification",
                entities={},
                is_ambiguous=True,
                clarifying_question=clarification_q
            )

        # -------------------------------------------------------------
        # 4. Extract Entities & Map Primary Intent
        # -------------------------------------------------------------
        entities = extract_entities(text)
        if context.get("pending_entities"):
            entities = {**context["pending_entities"], **entities}

        # Merge tool-level arguments into entities
        for tc in selected_tools:
            if tc.get("args"):
                entities.update(tc["args"])

        # Determine primary intent and multi-intent list
        tool_names = [tc["tool"] for tc in selected_tools]
        multi_intents = []

        if "get_balance" in tool_names:
            multi_intents.append("check_balance")
        if "get_transactions" in tool_names:
            multi_intents.append("mini_statement")
        if "get_customer_profile" in tool_names:
            multi_intents.append("account_info")
        if "find_transaction" in tool_names or "score_transaction" in tool_names:
            multi_intents.append("report_fraud")
        if "check_eligibility" in tool_names:
            if "assess_recent_risk" in tool_names or "get_kyc_status" in tool_names:
                multi_intents.append("apply_loan")
            else:
                multi_intents.append("loan_eligibility")
        if "calculate_emi" in tool_names and "apply_loan" not in multi_intents:
            multi_intents.append("calculate_emi")
        if "block_card" in tool_names or any(w in text.lower() for w in ["block card", "block my card", "freeze card", "stop card"]):
            multi_intents.append("block_card")
        elif "get_card_status" in tool_names or "card" in text.lower():
            multi_intents.append("card_status")
        if "transfer_money" in tool_names or re.search(r"\b(transfer|send money|send|wire|pay|remit)\b", text, re.IGNORECASE):
            multi_intents.append("transfer_money")
        if "get_kyc_status" in tool_names and "apply_loan" not in multi_intents:
            multi_intents.append("kyc_status")
        if "get_credit_profile" in tool_names or "get_bureau_score" in tool_names:
            multi_intents.append("credit_score")
        if "list_alerts" in tool_names:
            multi_intents.append("view_alerts")

        if context.get("pending_intent"):
            primary_intent = context["pending_intent"]
        else:
            primary_intent = multi_intents[0] if multi_intents else self._fallback_intent(text, entities)

        # Multi-intent loan application check
        if re.search(r"apply (?:for )?(?:a )?(?:personal )?loan|prepare a loan application|submit loan application", text, re.IGNORECASE):
            primary_intent = "apply_loan"

        # Check required slots
        missing = []
        if primary_intent in INTENT_REQUIRED_ENTITIES:
            req_keys = INTENT_REQUIRED_ENTITIES[primary_intent]
            missing = [k for k in req_keys if k not in entities or entities[k] is None]
            if missing and not clarification_q:
                if "amount" in missing and "tenure_months" in missing:
                    clarification_q = "How much would you like to borrow and for what tenure (e.g. ₹5 lakh for 3 years)?"
                elif "amount" in missing:
                    clarification_q = "Could you specify the amount you would like for this request?"
                elif "tenure_months" in missing:
                    clarification_q = "What repayment tenure would you prefer (e.g. 1 year, 3 years, 5 years)?"
            elif not missing:
                clarification_q = None

        goal_descriptions = {
            "check_balance": "Retrieve current account balance",
            "mini_statement": "Retrieve recent transaction statement",
            "card_status": "Inspect payment card status and limits",
            "report_fraud": "Investigate suspicious payment and assess fraud risk",
            "credit_score": "Retrieve credit bureau profile and CIBIL score",
            "loan_eligibility": "Evaluate loan eligibility and maximum borrowing capacity",
            "calculate_emi": "Calculate monthly loan EMI and interest breakdown",
            "apply_loan": "Process personal loan application with cross-agent underwriting",
            "transfer_money": "Initiate inter-account funds transfer",
            "view_alerts": "Review active security and banking notifications",
            "kyc_status": "Verify regulatory KYC compliance status",
            "greeting": "Conversational Greeting",
            "out_of_scope": "Unsupported request requiring human escalation",
        }
        goal = goal_descriptions.get(primary_intent, f"Execute banking request ({primary_intent})")

        return ObserveResult(
            goal=goal,
            intent=primary_intent,
            entities=entities,
            missing_entities=missing,
            is_ambiguous=bool(clarification_q),
            clarifying_question=clarification_q,
            selected_tools=selected_tools,
            multi_intent=multi_intents,
            is_mock=(settings.llm_provider == "mock")
        )

    def _fallback_intent(self, text: str, entities: dict[str, Any]) -> str:
        """Fallback classifier if no tool calls were resolved."""
        lower = text.lower()
        if any(w in lower for w in ["fraud", "recognise", "recognize", "unauthorised", "unauthorized", "didn't make", "did not make"]):
            return "report_fraud"
        if any(w in lower for w in ["credit score", "cibil", "credit rating", "credit profile", "bureau score", "my score"]):
            return "credit_score"
        if any(w in lower for w in ["apply for a loan", "apply loan", "apply for personal loan"]):
            return "apply_loan"
        if any(w in lower for w in ["emi", "monthly payment", "calculate emi"]):
            return "calculate_emi"
        if any(w in lower for w in ["eligible", "eligibility", "can i get", "how much can i borrow", "loan"]):
            return "loan_eligibility"
        if any(w in lower for w in ["profile", "account info", "my accounts", "account details"]):
            return "account_info"
        if any(w in lower for w in ["balance", "how much money", "how much do i have", "available funds", "my funds"]):
            return "check_balance"
        if any(w in lower for w in ["transactions", "statement", "spent", "spending", "recent payments"]):
            return "mini_statement"
        if any(w in lower for w in ["card", "block"]):
            return "card_status"
        if any(w in lower for w in ["kyc", "compliance", "pan"]):
            return "kyc_status"
        if any(w in lower for w in ["alert", "notification"]):
            return "view_alerts"
        return "needs_clarification"
