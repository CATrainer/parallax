"""Search router — free-text → candidate sites/companies/people (§8.2, pull entry).

SITE-FIRST (§1): a search never *requires* a company. We resolve the query against Sites
(postcode / address, with pg_trgm similarity) first, then Owners (name / company number) as
secondary entities that still hang off sites. Conviction/band are attached from each site's
latest briefing where one exists.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_optional_user
from app.core.logging import get_logger
from app.models.entities import Briefing, Owner, OwnershipLink, Site
from app.schemas.common import ok
from app.schemas.domain import SearchResult

log = get_logger("parallax.api.search")
router = APIRouter(tags=["search"])

_LIMIT = 25
# pg_trgm similarity floor for fuzzy address matches.
_SIM_FLOOR = 0.15


async def _briefing_index(db: AsyncSession, uprns: list[str]) -> dict[str, tuple[int, str]]:
    """Map uprn → (conviction, band) from the freshest non-stale briefing for each site."""
    if not uprns:
        return {}
    rows = (
        await db.execute(
            select(Briefing.site_uprn, Briefing.conviction, Briefing.band)
            .where(Briefing.site_uprn.in_(uprns), Briefing.is_stale.is_(False))
            .order_by(Briefing.site_uprn, Briefing.updated_at.desc())
        )
    ).all()
    index: dict[str, tuple[int, str]] = {}
    for uprn, conviction, band in rows:
        index.setdefault(uprn, (conviction, band))  # first per uprn = freshest
    return index


async def _search_sites(db: AsyncSession, q: str) -> list[Site]:
    like = f"%{q}%"
    # pg_trgm similarity ranks fuzzy address hits; ilike catches postcode/substring matches.
    sim = func.similarity(Site.address, q)
    stmt = (
        select(Site)
        .where(
            or_(
                Site.address.ilike(like),
                Site.postcode.ilike(like),
                sim > _SIM_FLOOR,
            )
        )
        .order_by(sim.desc())
        .limit(_LIMIT)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _search_owners(db: AsyncSession, q: str) -> list[tuple[Owner, Optional[str]]]:
    """Owners matching by name or company number, paired with a current site uprn if linked."""
    like = f"%{q}%"
    stmt = (
        select(Owner)
        .where(or_(Owner.display_name.ilike(like), Owner.company_number.ilike(like)))
        .limit(_LIMIT)
    )
    owners = list((await db.execute(stmt)).scalars().all())
    out: list[tuple[Owner, Optional[str]]] = []
    for owner in owners:
        link = (
            await db.execute(
                select(OwnershipLink.site_uprn)
                .where(OwnershipLink.owner_id == owner.id, OwnershipLink.is_current.is_(True))
                .order_by(OwnershipLink.link_confidence.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append((owner, link))
    return out


@router.get("/search")
async def search(
    q: str = Query(default="", min_length=0),
    type: Optional[str] = Query(default=None, description="optional kind filter: site|company|person"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_optional_user),
):
    query = (q or "").strip()
    if not query:
        return ok([])

    results: list[SearchResult] = []

    # --- Sites first (the canonical unit) ---
    sites = await _search_sites(db, query)
    index = await _briefing_index(db, [s.uprn for s in sites])
    if type in (None, "site"):
        for s in sites:
            conviction, band = index.get(s.uprn, (None, None))
            results.append(
                SearchResult(
                    kind="site",
                    uprn=s.uprn,
                    label=s.address,
                    sublabel=s.postcode,
                    conviction=conviction,
                    band=band,
                )
            )

    # --- Owners (companies/people) — secondary, still anchored to a site where possible ---
    if type in (None, "company", "person"):
        for owner, site_uprn in await _search_owners(db, query):
            kind = "company" if owner.owner_type == "company" else "person"
            if type in ("company", "person") and kind != type:
                continue
            conviction, band = (None, None)
            if site_uprn:
                # Pull the linked site's briefing band if we have it (resolve backwards).
                conviction, band = (await _briefing_index(db, [site_uprn])).get(
                    site_uprn, (None, None)
                )
            results.append(
                SearchResult(
                    kind=kind,
                    uprn=site_uprn,
                    label=owner.display_name,
                    sublabel=owner.company_number or ("individual" if kind == "person" else None),
                    conviction=conviction,
                    band=band,
                )
            )

    return ok([r.model_dump() for r in results])
