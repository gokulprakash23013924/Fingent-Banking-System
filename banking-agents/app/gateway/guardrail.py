"""Output guardrail and prompt-injection defence.

* untrusted text (transaction descriptions, merchant names) is sanitised before a model sees it
* every number in an LLM-written answer must appear in the tool output it was given
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .pii import mask_pii

_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)"
    r"|system\s+prompt|you\s+are\s+now|approve\s+(all|every)\b|reveal\s+.{0,20}(prompt|key|password)",
    re.IGNORECASE,
)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_text(s: str, max_len: int = 160) -> tuple[str, bool]:
    s = _CTRL.sub(" ", s)
    flagged = bool(_INJECTION.search(s))
    if flagged:
        return "[removed: suspicious text]", True
    return (s[:max_len] + "...") if len(s) > max_len else s, False


def sanitize_obj(obj) -> tuple[object, int]:
    """Return (clean copy, number of strings that looked like instructions)."""
    flagged = 0

    def walk(o):
        nonlocal flagged
        if isinstance(o, str):
            clean, f = sanitize_text(o)
            flagged += int(f)
            return clean
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [walk(v) for v in o]
        return o

    return walk(obj), flagged


# ---------------------------------------------------------------- grounding
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?!\w)")
_ANY_NUM = re.compile(r"\d+(?:\.\d+)?")


def facts_numbers(facts) -> set[float]:
    text = json.dumps(facts, default=str).replace(",", "")
    base = {float(x) for x in _ANY_NUM.findall(text)}
    out = set(base)
    for v in base:
        out.update({round(v), round(v, 1), round(v, 2)})
        if v >= 1000:
            out.update({v / 1e5, v / 1e3, v / 1e7})
        if v >= 12:
            out.add(v / 12)
        if 0 < v <= 10:
            out.add(round(v * 100, 1))
            out.add(round(v * 100))
    return out


def ungrounded_numbers(text: str, facts) -> list[str]:
    known = facts_numbers(facts)
    bad: list[str] = []
    for tok in _NUM.findall(text):
        v = float(tok.replace(",", ""))
        if v <= 3:
            continue
        tol = 0.51 if v >= 100 else 0.051
        if not any(abs(v - k) <= tol for k in known):
            bad.append(tok)
    return bad


@dataclass
class GuardResult:
    text: str
    pii_masked: int = 0
    ungrounded: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.ungrounded


def guard_output(text: str, facts=None, *, check_grounding: bool = True) -> GuardResult:
    m = mask_pii(text)
    bad = ungrounded_numbers(m.text, facts) if (check_grounding and facts is not None) else []
    return GuardResult(text=m.text, pii_masked=len(m.findings), ungrounded=bad)
