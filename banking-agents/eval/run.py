"""Routing benchmark: python -m eval.run [--mode ladder|llm_only|offline] [--runs 3]

ladder    full LLM-last ladder (default)
llm_only  baseline: tiers 0-1 disabled, every request is classified by an LLM
offline   ladder with the LLM switched off (tiers 0-1 only; unsure requests must become clarifying questions)
Runs on a throw-away database. With LLM_PROVIDER=mock the LLM numbers come from a keyword stub, not a real model.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ladder", "llm_only", "offline"], default="ladder")
    ap.add_argument("--runs", type=int, default=3, help="repeat each prompt to measure determinism")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.json"))
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="bank-eval-")
    os.environ["BANK_DB_PATH"] = os.path.join(tmp, "bank.db")
    os.environ["MODELS_DIR"] = os.path.join(tmp, "models")
    os.environ["PIPELINE_MODE"] = "llm_only" if a.mode == "llm_only" else "ladder"
    if a.mode == "offline":
        os.environ["LLM_ENABLED"] = "false"

    from app import config
    from data.seed import seed
    from app.gateway.gateway import Gateway
    from app.ladder import Ladder
    from app.state import RequestState, Session
    from app.ml.intent_model import get_intent_model

    seed(reset=True)
    get_intent_model()
    s = config.get_settings()
    if a.mode == "llm_only" and not Gateway().available():
        sys.exit("llm_only needs a working LLM provider (set LLM_PROVIDER / LLM_API_KEY, or LLM_PROVIDER=mock for a dry run)")
    ladder = Ladder(Gateway())
    rows = [json.loads(l) for l in (ROOT / "eval" / "prompts.jsonl").read_text().splitlines() if l.strip()]

    correct = no_llm = tokens = clar_ok = clar_total = stable = 0
    lat: list[float] = []
    by_tier: dict[int, int] = {}
    misses = []
    for r in rows:
        sigs = set()
        for k in range(a.runs):
            st = RequestState.new(Session("C001"), "eval", r["text"])
            t0 = time.perf_counter()
            res = ladder.classify(r["text"], st)
            ms = (time.perf_counter() - t0) * 1000
            got = sorted(i.intent for i in res.items) or ["clarify"]
            sigs.add(tuple(got))
            if k == 0:
                lat.append(ms)
                tokens += st.tokens_in + st.tokens_out
                no_llm += int(st.routing_calls == 0)
                by_tier[res.tier] = by_tier.get(res.tier, 0) + 1
                exp = sorted(r["expected"])
                ok = got == exp
                correct += int(ok)
                if exp == ["clarify"]:
                    clar_total += 1
                    clar_ok += int(ok)
                if not ok:
                    misses.append({"text": r["text"], "expected": exp, "got": got, "tier": res.tier})
        stable += int(len(sigs) == 1)
    n = len(rows)
    lat.sort()
    out = {"mode": a.mode, "provider": s.llm_provider, "prompts": n, "routing_accuracy": round(correct / n, 3),
           "llm_avoidance_rate": round(no_llm / n, 3), "by_tier": {str(k): v for k, v in sorted(by_tier.items())},
           "tokens_per_prompt": round(tokens / n, 1), "latency_ms_p50": round(lat[n // 2], 2), "latency_ms_p95": round(lat[int(n * .95)], 2),
           "determinism": round(stable / n, 3), "clarify_cases_ok": f"{clar_ok}/{clar_total}", "misses": misses}
    print(f"\nmode={a.mode} provider={s.llm_provider}{' (keyword stub, not a real model)' if s.llm_provider == 'mock' else ''}")
    for k in ("prompts", "routing_accuracy", "llm_avoidance_rate", "by_tier", "tokens_per_prompt", "latency_ms_p50", "latency_ms_p95", "determinism", "clarify_cases_ok"):
        print(f"  {k:20} {out[k]}")
    if misses:
        print("  misses:")
        for m in misses:
            print(f"    tier {m['tier']}  {m['text'][:60]!r}: expected {m['expected']} got {m['got']}")
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
