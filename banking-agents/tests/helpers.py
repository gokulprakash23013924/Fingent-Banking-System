"""Shared test setup: one throw-away database and model directory per test run (the real data/ is never touched)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = None


def setup() -> str:
    """Point the app at a temp DB, seed it once and return its path."""
    global _TMP
    if _TMP is None:
        _TMP = tempfile.mkdtemp(prefix="bank-test-")
        os.environ["BANK_DB_PATH"] = os.path.join(_TMP, "bank.db")
        os.environ["MODELS_DIR"] = os.path.join(_TMP, "models")
        os.environ["LLM_PROVIDER"] = "mock"
        os.environ["LLM_ENABLED"] = "true"
        os.environ["LLM_TIER2_MODEL"] = "mock-small"
        os.environ["LLM_TIER3_MODEL"] = "mock-large"
        os.environ["LLM_FALLBACK_MODEL"] = "mock-small"
        os.environ["PIPELINE_MODE"] = "ladder"
        reseed()
    return os.environ["BANK_DB_PATH"]


def reseed() -> None:
    from data.seed import seed
    from app.ml import fraud
    seed(reset=True)
    fraud.reset_cache()
    p = fraud.model_path()
    if os.path.exists(p):
        os.remove(p)
