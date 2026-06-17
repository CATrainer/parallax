"""Sites router — site detail + status (§8.2).

``GET /sites/{uprn}`` returns facts + resolved (probabilistic) ownership + signals + the
headline conviction/band from the latest briefing — NO premium synthesis (that lives behind
``/briefing``). ``POST /sites/{uprn}/status`` upserts the user's pursuing|dead marker, which
"trains relevance" — for now that is simply persisting the choice and logging it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_optional_user
from app.core.logging import get_logger
from app.models.entities import Briefing, OwnershipLink, Site, WatchlistItem
from app.schemas.common import err, ok
from app.schemas.domain import (
    OwnershipLinkOut,
    SignalOut,
    SiteDetail,
    StatusIn,
)

log = get_logger("parallax.api.sites")
router = APIRouter(tags=["sites"])


async def load_site_full(db: AsyncSession, uprn: str) -> Site | None:
    """Load a Site with signals + ownership links (+ owners) eagerly. Shared with briefings."""
    return (
        await db.execute(
            select(Site)
            .where(Site.uprn == uprn)
            .options(
                selectinload(Site.signals),
                selectinload(Site.ownership_links).selectinload(OwnershipLink.owner),
            )
        )
    ).scalar_one_or_none()


async def latest_briefing(db: AsyncSession, uprn: str) -> Briefing | None:
    return (
        await db.execute(
            select(Briefing)
            .where(Briefing.site_uprn == uprn, Briefing.is_stale.is_(False))
            .order_by(Briefing.updated_at.desc())
        )
    ).scalars().first()


@router.get("/sites/{uprn}")
async def get_site(
    uprn: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_optional_user),
):
    site = await load_site_full(db, uprn)
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    briefing = await latest_briefing(db, uprn)
    detail = SiteDetail(
        uprn=site.uprn,
        address=site.address,
        postcode=site.postcode,
        lat=site.lat,
        lng=site.lng,
        property_type=site.property_type,
        tenure=site.tenure,
        local_authority=site.local_authority,
        resolution_confidence=site.resolution_confidence,
        ownership=[OwnershipLinkOut.model_validate(link) for link in site.ownership_links],
        signals=[SignalOut.model_validate(s) for s in site.signals],
        headline_conviction=briefing.conviction if briefing else None,
        headline_band=briefing.band if briefing else None,
    )
    return ok(detail.model_dump(mode="json"))


@router.post("/sites/{uprn}/status")
async def set_status(
    uprn: str,
    body: StatusIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    site = await db.get(Site, uprn)
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    item = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == current_user.id,
                WatchlistItem.site_uprn == uprn,
            )
        )
    ).scalar_one_or_none()

    if item is None:
        item = WatchlistItem(user_id=current_user.id, site_uprn=uprn, status=body.status)
        db.add(item)
    else:
        item.status = body.status

    await db.commit()
    # "Trains relevance" = persist the triage decision + log it for later relevance tuning.
    log.info("site_status_set", user_id=current_user.id, uprn=uprn, status=body.status)
    return ok({"site_uprn": uprn, "status": body.status})
