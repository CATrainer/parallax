"""Auth router — register / login / me (§8.2, BUILD_SPEC).

New users land on the Entry rung with a small credit allowance so the metered surfaces work
out of the box. Every response is the standard envelope; error copy follows §9 voice and never
leaks PII.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token, hash_password, verify_password
from app.api.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.models.entities import User
from app.schemas.common import err, ok
from app.schemas.domain import LoginIn, RegisterIn, TokenOut

log = get_logger("parallax.api.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

# New Entry-rung accounts start with a handful of credits so deep-dives/validation work day one.
_STARTING_CREDITS = 10


def _token_payload(user: User) -> dict:
    return TokenOut(
        access_token=create_access_token(user.id),
        rung=user.rung,
        is_broker=bool(user.is_broker),
    ).model_dump()


@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        return err("INVALID_INPUT", "Enter an email and a password to create an account.")

    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        return err("EMAIL_TAKEN", "An account already exists for that email. Sign in instead.")

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
        rung="entry",
        credits_remaining=_STARTING_CREDITS,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("user_registered", user_id=user.id, rung=user.rung)
    return ok(_token_payload(user))


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    email = (body.email or "").strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        # Same message either way — never reveal whether the email exists.
        return err("INVALID_CREDENTIALS", "Email or password is incorrect.")
    log.info("user_logged_in", user_id=user.id)
    return ok(_token_payload(user))


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return ok(
        {
            "id": current_user.id,
            "email": current_user.email,
            "display_name": current_user.display_name,
            "rung": current_user.rung,
            "credits_remaining": current_user.credits_remaining,
            "deep_dives_used": current_user.deep_dives_used,
            "is_broker": bool(current_user.is_broker),
        }
    )
