"""
Password hashing (bcrypt, called directly) and signed session cookies
(itsdangerous). No secret is ever hard-coded — SECRET_KEY comes from
the environment via app.config.settings.
"""
from __future__ import annotations

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="roomiq-session")

SESSION_COOKIE = "roomiq_session"


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except Exception:
        return False


def create_session_token(user_id: str) -> str:
    return _serializer.dumps({"user_id": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=settings.SESSION_MINUTES * 60)
        if isinstance(data, dict):
            uid = data.get("user_id")
            return str(uid) if uid is not None else None
        if isinstance(data, str):
            return data
        return None
    except Exception:
        return None
