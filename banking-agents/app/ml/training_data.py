"""Synthetic training utterances for the tier 1 intent classifier.

Phrasings are written by hand and varied with prefixes, suffixes, slot values, typos and Hinglish so the
classifier sees realistic noise. Deterministic for a given seed.
"""
from __future__ import annotations

import random

AMT = ["5 lakh", "₹500000", "3 lakhs", "2,00,000", "10 lakh", "rs 300000", "1.5 lakh", "₹7,50,000", "4 lakh", "800000"]
TEN = ["3 years", "36 months", "5 years", "24 months", "1 year", "48 months", "2 years", "60 months"]
CNT = ["5", "3", "10", "7", "2"]
SMALL = ["500", "2000", "5000", "10000", "₹1,500", "rs 750", "25000", "48,000", "₹32000"]
ACCT = ["123456789012", "987654321098", "445566778899", "A1002", "A1005", "A1007", "A1008"]
LAST4 = ["4821", "1234", "9087"]

BASE: dict[str, list[str]] = {
    "check_balance": [
        "what is my balance", "check balance", "how much money do I have", "account balance", "show my balance",
        "balance enquiry", "how much is in my savings account", "available balance please", "mera balance kitna hai",
        "balance batao", "bal check", "what's in my account", "money left in my account", "tell me my current balance",
        "how much do i have in the bank", "savings account balance", "can you tell me the balance", "current balance of my account",
    ],
    "mini_statement": [
        "show my last transactions", "mini statement", "recent transactions", "last {cnt} transactions", "show statement",
        "what did I spend recently", "transaction history", "list my recent payments", "my account statement",
        "passbook", "recent transactions dikhao", "show me the past few transactions", "last {cnt} txns", "what were my latest debits",
        "give me my statement", "view my transaction history", "show the latest {cnt} payments",
    ],
    "card_status": [
        "is my card active", "card status", "status of my debit card", "check my card", "is my card blocked",
        "what is the limit on my card", "card details", "is my card working", "show my card info", "card limit kitna hai",
        "my debit card ending {last4} status", "is card {last4} active",
    ],
    "account_info": [
        "show my account details", "my profile", "what accounts do I have", "account information", "list my accounts",
        "customer details", "which accounts are linked to me", "show my customer profile", "how many accounts do i have",
        "tell me about my accounts", "my account number and type",
    ],
    "report_fraud": [
        "I did not make this transaction", "unrecognized transaction on my account", "there is a payment I don't recognise",
        "someone used my card", "suspicious transaction on my account", "fraud on my account", "I see a charge I did not authorize",
        "this payment is not mine", "unauthorised debit from my account", "I didn't make this payment of {small}",
        "dispute a transaction", "mujhe ye transaction nahi pehchan", "unknown debit from my account", "money got debited but I didn't do it",
        "report a fraudulent charge", "i didnt authorise the {small} payment", "what is this {small} transaction i dont remember it",
        "unknown payment of {small} showing in my account", "someone has stolen money from my account", "i think my account was hacked",
    ],
    "block_card": [
        "block my card", "I lost my card", "freeze my debit card", "my card was stolen", "please block card",
        "stop my card immediately", "card block kar do", "disable my card", "block card ending {last4}", "my card is lost please block it",
        "i want to block my debit card", "hotlist my card",
    ],
    "loan_eligibility": [
        "am I eligible for a loan", "can I get a personal loan", "loan eligibility", "how much loan can I get",
        "check my loan eligibility for {amt}", "can I get a loan of {amt} for {ten}", "will I qualify for a loan", "loan milega kya",
        "eligibility for {amt} loan", "what loan amount am I eligible for", "do i qualify for a {amt} loan", "can i borrow {amt}",
        "how much can i borrow", "am i eligible for {amt} over {ten}",
    ],
    "calculate_emi": [
        "calculate emi", "what will be the emi for {amt} for {ten}", "emi for a loan of {amt}", "monthly installment for {amt} over {ten}",
        "emi calculator", "how much emi will I pay", "emi kitna hoga", "monthly payment on a {amt} loan", "emi on {amt} for {ten}",
        "work out the emi for {amt}", "what would my monthly instalment be for {amt} for {ten}",
    ],
    "apply_loan": [
        "I want to apply for a loan", "apply for a personal loan of {amt}", "I need a loan", "submit a loan application",
        "I would like to take a loan", "start loan application", "loan apply karna hai", "apply loan {amt} for {ten}",
        "process my loan request", "i want a personal loan of {amt}", "please apply a {amt} loan for me for {ten}", "i want to take a {amt} loan",
        "open a loan application", "can you apply for a loan for me",
    ],
    "loan_status": [
        "status of my loan application", "loan application status", "where is my loan application", "did my loan get approved",
        "track my loan", "loan status", "has my loan been approved yet", "what happened to my loan request", "check my loan application",
    ],
    "transfer_money": [
        "transfer {small} to account {acct}", "send money to {acct}", "pay {small} to account {acct}", "I want to transfer funds",
        "send rs {small} to {acct}", "fund transfer", "move money to another account", "paise bhejna hai", "transfer {small} to {acct}",
        "i need to send {small} to someone", "make a payment of {small} to account {acct}", "neft {small} to {acct}",
    ],
    "view_alerts": [
        "show my alerts", "any fraud alerts", "notifications", "what alerts do I have", "show alerts", "recent alerts",
        "any new notifications", "do i have any alerts", "alert history", "were there any security alerts on my account",
    ],
    "kyc_status": [
        "is my kyc complete", "kyc status", "check my kyc", "do I need to update my kyc", "is my kyc verified", "kyc pending hai kya",
        "is my kyc up to date", "when does my kyc expire", "kyc re-verification", "has my kyc been approved", "what is the status of my kyc",
        "do i have to redo my kyc", "kyc update karna hai kya", "is my kyc valid",
    ],
    "explain_decision": [
        "why was my loan declined", "why did you block my card", "explain the decision", "why was it rejected",
        "reason for that decision", "why", "explain why", "how did you decide", "why was my application refused",
        "can you explain that decision", "what was the reason for the rejection", "why was my loan not approved",
    ],
    "help": [
        "help", "what can you do", "hi", "hello", "menu", "options", "how can you help me", "start", "hey there",
        "good morning", "what services do you offer", "hi can you help me",
    ],
    "out_of_scope": [
        "invest my savings", "which mutual fund should I buy", "give me stock tips", "should I buy gold", "best investment plan",
        "what is the weather today", "tell me a joke", "who won the match", "how do I file taxes", "write me a poem",
        "which shares will go up", "should i invest in bitcoin", "what is the capital of france", "recommend a good movie",
        "where should i put my money to grow it", "how do i invest in the stock market",
    ],
}

