"""Usage router — credits / deep-dives / rung (§8.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.common import ok
from app.schemas.domain import UsageOut

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def get_usage(current_user=Depends(get_current_user)):
    return ok(
        UsageOut(
            rung=current_user.rung,
            credits_remaining=current_user.credits_remaining,
            deep_dives_used=current_user.deep_dives_used,
        ).model_dump()
    )
