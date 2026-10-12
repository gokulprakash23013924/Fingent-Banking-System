"""FastAPI app. Run: uvicorn app.main:app --reload --port 8000   (interactive docs at /docs)

Routes are deliberately thin: each one calls a function in handlers.py, where all the logic lives.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config, handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    handlers.startup()
    if config.get_settings().stream_enabled:
        handlers.stream_control("start")
    yield
    handlers.stream_control("stop")


app = FastAPI(title="Multi-agent banking core", version="1.0.0", lifespan=lifespan,
              description="Supervisor + specialised agents over a simulated bank. LLM-last routing.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
                   allow_methods=["*"], allow_headers=["*"])


class LoginIn(BaseModel):
    username: str
    password: str


class ChatIn(BaseModel):
    message: str = Field("", max_length=2000)
    customer_id: str = Field(..., examples=["C001"])
    role: Literal["customer", "rm", "supervisor"] = "customer"
    conversation_id: str | None = None
    action: str | None = Field(None, description="Optional explicit intent from a UI button, e.g. check_balance")
    entities: dict | None = Field(None, description="Optional structured values: amount, tenure_months, txn_id, account_ref, card_last4, count")


class ApprovalIn(BaseModel):
    approve: bool
    customer_id: str
    role: Literal["customer", "rm", "supervisor"] = "customer"


class SimulateIn(BaseModel):
    customer_id: str | None = None
    anomalous: bool | None = None


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except handlers.HandlerError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return authorization.strip()


@app.get("/health")
def health():
    return {"ok": True, "llm": handlers.llm_status()}


# ---- authentication
@app.post("/auth/login")
def login(body: LoginIn):
    return _run(handlers.login, body.username, body.password)


@app.post("/auth/logout")
def logout(authorization: str | None = Header(None)):
    token = _extract_token(authorization)
    return handlers.logout(token)


@app.get("/auth/me")
def me(authorization: str | None = Header(None)):
    token = _extract_token(authorization)
    return handlers.get_current_user(token)


@app.get("/auth/demo-users")
def demo_users():
    return handlers.get_demo_users()


# ---- the agent system
@app.post("/chat")
def chat(body: ChatIn, authorization: str | None = Header(None)):
    return _run(handlers.chat, body.model_dump(), _extract_token(authorization))


@app.post("/approvals/{group_id}")
def decide(group_id: str, body: ApprovalIn, authorization: str | None = Header(None)):
    return _run(handlers.decide_approval, group_id, body.model_dump(), _extract_token(authorization))


@app.get("/approvals/pending")
def pending(customer_id: str | None = None, authorization: str | None = Header(None)):
    return handlers.pending_approvals(customer_id, _extract_token(authorization))


# ---- simulated back-end systems (role/token isolated)
@app.get("/customers")
def customers(authorization: str | None = Header(None)):
    return handlers.list_customers(_extract_token(authorization))


@app.get("/customers/{cid}")
def customer(cid: str, authorization: str | None = Header(None)):
    return _run(handlers.customer, cid, _extract_token(authorization))


@app.get("/accounts/{account_id}/balance")
def balance(account_id: str, authorization: str | None = Header(None)):
    return _run(handlers.balance, account_id, _extract_token(authorization))


@app.get("/accounts/{account_id}/transactions")
def transactions(account_id: str, limit: int = Query(10, ge=1, le=100)):
    return _run(handlers.transactions, account_id, limit)


@app.get("/transactions/{txn_id}")
def get_transaction(txn_id: str):
    return _run(handlers.get_transaction, txn_id)


@app.get("/transactions/{txn_id}/risk")
def risk(txn_id: str):
    return _run(handlers.txn_risk, txn_id)


@app.post("/cards/{card_id}/block")
def block_card(card_id: str, reason: str = Query("customer request")):
    return _run(handlers.block_card, card_id, reason)


@app.post("/disputes")
def create_dispute(body: dict):
    return _run(handlers.create_dispute, body)


@app.post("/loans/eligibility")
def loan_eligibility(body: dict):
    return _run(handlers.loan_eligibility, body)


@app.post("/loans/applications")
def loan_applications(body: dict):
    return _run(handlers.loan_applications, body)


@app.get("/bureau/{cid}/score")
def bureau(cid: str):
    return _run(handlers.bureau, cid)


@app.get("/kyc/{cid}")
def kyc(cid: str):
    return _run(handlers.kyc, cid)


@app.get("/alerts")
def alerts(customer_id: str | None = None, after_id: int = 0, limit: int = Query(20, ge=1, le=100)):
    return handlers.alerts(customer_id, after_id, limit)


# ---- observability, controls, simulation
@app.get("/tools")
def tools():
    return handlers.tools_catalogue()


@app.get("/intents")
def intents():
    return handlers.intents_catalogue()


@app.get("/audit")
def audit_log(trace_id: str | None = None, limit: int = Query(50, ge=1, le=500)):
    return handlers.get_audit(trace_id, limit)


@app.get("/metrics")
def metrics_summary():
    return handlers.get_metrics()


@app.post("/metrics/reset")
def metrics_reset():
    return handlers.reset_metrics()


@app.get("/admin/llm")
def llm_get():
    return handlers.llm_status()


@app.post("/admin/llm")
def llm_set(enabled: bool):
    return handlers.set_llm(enabled)


@app.post("/simulate/transaction")
def simulate(body: SimulateIn):
    return _run(handlers.simulate, body.customer_id, body.anomalous)


@app.post("/stream/{action}")
def stream_ctl(action: Literal["start", "stop", "status"]):
    return handlers.stream_control(action)
