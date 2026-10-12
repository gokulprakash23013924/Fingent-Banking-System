"""Framework-free request handlers. The FastAPI routes in main.py only translate HTTP to these calls,
so everything here is testable without a web server (and re-usable from a CLI, a worker or another framework)."""
from __future__ import annotations

import os
import threading

from . import config, db, metrics, services, stream
from .gateway.gateway import Gateway
from .intents import INTENTS
from .ml import fraud
from .ml.intent_model import get_intent_model
from .supervisor import Supervisor
from .tools import approvals, audit, definitions  # noqa: F401
from .tools.registry import REGISTRY

_sup: Supervisor | None = None
_lock = threading.Lock()
_runner: stream.StreamRunner | None = None


class HandlerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def supervisor() -> Supervisor:
    global _sup
    with _lock:
        if _sup is None:
            _sup = Supervisor(Gateway())
        return _sup


def startup(seed_if_missing: bool = True) -> dict:
    """Create and seed the database on first run and warm the two small models."""
    path = config.get_settings().db_path
    seeded = False
    if seed_if_missing and not os.path.exists(path):
        from data.seed import seed
        seed(reset=True)
        seeded = True
    db.init_db()
    from .auth import init_auth_db
    init_auth_db()
    get_intent_model()
    fraud.get_model()
    return {"db": path, "seeded": seeded}


# ---------------------------------------------------------------- authentication
def login(username: str, password: str) -> dict:
    from . import auth
    user = auth.authenticate_user(username, password)
    if not user:
        raise HandlerError(401, "Invalid username or password")
    token = auth.create_session(user)
    return {
        "ok": True,
        "token": token,
        "user": user.to_dict()
    }


def logout(token: str | None) -> dict:
    from . import auth
    auth.invalidate_session(token)
    return {"ok": True}


def get_current_user(token: str | None) -> dict:
    from . import auth
    sess = auth.get_session(token)
    if not sess:
        return {"authenticated": False, "user": None}
    user, _ = sess
    return {"authenticated": True, "user": user.to_dict()}


def get_demo_users() -> list[dict]:
    from . import auth
    return auth.get_all_demo_users()


def _resolve_session(token: str | None, customer_id: str | None, role: str | None) -> tuple[str, str]:
    from . import auth
    sess = auth.get_session(token) if token else None
    if sess:
        user, session_obj = sess
        # Server-side authentication enforces customer identity for customers
        cid = user.customer_id if user.role == "customer" else (customer_id or "")
        return cid, session_obj.role
    return customer_id or "", role or "customer"


# ---------------------------------------------------------------- chat + approvals
def chat(body: dict, token: str | None = None) -> dict:
    cid, role = _resolve_session(token, body.get("customer_id"), body.get("role"))
    msg = (body.get("message") or "").strip()
    if not msg and not body.get("action"):
        raise HandlerError(422, "message is required")
    if len(msg) > 2000:
        raise HandlerError(422, "message too long")
    return supervisor().handle(msg, cid, role,
                               body.get("conversation_id"), body.get("action"), body.get("entities"))


def decide_approval(group_id: str, body: dict, token: str | None = None) -> dict:
    cid, role = _resolve_session(token, body.get("customer_id"), body.get("role"))
    return supervisor().decide_approval(group_id, bool(body.get("approve")), cid, role)


def pending_approvals(customer_id: str | None, token: str | None = None) -> list[dict]:
    from . import auth
    sess = auth.get_session(token) if token else None
    if sess:
        user, _ = sess
        if user.role == "customer":
            return approvals.pending_for(user.customer_id)
        # Supervisors can view all pending approvals across the bank
        return approvals.pending_for(None)
    return approvals.pending_for(customer_id)


# ---------------------------------------------------------------- read-only back-end views
def list_customers(token: str | None = None) -> list[dict]:
    from . import auth
    sess = auth.get_session(token) if token else None
    if sess:
        user, _ = sess
        if user.role == "customer":
            # Customer can only view their own profile
            return [services.get_customer(user.customer_id)]
    return services.list_customers()


def customer(cid: str, token: str | None = None) -> dict:
    from . import auth
    sess = auth.get_session(token) if token else None
    if sess:
        user, session_obj = sess
        if not session_obj.can_access(cid):
            raise HandlerError(403, "Access denied: cannot view another customer's data")
    try:
        c = services.get_customer(cid)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)
    return {
        **c,
        "accounts": services.get_accounts(cid),
        "cards": [{k: v for k, v in x.items() if k != "limit_amount"} | {"limit": x["limit_amount"]} for x in services.get_cards(cid)],
        "loans": services.loan_applications(cid)
    }


