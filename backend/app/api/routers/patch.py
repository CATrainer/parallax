"""Patch router — define a patch + the push feed (§8.2).

A user has one patch (the buy-box + postcodes + conviction floor). ``GET /patch/briefings`` is
the push surface: briefings for sites whose postcode falls in the patch AND whose conviction
clears the floor, filtered by band / opportunity type / since, newest first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.models.entities import Briefing, Patch, Signal, Site
from app.schemas.common import ok
from app.schemas.domain import BriefingCard, BuyBox, PatchIn, PatchOut

log = get_logger("parallax.api.patch")
router = APIRouter(tags=["patch"])

_FEED_LIMIT = 100


def _patch_out(patch: Patch) -> dict:
    bb = patch.buy_box or {}
    return PatchOut(
        id=patch.id,
        name=patch.name,
        postcodes=list(patch.postcodes or []),
        buy_box=BuyBox(
            min_price=bb.get("min_price"),
            max_price=bb.get("max_price"),
            property_types=bb.get("property_types") or bb.get("types") or [],
        ),
        opportunity_types=list(patch.opportunity_types or []),
        conviction_floor=patch.conviction_floor,
    ).model_dump()


async def _user_patch(db: AsyncSession, user_id: str) -> Patch | None:
    return (
        await db.execute(
            select(Patch).where(Patch.user_id == user_id).order_by(Patch.created_at.asc())
        )
    ).scalars().first()


@router.get("/patch")
async def get_patch(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    patch = await _user_patch(db, current_user.id)
    return ok(_patch_out(patch) if patch else None)


@router.post("/patch")
async def upsert_patch(
    body: PatchIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    patch = await _user_patch(db, current_user.id)
    buy_box = body.buy_box.model_dump() if body.buy_box else {}
    if patch is None:
        patch = Patch(user_id=current_user.id)
        db.add(patch)
    patch.name = body.name
    patch.postcodes = list(body.postcodes or [])
    patch.buy_box = buy_box
    patch.opportunity_types = list(body.opportunity_types or [])
    patch.conviction_floor = body.conviction_floor
    await db.commit()
    await db.refresh(patch)
    log.info("patch_upserted", user_id=current_user.id, postcodes=len(patch.postcodes))
    return ok(_patch_out(patch))


@router.get("/patch/briefings")
async def patch_feed(
    since: Optional[datetime] = Query(default=None),
    band: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None, description="opportunity type filter"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    patch = await _user_patch(db, current_user.id)
    if patch is None or not (patch.postcodes or []):
        return ok([])

    postcodes = list(patch.postcodes or [])
    floor = patch.conviction_floor or 0

    # Match by postcode prefix (patch carries outward codes like "BS1"); Site.postcode is full.
    # ILIKE 'BS1%' catches "BS1 4ND" etc.
    from sqlalchemy import or_

    pc_clauses = [Site.postcode.ilike(f"{pc}%") for pc in postcodes if pc]

    stmt = (
        select(Briefing, Site)
        .join(Site, Site.uprn == Briefing.site_uprn)
        .where(
            Briefing.is_stale.is_(False),
            Briefing.conviction >= floor,
            or_(*pc_clauses) if pc_clauses else False,
        )
        .order_by(Briefing.updated_at.desc())
        .limit(_FEED_LIMIT)
    )
    if band:
        stmt = stmt.where(Briefing.band == band.upper())
    if since:
        stmt = stmt.where(Briefing.updated_at >= since)

    rows = (await db.execute(stmt)).all()

    cards: list[dict] = []
    for briefing, site in rows:
        opp_types = briefing.opportunity_types or []
        if type and type not in opp_types and briefing.headline_opportunity != type:
            continue
        signal_count = (
            await db.execute(
                select(func.count(Signal.id)).where(
                    Signal.site_uprn == site.uprn, Signal.fired.is_(True)
                )
            )
        ).scalar_one()
        cards.append(
            BriefingCard(
                id=briefing.id,
                site_uprn=briefing.site_uprn,
                address=site.address,
                postcode=site.postcode,
                lede=briefing.lede,
                conviction=briefing.conviction,
                band=briefing.band,
                headline_opportunity=briefing.headline_opportunity,
                opportunity_types=opp_types,
                signal_count=signal_count,
                updated_at=briefing.updated_at,
            ).model_dump(mode="json")
        )

    return ok(cards)
