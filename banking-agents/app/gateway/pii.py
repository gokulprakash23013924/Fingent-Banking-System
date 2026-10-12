"""PII detection and masking. Raw text stays in-process; models, logs and audit rows only see masked text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("CARD", re.compile(r"(?<![A-Za-z0-9])(?:\d{4}[ -]){3}\d{4}(?![A-Za-z0-9])|(?<![A-Za-z0-9])\d{16}(?![A-Za-z0-9])")),
    ("AADHAAR", re.compile(r"(?<![A-Za-z0-9])\d{4}\s\d{4}\s\d{4}(?![A-Za-z0-9])")),
    ("PHONE", re.compile(r"(?<![A-Za-z0-9])(?:\+91[\s-]?)?[6-9]\d{9}(?![A-Za-z0-9])")),
    ("ACCOUNT", re.compile(r"(?<![A-Za-z0-9])\d{9,18}(?![A-Za-z0-9])")),
]


@dataclass
class MaskResult:
    text: str
    findings: list[str] = field(default_factory=list)


def mask_pii(text: str) -> MaskResult:
    findings: list[str] = []

    def make(label: str):
        def repl(m: re.Match) -> str:
            findings.append(label)
            if label == "PAN":
                return "[PAN]"
            digits = re.sub(r"\D", "", m.group(0))
            return f"[{label}:****{digits[-4:]}]"
        return repl

    out = text
    for label, pat in _PATTERNS:
        out = pat.sub(make(label), out)
    return MaskResult(out, findings)


def mask_obj(obj):
    """Recursively mask every string inside dicts, lists and tuples."""
    if isinstance(obj, str):
        return mask_pii(obj).text
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v) for v in obj]
    return obj
