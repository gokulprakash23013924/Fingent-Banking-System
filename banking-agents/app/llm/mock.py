"""Intelligent Offline Mock LLM Adapter with Dynamic Tool Selection and Natural Dialogue.

Provides semantic tool selection, multi-intent reasoning, and conversational interaction
in mock mode without requiring an external API key.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from .client import BaseClient, LLMError, LLMResult, LLMToolCallResult


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


class MockClient(BaseClient):
    name = "mock"

    def complete(self, *, task: str, system: str, user: str, model: str,
                 max_tokens: int = 400, json_mode: bool = False) -> LLMResult:
        """Legacy completion interface for test harnesses."""
        t0 = time.perf_counter()
        if model == "mock-fail":
            raise LLMError("simulated provider failure")
        if task == "classify":
            m = re.search(r"<user_message>(.*?)</user_message>", user, re.S)
            text = (m.group(1) if m else user).lower().strip()

            # Check greetings first
            if any(text.startswith(g) for g in ["hi", "hello", "hey", "good morning", "good afternoon"]):
                out = json.dumps({"intents": [{"intent": "greeting", "confidence": 0.99}], "clarification": None})
            elif any(w in text for w in ["stolen", "block", "card", "freeze", "stop working"]):
                out = json.dumps({"intents": [{"intent": "block_card", "confidence": 0.95}], "clarification": None})
            elif any(w in text for w in ["fraud", "unrecognised", "unrecognized", "scam"]):
                out = json.dumps({"intents": [{"intent": "report_fraud", "confidence": 0.95}], "clarification": None})
            elif any(w in text for w in ["loan", "borrow", "emi"]):
                out = json.dumps({"intents": [{"intent": "loan_eligibility", "confidence": 0.95}], "clarification": None})
            elif any(w in text for w in ["transaction", "statement", "spent", "spending"]):
                out = json.dumps({"intents": [{"intent": "mini_statement", "confidence": 0.95}], "clarification": None})
            else:
                out = json.dumps({"intents": [{"intent": "check_balance", "confidence": 0.85}], "clarification": None})
        elif task == "explain":
            m = re.search(r"FACTS:\s*(\{.*\})", user, re.S)
            summary = ""
            if m:
                try:
                    summary = json.loads(m.group(1)).get("summary", "")
                except ValueError:
                    summary = ""
            out = summary or "Here is the outcome of the checks listed above."
        else:
            out = "{}"
        return LLMResult(out, model, _tokens(system) + _tokens(user), _tokens(out), (time.perf_counter() - t0) * 1000)

    def call_tools(self, *, system: str, user: str, tools: list[dict], model: str,
                   max_tokens: int = 800) -> LLMToolCallResult:
        """Dynamic tool selection and conversational dialogue for the Supervisor."""
        from .typo_normalizer import normalize_banking_query
        t0 = time.perf_counter()
        normalized_user = normalize_banking_query(user)
        text = normalized_user.strip().lower()

        # ---------------------------------------------------------
        # 1. Natural Greetings and General Conversation
        # ---------------------------------------------------------
        greeting_patterns = [
            r"^(?:hi|hey|hello|good\s+(?:morning|afternoon|evening)|howdy)\b",
            r"^(?:how are you|how's it going|can you help(?: me)?|what can you do|who are you)\b",
        ]
        if any(re.search(pat, text, re.IGNORECASE) for pat in greeting_patterns) and not any(
            w in text for w in ["balance", "transaction", "payment", "loan", "fraud", "card", "statement", "emi", "score", "send", "transfer"]
        ):
            return LLMToolCallResult(
                tool_calls=[],
                reply=(
                    "Hello! I am your Fingent banking assistant. I can help you check account balances, "
                    "review recent transactions, transfer money via Razorpay, calculate loan EMI, evaluate loan eligibility, block cards, "
                    "or investigate unrecognized payments. How may I assist you today?"
                ),
                is_greeting=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=45,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # ---------------------------------------------------------
        # 2. Ambiguous, Tough, and Out-of-Scope Requests with Clear Reasons
        # ---------------------------------------------------------
        if any(p in text for p in ["help me with my money", "what should i do next", "manage my finances", "what should i do with my money"]):
            return LLMToolCallResult(
                tool_calls=[],
                clarification=(
                    "I can assist with checking your account balances, viewing recent transactions, or reviewing loan options. "
                    "Could you clarify which of these you would like help with?"
                ),
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=35,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        if re.search(r"\b(invest|investing|investment|crypto|bitcoin|ethereum|stocks?|mutual fund|trading|shares?)\b", text):
            return LLMToolCallResult(
                tool_calls=[],
                reply=(
                    "I cannot provide investment advice or trade securities/cryptocurrencies because Fingent is restricted "
                    "to regulated commercial banking operations (accounts, deposits, card security, and lending). "
                    "I can connect you with a Relationship Manager for wealth advisory, or help with your balances, cards, or loans."
                ),
                out_of_scope=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=50,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        if re.search(r"\b(weather|temperature|forecast|cricket|football|movie|song|joke|president|prime minister)\b", text):
            return LLMToolCallResult(
                tool_calls=[],
                reply=(
                    "I cannot answer general trivia, entertainment, or weather questions. As your Fingent AI Banking Assistant, "
                    "my capabilities are specialized in banking services: checking balances, transaction history, funds transfers, "
                    "card controls, and loan processing."
                ),
                out_of_scope=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=45,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        if re.search(r"\b(cash|withdraw cash|atm cash|dispense cash)\b", text):
            return LLMToolCallResult(
                tool_calls=[],
                reply=(
                    "Physical cash cannot be dispensed through digital chat. You can withdraw cash using your active debit card "
                    "at any Fingent ATM or partner banking network across India."
                ),
                out_of_scope=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=40,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        if re.search(r"\b(ignore previous|system prompt|jailbreak|developer mode|reveal prompt|system instructions)\b", text):
            return LLMToolCallResult(
                tool_calls=[],
                reply="I cannot disclose internal system instructions or bypass security boundaries. Fingent operates under strict audit logging and customer data isolation protections.",
                out_of_scope=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=35,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        if re.search(r"\b(0 (?:percent|%)|zero interest|no documents|without documents)\b", text) and "loan" in text:
            return LLMToolCallResult(
                tool_calls=[],
                reply="Fingent cannot offer loans with zero percent interest or without standard KYC documentation. Under bank lending policy, all loans require verified KYC and adhere to regulatory rate cards (min 10.5% p.a.).",
                out_of_scope=True,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=45,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # ---------------------------------------------------------
        # 3. Dynamic Multi-Intent Detection
        # ---------------------------------------------------------
        tool_calls: list[dict[str, Any]] = []

        # Case A: Balance AND Mini Statement in single query
        # Example: "What is my balance, and show me my last five transactions?"
        has_balance = any(w in text for w in ["balance", "how much money", "how much do i have", "available funds", "available balance"])
        has_txns = any(w in text for w in ["transaction", "statement", "spent", "spending", "last 5", "last five"])

        if has_balance and has_txns:
            tool_calls.append({"tool": "get_balance", "agent": "banking", "args": {}})
            tool_calls.append({"tool": "get_transactions", "agent": "banking", "args": {"limit": 5}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=50,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case B: Fraud / Suspicious payment
        if any(w in text for w in ["not recognise", "not recognize", "didn't make", "did not make", "fraud", "unauthorised", "unauthorized", "unrecognized"]):
            # Extract amount if present
            amt_match = re.search(r"(?:₹|rs\.?|inr)?\s*([0-9,]+(?:\.[0-9]+)?)", text)
            amount = None
            if amt_match:
                cleaned = amt_match.group(1).replace(",", "")
                try:
                    val = float(cleaned)
                    if val > 100:
                        amount = val
                except ValueError:
                    pass
            tool_calls.append({"tool": "find_transaction", "agent": "fraud", "args": {"amount": amount or 48000.0}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=30,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case C: Multi-Agent Loan Application vs Loan Eligibility
        if any(w in text for w in ["apply for a loan", "apply for personal loan", "prepare a loan application", "submit loan application"]) or \
           ("apply" in text and "loan" in text and ("application" in text or "personal" in text)):
            # Parse amount & tenure
            amount = 500000.0
            tenure = None
            if "lakh" in text:
                m = re.search(r"(\d+(?:\.\d+)?)\s*lakh", text)
                if m:
                    amount = float(m.group(1)) * 100000
            elif re.search(r"\b(\d{5,8})\b", text):
                m = re.search(r"\b(\d{5,8})\b", text)
                if m:
                    amount = float(m.group(1))
            if "year" in text:
                m = re.search(r"(\d+)\s*year", text)
                if m:
                    tenure = int(m.group(1)) * 12
            elif "month" in text:
                m = re.search(r"(\d+)\s*month", text)
                if m:
                    tenure = int(m.group(1))

            args = {"amount": amount}
            if tenure is not None:
                args["tenure_months"] = tenure
            # Parallel underwriting agents: credit, fraud, compliance
            tool_calls.append({"tool": "check_eligibility", "agent": "credit", "args": args})
            tool_calls.append({"tool": "assess_recent_risk", "agent": "fraud", "args": {}})
            tool_calls.append({"tool": "get_kyc_status", "agent": "compliance", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=60,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case C-2: Credit Score / CIBIL / Bureau Profile
        if any(w in text for w in ["credit score", "cibil", "credit rating", "credit profile", "bureau score", "my score"]) or \
           ("score" in text and ("credit" in text or "bureau" in text or "cibil" in text or "my" in text)):
            tool_calls.append({"tool": "get_credit_profile", "agent": "credit", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=30,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case D: Loan Eligibility & EMI
        if any(w in text for w in ["loan", "borrow", "eligible", "eligibility"]) or "emi" in text:
            amount = 500000.0
            tenure = 36
            if "lakh" in text:
                m = re.search(r"(\d+(?:\.\d+)?)\s*lakh", text)
                if m:
                    amount = float(m.group(1)) * 100000
            if "year" in text:
                m = re.search(r"(\d+)\s*year", text)
                if m:
                    tenure = int(m.group(1)) * 12

            tool_calls.append({"tool": "check_eligibility", "agent": "credit", "args": {"amount": amount, "tenure_months": tenure}})
            if "emi" in text or "monthly" in text or "how much" in text:
                tool_calls.append({"tool": "calculate_emi", "agent": "credit", "args": {"amount": amount, "annual_rate": 10.5, "tenure_months": tenure}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=45,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case E: Balance inquiry
        if has_balance:
            tool_calls.append({"tool": "get_balance", "agent": "banking", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case F: Transaction history
        if has_txns:
            tool_calls.append({"tool": "get_transactions", "agent": "banking", "args": {"limit": 5}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case G: Card management
        if "card" in text:
            tool_calls.append({"tool": "get_card_status", "agent": "fraud", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case H: KYC / Compliance
        if any(w in text for w in ["kyc", "compliance", "pan", "aadhaar"]):
            tool_calls.append({"tool": "get_kyc_status", "agent": "compliance", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case I: Alerts
        if any(w in text for w in ["alert", "notification"]):
            tool_calls.append({"tool": "list_alerts", "agent": "notification", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case J: Transfer money
        if (any(w in text for w in ["transfer", "send", "wire", "remit", "pay"]) and not any(w in text for w in ["loan", "emi", "card", "score", "credit", "cibil"])) or "send money" in text:
            m_amt = re.search(r"\b([0-9,]+(?:\.[0-9]+)?)\b", text)
            args = {}
            if m_amt:
                try:
                    args["amount"] = float(m_amt.group(1).replace(",", ""))
                except ValueError:
                    pass
            m_aid = re.search(r"\b(A\d{4})\b", text, re.I)
            if m_aid:
                args["account_ref"] = m_aid.group(1).upper()
                args["to_account"] = m_aid.group(1).upper()
            tool_calls.append({"tool": "transfer_money", "agent": "banking", "args": args})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=30,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case K: Block card
        if any(w in text for w in ["block card", "block my card", "freeze card", "stop card", "block"]) and "card" in text:
            args = {}
            m_l4 = re.search(r"\b(\d{4})\b", text)
            if m_l4:
                args["card_last4"] = m_l4.group(1)
            tool_calls.append({"tool": "block_card", "agent": "fraud", "args": args})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Case L: Profile & Account Information
        if any(w in text for w in ["profile", "account info", "my accounts", "account details"]):
            tool_calls.append({"tool": "get_customer_profile", "agent": "banking", "args": {}})
            return LLMToolCallResult(
                tool_calls=tool_calls,
                tokens_in=_tokens(system) + _tokens(user),
                tokens_out=25,
                latency_ms=(time.perf_counter() - t0) * 1000,
                model="mock"
            )

        # Default fallback: Ask for clarification
        return LLMToolCallResult(
            tool_calls=[],
            clarification="Could you please provide a few more details so I can assist you with your banking request?",
            tokens_in=_tokens(system) + _tokens(user),
            tokens_out=30,
            latency_ms=(time.perf_counter() - t0) * 1000,
            model="mock"
        )
