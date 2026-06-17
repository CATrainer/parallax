"""Auth primitives — bcrypt password hashing + HS256 JWTs (§8 / BUILD_SPEC).

Secrets only via ``settings`` (§3.3): JWT signing uses ``settings.jwt_secret`` and tokens
live for ``settings.access_token_ttl_min`` minutes. No PII in tokens — the subject is the
opaque user id, never the email/name.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("parallax.auth")

# bcrypt via passlib — same scheme the seed uses, so seeded hashes verify cleanly.
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

_ALGORITHM = "HS256"


# ─────────────────────────────────────────── passwords ───────────────────────────────────────────
def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password``. The plaintext is never logged."""
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time-ish verify; never raises on malformed hashes."""
    try:
        return _pwd.verify(password, hashed)
    except Exception:  # noqa: BLE001 — a bad stored hash must not 500 the login path
        log.warning("password_verify_error")
        return False


# ─────────────────────────────────────────── tokens ──────────────────────────────────────────────
def create_access_token(user_id: str, *, ttl_minutes: int | None = None) -> str:
    """Mint a signed HS256 JWT whose subject is the user id (no PII)."""
    ttl = settings.access_token_ttl_min if ttl_minutes is None else ttl_minutes
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode + verify a JWT. Returns the claims dict, or ``None`` if invalid/expired."""
    if not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except JWTError:
        return None
