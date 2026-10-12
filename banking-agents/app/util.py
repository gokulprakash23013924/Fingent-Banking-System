from __future__ import annotations

import json
import uuid
from datetime import datetime


def fmt_inr(x: float | int, decimals: int | None = None) -> str:
    """Indian digit grouping: 500000 -> ₹5,00,000."""
    neg = x < 0
    x = abs(float(x))
    if decimals is None:
        decimals = 0 if float(x).is_integer() else 2
    s = f"{x:.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + "₹" + whole + ("." + frac if frac else "")


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat()


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def short_id(prefix: str = "") -> str:
    h = uuid.uuid4().hex[:10]
    if h.isdigit():  # keep at least one letter so an id can never be mistaken for a number
        h = "a" + h[1:]
    return prefix + h


def dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def fmt_ts(iso: str | None) -> str:
    """'2026-10-10T02:14:00' -> '10 Oct, 02:14'."""
    if not iso:
        return ""
    try:
        return parse_ts(iso).strftime("%d %b, %H:%M")
    except ValueError:
        return iso
