"""Watchlist router — save/track sites (§8.2).

``GET /watchlist`` lists the user's items joined with the site address and the latest
briefing's conviction/band. ``POST /watchlist`` upserts an item (status pursuing|watching|dead).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.models.entities import Briefing, Site, WatchlistItem
from app.schemas.common import err, ok
from app.schemas.domain import WatchlistIn, WatchlistOut

log = get_logger("parallax.api.watchlist")
router = APIRouter(tags=["watchlist"])


@router.get("/watchlist")
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = list(
        (
            await db.execute(
                select(WatchlistItem)
                .where(WatchlistItem.user_id == current_user.id)
                .order_by(WatchlistItem.updated_at.desc())
            )
        ).scalars().all()
    )

    out: list[dict] = []
    for item in items:
        site = await db.get(Site, item.site_uprn)
        briefing = (
            await db.execute(
                select(Briefing)
                .where(Briefing.site_uprn == item.site_uprn, Briefing.is_stale.is_(False))
                .order_by(Briefing.updated_at.desc())
            )
        ).scalars().first()
        out.append(
            WatchlistOut(
                id=item.id,
                site_uprn=item.site_uprn,
                status=item.status,
                note=item.note,
                address=site.address if site else None,
                conviction=briefing.conviction if briefing else None,
                band=briefing.band if briefing else None,
            ).model_dump()
        )
    return ok(out)


@router.post("/watchlist")
async def upsert_watchlist(
    body: WatchlistIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    site = await db.get(Site, body.site_uprn)
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    item = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == current_user.id,
                WatchlistItem.site_uprn == body.site_uprn,
            )
        )
    ).scalar_one_or_none()

    if item is None:
        item = WatchlistItem(
            user_id=current_user.id,
            site_uprn=body.site_uprn,
            status=body.status,
            note=body.note,
        )
        db.add(item)
    else:
        item.status = body.status
        if body.note is not None:
            item.note = body.note

    await db.commit()
    await db.refresh(item)
    log.info("watchlist_upserted", user_id=current_user.id, uprn=body.site_uprn, status=item.status)
    return ok(
        WatchlistOut(
            id=item.id,
            site_uprn=item.site_uprn,
            status=item.status,
            note=item.note,
            address=site.address,
        ).model_dump()
    )