PREFIX = ["hi ", "hey ", "please ", "pls ", "can you ", "could you ", "i want to know ", "bro ", "hello, ", "quick question: ", "tell me ", "i need to ask, "]
SUFFIX = [" please", " now", " asap", " pls", "?", " thanks", " today", " urgently", " bhai"]


def _typo(s: str, rng: random.Random) -> str:
    if len(s) < 6:
        return s
    i = rng.randrange(1, len(s) - 2)
    kind = rng.choice(["swap", "drop", "dup"])
    if kind == "swap":
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if kind == "drop":
        return s[:i] + s[i + 1:]
    return s[:i] + s[i] + s[i:]


def _fill(s: str, rng: random.Random) -> str:
    return s.format(amt=rng.choice(AMT), ten=rng.choice(TEN), cnt=rng.choice(CNT), small=rng.choice(SMALL),
                    acct=rng.choice(ACCT), last4=rng.choice(LAST4))


def generate(seed: int = 7, per_intent: int = 70) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    xs: list[str] = []
    ys: list[str] = []
    for intent, bases in BASE.items():
        seen: set[str] = set()
        attempts = 0
        while len(seen) < per_intent and attempts < per_intent * 30:
            attempts += 1
            s = _fill(rng.choice(bases), rng)
            if rng.random() < 0.35:
                s = rng.choice(PREFIX) + s
            if rng.random() < 0.3:
                s = s + rng.choice(SUFFIX)
            if rng.random() < 0.25:
                s = _typo(s, rng)
            r = rng.random()
            if r < 0.15:
                s = s.upper()
            elif r < 0.25:
                s = s.capitalize()
            if s not in seen:
                seen.add(s)
                xs.append(s)
                ys.append(intent)
    return xs, ys
