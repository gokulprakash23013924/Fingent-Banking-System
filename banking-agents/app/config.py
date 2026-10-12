"""Settings (environment) and policies (YAML). Read lazily so tests can override env vars."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Runtime overrides set through the API (for example the "LLM available" demo switch).
runtime: dict = {}


def _load_dotenv(override: bool = False) -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.split(" #")[0].strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = val


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _path(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else ROOT / q)


@dataclass(frozen=True)
class Settings:
    db_path: str
    models_dir: str
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    tier2_model: str
    tier3_model: str
    fallback_model: str
    llm_enabled: bool
    max_tokens_per_request: int
    max_llm_calls: int
    max_iterations: int
    price_in_per_1k: float
    price_out_per_1k: float
    mode: str  # "ladder" | "llm_only"
    stream_enabled: bool
    stream_interval: float


def get_settings() -> Settings:
    _load_dotenv(override=False)
    return Settings(
        db_path=_path(_env("BANK_DB_PATH", "data/bank.db")),
        models_dir=_path(_env("MODELS_DIR", "models")),
        llm_provider=_env("LLM_PROVIDER", "mock").lower(),
        llm_api_key=_env("LLM_API_KEY"),
        llm_base_url=_env("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        tier2_model=_env("LLM_TIER2_MODEL", "mock-small"),
        tier3_model=_env("LLM_TIER3_MODEL", "mock-large"),
        fallback_model=_env("LLM_FALLBACK_MODEL", "mock-small"),
        llm_enabled=runtime.get("llm_enabled", _bool(_env("LLM_ENABLED", "true"))),
        max_tokens_per_request=int(_env("MAX_TOKENS_PER_REQUEST", "4000")),
        max_llm_calls=int(_env("MAX_LLM_CALLS_PER_REQUEST", "4")),
        max_iterations=int(_env("MAX_ITERATIONS", "12")),
        price_in_per_1k=float(_env("LLM_PRICE_IN_PER_1K", "0") or 0),
        price_out_per_1k=float(_env("LLM_PRICE_OUT_PER_1K", "0") or 0),
        mode=_env("PIPELINE_MODE", "ladder").lower(),
        stream_enabled=_bool(_env("STREAM_ENABLED", "false")),
        stream_interval=float(_env("STREAM_INTERVAL_SECONDS", "5")),
    )


@lru_cache(maxsize=4)
def _load_policy(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_policy() -> dict:
    return _load_policy(_path(_env("POLICY_PATH", "config/policies.yaml")))
