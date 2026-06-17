"""Shared FastAPI dependencies — auth + credit gating.

``get_current_user`` turns a ``Authorization: Bearer <jwt>`` header into a ``User`` row, or
raises a 401 whose ``detail`` is the standard error envelope (§8.1) so the client always sees
the same shape. ``get_optional_user`` is the lenient variant (returns ``None`` when absent).
PII never appears in error messages (§12).
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import decode_token
from app.core.db import get_db
from app.models.entities import User
from app.schemas.common import err

# Re-export so routers can `from app.api.deps import get_db`.
__all__ = ["get_db", "get_current_user", "get_optional_user", "require_credits"]


def _auth_error(code: str, message: str, status_code: int = 401) -> HTTPException:
    """An HTTPException whose detail is the envelope body — formatted uniformly by main.py."""
    return HTTPException(status_code=status_code, detail=err(code, message))


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def _user_from_token(token: str | None, db: AsyncSession) -> User | None:
    if not token:
        return None
    claims = decode_token(token)
    if not claims:
        return None
    user_id = claims.get("sub")
    if not user_id:
        return None
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the bearer token to a ``User`` or raise an envelope-shaped 401."""
    token = _bearer_token(authorization)
    if token is None:
        raise _auth_error("UNAUTHORIZED", "Sign in to continue.")
    user = await _user_from_token(token, db)
    if user is None:
        raise _auth_error("UNAUTHORIZED", "Your session has expired. Sign in again.")
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Lenient variant — returns ``None`` when no/invalid token, never raises."""
    return await _user_from_token(_bearer_token(authorization), db)


def require_credits(user: User, n: int) -> None:
    """Guard a metered action. Raises an envelope-shaped 402 when the balance is short."""
    if (user.credits_remaining or 0) < n:
        raise _auth_error(
            "INSUFFICIENT_CREDITS",
            f"This action needs {n} credit{'s' if n != 1 else ''}; top up to continue.",
            status_code=402,
        )
