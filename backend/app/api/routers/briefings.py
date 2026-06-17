"""Briefings router — the hero endpoint (§8.2).

``GET /sites/{uprn}/briefing`` returns the full briefing, triggering premium synthesis when
the persisted one is stale (via the engine's ``get_or_build_briefing``). It is metered as a
deep-dive: ``deep_dives_used`` is incremented. Entry rung is allowed — we just count it (§10).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.routers.sites import load_site_full
from app.core.logging import get_logger
from app.engine.synthesis import briefing_to_out, get_or_build_briefing
from app.models.entities import Site
from app.schemas.common import err, ok
from app.schemas.domain import BriefingOut

log = get_logger("parallax.api.briefings")
router = APIRouter(tags=["briefings"])


@router.get("/sites/{uprn}/briefing")
async def get_briefing(
    uprn: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    site = await db.get(Site, uprn)
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    try:
        briefing = await get_or_build_briefing(db, uprn, premium=True)
    except ValueError:
        return err("SITE_NOT_FOUND", "No site matches that reference.")
    except Exception:  # noqa: BLE001 — synthesis is best-effort; never leak internals
        log.warning("briefing_build_failed", uprn=uprn)
        return err("BRIEFING_UNAVAILABLE", "This briefing could not be assembled right now. Try again shortly.")

    # Meter the deep-dive (§10) — counted at every rung, including Entry.
    current_user.deep_dives_used = (current_user.deep_dives_used or 0) + 1
    await db.commit()
    log.info("deep_dive_metered", user_id=current_user.id, uprn=uprn)

    # Re-load the site with signals + ownership for the full briefing payload.
    full = await load_site_full(db, uprn)
    signals = list(full.signals) if full else []
    ownership = list(full.ownership_links) if full else []

    out = briefing_to_out(briefing, full or site, signals, ownership)
    return ok(BriefingOut.model_validate(out).model_dump(mode="json"))
