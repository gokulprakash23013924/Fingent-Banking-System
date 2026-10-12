"""Robust typo normalizer and fuzzy spelling corrector for banking queries.

Handles common spelling errors, phonetic typos, concatenated words/units, and
banking-specific slang/abbreviations.
"""
from __future__ import annotations

import re

# Comprehensive banking typo correction map
TYPO_MAP: dict[str, str] = {
    # Balance & Accounts
    "balnce": "balance",
    "balens": "balance",
    "balence": "balance",
    "balacne": "balance",
    "blance": "balance",
    "balanace": "balance",
    "balanc": "balance",
    "bal": "balance",
    "acount": "account",
    "accont": "account",
    "acounts": "accounts",
    "acconts": "accounts",
    "accnt": "account",
    "accnts": "accounts",
    "savngs": "savings",
    "savng": "savings",
    "svings": "savings",
    "curret": "current",
    "crrent": "current",
    "currnt": "current",

    # Transfers & Payments
    "sned": "send",
    "snd": "send",
    "sendd": "send",
    "trnsfer": "transfer",
    "transfr": "transfer",
    "tranfer": "transfer",
    "trnasfer": "transfer",
    "trasfer": "transfer",
    "paymnt": "payment",
    "pymnt": "payment",
    "paimt": "payment",
    "paymet": "payment",
    "mney": "money",
    "moni": "money",
    "monney": "money",
    "rupes": "rupees",
    "rupe": "rupees",
    "ruppes": "rupees",
    "rpees": "rupees",
    "rs": "rupees",

    # Transactions & Statements
    "transction": "transactions",
    "transctions": "transactions",
    "transacton": "transactions",
    "transactons": "transactions",
    "trasaction": "transactions",
    "trasactions": "transactions",
    "statment": "statement",
    "statmnt": "statement",
    "stmnt": "statement",
    "statemnt": "statement",
    "spendings": "spending",
    "spnding": "spending",
    "spndings": "spending",
    "recet": "recent",
    "recnt": "recent",

    # Loans & Credit
    "lon": "loan",
    "lone": "loan",
    "lons": "loans",
    "lones": "loans",
    "elgible": "eligible",
    "elgibilty": "eligibility",
    "eligiblity": "eligibility",
    "eligble": "eligible",
    "aply": "apply",
    "appli": "apply",
    "cibil": "cibil",
    "cbill": "cibil",
    "cbil": "cibil",
    "cibill": "cibil",
    "scor": "score",
    "scr": "score",
    "scoree": "score",
    "ratng": "rating",
    "ratin": "rating",
    "bureau": "bureau",
    "buro": "bureau",
    "burau": "bureau",
    "borow": "borrow",
    "borrw": "borrow",

    # Cards & Security
    "crd": "card",
    "crds": "cards",
    "cad": "card",
    "blck": "block",
    "blok": "block",
    "blcok": "block",
    "freze": "freeze",
    "frezee": "freeze",
    "stolen": "stolen",
    "frud": "fraud",
    "fraude": "fraud",
    "unrecognised": "unrecognized",
    "unauthorizd": "unauthorized",
    "unauthorised": "unauthorized",
}


def normalize_banking_query(raw_text: str) -> str:
    """Correct typos, split joined numbers and currency units, and clean punctuation."""
    if not raw_text:
        return ""

    text = raw_text.strip()

    # 1. Protect banking identifiers from digit-letter splitting (e.g. A1001, C001, T000123, LN-123)
    id_tokens = re.findall(r"\b[ACTact]\d{3,6}\b|\bLN-[\w]+\b", text)
    placeholders = {}
    for i, tok in enumerate(id_tokens):
        ph = f"__ID_TOKEN_{i}__"
        placeholders[ph] = tok
        text = text.replace(tok, ph)

    # 2. Separate numbers joined with letters/currency, e.g. "5000rupees" -> "5000 rupees", "5lakh" -> "5 lakh"
    text = re.sub(r"(\d+)([a-zA-Z]+)", r"\1 \2", text)
    text = re.sub(r"([a-zA-Z]+)(\d+)", r"\1 \2", text)

    # Restore protected banking identifiers
    for ph, orig in placeholders.items():
        text = text.replace(ph, orig)

    # 3. Token-by-token typo replacement preserving casing structure where needed
    tokens = re.split(r"(\s+|[^\w\s])", text)
    normalized_tokens = []

    for token in tokens:
        lower_token = token.lower()
        if lower_token in TYPO_MAP:
            normalized_tokens.append(TYPO_MAP[lower_token])
        else:
            normalized_tokens.append(token)

    corrected = "".join(normalized_tokens)

    # 4. Collapse extra whitespace
    corrected = re.sub(r"\s+", " ", corrected).strip()
    return corrected
