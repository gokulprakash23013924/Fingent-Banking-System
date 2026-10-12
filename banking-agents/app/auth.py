"""Authentication and Session Management for Fingent Banking Platform.

Provides session-based authentication, role enforcement (customer vs supervisor),
and customer data isolation.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from . import db
from .state import Session

_SALT = "fingent_banking_salt_2026"
_SESSIONS_LOCK = threading.Lock()
_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL_SECONDS = 86400  # 24 hours


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"{password}:{_SALT}".encode()).hexdigest()


@dataclass
class AuthUser:
    username: str
    role: str  # "customer" | "supervisor" | "rm"
    customer_id: str | None
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "role": self.role,
            "customer_id": self.customer_id,
            "name": self.name,
        }


def init_auth_db() -> None:
    """Create the users table if it does not exist."""
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        customer_id TEXT,
        name TEXT NOT NULL
    );
    """)
    seed_users()


DEMO_USERS = [
    # Customers
    ("C001", "password123", "customer", "C001", "Aarav Mehta"),
    ("C002", "password123", "customer", "C002", "Diya Nair"),
    ("C003", "password123", "customer", "C003", "Rohan Das"),
    ("C004", "password123", "customer", "C004", "Meera Iyer"),
    ("C005", "password123", "customer", "C005", "Karthik Raman"),
    ("C006", "password123", "customer", "C006", "Sana Khan"),
    ("C007", "password123", "customer", "C007", "Vikram Singh"),
    ("C008", "password123", "customer", "C008", "Ananya Rao"),
    ("C009", "password123", "customer", "C009", "Imran Sheikh"),
    ("C010", "password123", "customer", "C010", "Lakshmi Pillai"),
    # Supervisors
    ("supervisor", "admin123", "supervisor", None, "Chief Banking Supervisor"),
    ("rm001", "admin123", "rm", None, "Senior Relationship Manager"),
]


def seed_users() -> None:
    """Seed initial demo users into the users table."""
    for username, pwd, role, cid, name in DEMO_USERS:
        p_hash = _hash_password(pwd)
        db.execute("""
        INSERT OR REPLACE INTO users (username, password_hash, role, customer_id, name)
        VALUES (?, ?, ?, ?, ?)
        """, (username, p_hash, role, cid, name))


def authenticate_user(username: str, password: str) -> AuthUser | None:
    """Verify credentials and return user object if valid."""
    p_hash = _hash_password(password)
    row = db.query_one("SELECT username, role, customer_id, name FROM users WHERE username = ? AND password_hash = ?",
                       (username.strip(), p_hash))
    if not row:
        return None
    return AuthUser(
        username=row["username"],
        role=row["role"],
        customer_id=row["customer_id"],
        name=row["name"]
    )


def create_session(user: AuthUser) -> str:
    """Generate a secure session token and associate it with user context."""
    token = f"nxt_{secrets.token_hex(24)}"
    now = time.time()
    with _SESSIONS_LOCK:
        _ACTIVE_SESSIONS[token] = {
            "user": user,
            "created_at": now,
            "expires_at": now + _SESSION_TTL_SECONDS
        }
    return token


def get_session(token: str | None) -> tuple[AuthUser, Session] | None:
    """Validate token and return (AuthUser, Session)."""
    if not token:
        return None
    with _SESSIONS_LOCK:
        sess = _ACTIVE_SESSIONS.get(token)
        if not sess:
            return None
        if time.time() > sess["expires_at"]:
            del _ACTIVE_SESSIONS[token]
            return None
        user: AuthUser = sess["user"]
        # Map supervisor/rm role to 'rm' in Session object for full scope
        effective_role = "rm" if user.role in ("supervisor", "rm") else "customer"
        session_obj = Session(customer_id=user.customer_id or "", role=effective_role)
        return user, session_obj


def invalidate_session(token: str | None) -> bool:
    """Remove session token on logout."""
    if not token:
        return False
    with _SESSIONS_LOCK:
        if token in _ACTIVE_SESSIONS:
            del _ACTIVE_SESSIONS[token]
            return True
    return False


def get_all_demo_users() -> list[dict[str, Any]]:
    """Return available demo users for fast switching in UI."""
    return [
        {
            "username": u[0],
            "role": u[2],
            "customer_id": u[3],
            "name": u[4],
            "description": f"{u[2].upper()} - {u[4]} ({u[0]})"
        }
        for u in DEMO_USERS
    ]