def balance(account_id: str, token: str | None = None) -> dict:
    from . import auth
    sess = auth.get_session(token) if token else None
    if sess:
        user, session_obj = sess
        owner = services.customer_of("account", account_id)
        if owner and not session_obj.can_access(owner):
            raise HandlerError(403, "Access denied: cannot view another customer's balance")
    try:
        return services.get_balance(account_id)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def transactions(account_id: str, limit: int = 10) -> list[dict]:
    try:
        return services.get_transactions(account_id, max(1, min(limit, 100)))
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def txn_risk(txn_id: str) -> dict:
    try:
        return fraud.score_transaction(txn_id, persist=False)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def bureau(cid: str) -> dict:
    try:
        return services.get_bureau(cid)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def kyc(cid: str) -> dict:
    rec = services.get_kyc(cid)
    if not rec:
        raise HandlerError(404, "no KYC record")
    return rec


def get_transaction(txn_id: str) -> dict:
    try:
        return services.get_transaction(txn_id)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def block_card(card_id: str, reason: str = "customer request") -> dict:
    try:
        return services.block_card(card_id, reason)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def create_dispute(body: dict) -> dict:
    try:
        return services.create_dispute(body.get("txn_id"), body.get("reason", "transaction not recognised"))
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def loan_eligibility(body: dict) -> dict:
    from .rules import check_eligibility
    cid = body.get("customer_id")
    amt = float(body.get("amount", 100000))
    tenure = int(body.get("tenure_months", 36))
    try:
        c = services.get_customer(cid)
        b = services.get_bureau(cid)
        return check_eligibility(c, b["score"], amt, tenure)
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def loan_applications(body: dict) -> dict:
    cid = body.get("customer_id")
    amt = float(body.get("amount", 100000))
    tenure = int(body.get("tenure_months", 36))
    purpose = body.get("purpose", "personal")
    try:
        app_id = services.create_loan_application(
            customer_id=cid,
            amount=amt,
            tenure_months=tenure,
            rate=12.0,
            emi=amt / tenure,
            status="submitted",
            decision_reason="Submitted via banking API"
        )
        return {"application_id": app_id, "customer_id": cid, "amount": amt, "tenure_months": tenure, "status": "submitted"}
    except services.ServiceError as e:
        raise HandlerError(404, e.message)


def alerts(customer_id: str | None, after_id: int = 0, limit: int = 20) -> list[dict]:
    return services.list_alerts(customer_id, after_id, limit)


def tools_catalogue() -> list[dict]:
    return [{"name": s.name, "description": s.description, "allowed_agents": sorted(s.allowed_agents),
             "requires_approval": bool(s.requires_approval), "conditional_approval": callable(s.requires_approval)}
            for s in sorted(REGISTRY.values(), key=lambda s: s.name)]


def intents_catalogue() -> dict:
    return INTENTS


def get_audit(trace_id: str | None, limit: int = 50) -> list[dict]:
    return audit.for_trace(trace_id) if trace_id else audit.recent(limit)


# ---------------------------------------------------------------- ops
def get_metrics() -> dict:
    return metrics.summary()


def reset_metrics() -> dict:
    metrics.reset()
    return {"ok": True}


def set_llm(enabled: bool) -> dict:
    """The 'LLM available' switch for the offline-resilience demo."""
    config.runtime["llm_enabled"] = bool(enabled)
    return {"llm_enabled": config.get_settings().llm_enabled}


def llm_status() -> dict:
    s = config.get_settings()
    return {"enabled": s.llm_enabled, "provider": s.llm_provider, "tier2_model": s.tier2_model,
            "tier3_model": s.tier3_model, "fallback_model": s.fallback_model, "available": supervisor().gateway.available()}


def simulate(customer_id: str | None, anomalous: bool | None) -> dict:
    try:
        return stream.process_transaction(stream.simulate_transaction(customer_id, anomalous))
    except (StopIteration, services.ServiceError):
        raise HandlerError(404, "unknown customer or no savings account")


def stream_control(action: str) -> dict:
    global _runner
    s = config.get_settings()
    if _runner is None:
        _runner = stream.StreamRunner(s.stream_interval)
    if action == "start":
        _runner.start()
    elif action == "stop":
        _runner.stop()
    return {"running": _runner.running(), "recent": _runner.events[-10:]}
