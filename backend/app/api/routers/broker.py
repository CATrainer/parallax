"""Broker router — Product 2, the broker lens (§8.3, §11).

Same engine, an owner-situation lens: "does this owner's situation imply an imminent mortgage
event". ``/broker/enrich`` takes a pasted list of addresses, resolves each via the engine's
resolution spine, scores its signals, and produces a transaction-likelihood row (blending the
deterministic score with a best-effort ``broker_situation`` inference pass).
``/broker/site/{uprn}/intelligence`` reframes one site's signals as owner-situation intelligence.

Access is gated to brokers OR the ``pro`` rung, but lenient by design so the demo works (§11).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.engine.inference import get_provider
from app.engine.resolution import resolve_site
from app.engine.scoring import score_signals
from app.models.entities import OwnershipLink, Signal, Site
from app.models.enums import band_for
from app.schemas.common import err, ok
from app.schemas.domain import (
    BrokerEnrichOut,
    BrokerEnrichRow,
    BrokerIntelligenceOut,
    OwnershipLinkOut,
    SiteOut,
)

log = get_logger("parallax.api.broker")
router = APIRouter(prefix="/broker", tags=["broker"])

_MAX_LIST = 50
# Owner-situation lenses: the signal types that imply a near-term transaction / financing event.
_SITUATION_LABELS = {
    "probate_inherited": "inherited property — heirs typically liquidate",
    "owner_spv_distress": "financial distress on the owning entity",
    "long_distance_owner": "absentee owner — life-event move likely",
    "portfolio_regulatory_pressure": "regulatory pressure on a landlord portfolio",
    "long_hold_unimproved": "very long hold — equity release / downsizing candidate",
    "epc_lapsed": "lapsed EPC — property may be vacant pending sale",
    "single_property_owner": "single-property owner — one-off disposal likely",
}


def _broker_allowed(user) -> bool:
    """Lenient gate (§11): brokers and pro-rung users in; demo stays usable."""
    return bool(user.is_broker) or user.rung in {"pro", "broker"}


class EnrichBody(BaseModel):
    model_config = {"populate_by_name": True}
    addresses: list[str] | str = Field(default="", alias="list")


def _split_addresses(raw: str) -> list[str]:
    # One address per line (or semicolon-separated). NEVER split on commas — UK addresses
    # contain them ("14 Mill Lane, Bristol, BS3 4QN"), so comma-splitting shatters one address.
    parts = re.split(r"[\n;]+", raw or "")
    return [p.strip() for p in parts if p and p.strip()]


async def _signals_for(db: AsyncSession, uprn: str) -> list[Signal]:
    return list(
        (
            await db.execute(
                select(Signal).where(Signal.site_uprn == uprn, Signal.fired.is_(True))
            )
        ).scalars().all()
    )


def _drivers(signals: list[Signal]) -> list[str]:
    seen: list[str] = []
    for s in signals:
        label = _SITUATION_LABELS.get(s.signal_type)
        if label and label not in seen:
            seen.append(label)
    return seen


@router.post("/enrich")
async def enrich_post(
    body: EnrichBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    raw = body.addresses if isinstance(body.addresses, str) else "\n".join(body.addresses)
    return await _enrich(raw, db, current_user)


@router.get("/enrich")
async def enrich(
    list: str = Query(default="", description="comma- or newline-separated addresses"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _enrich(list, db, current_user)


async def _enrich(list: str, db: AsyncSession, current_user):
    if not _broker_allowed(current_user):
        return err("FORBIDDEN", "The broker console is available on broker and pro plans.")

    addresses = _split_addresses(list)[:_MAX_LIST]
    if not addresses:
        return ok(BrokerEnrichOut(rows=[], total=0).model_dump())

    provider = get_provider("cheap")
    rows: list[BrokerEnrichRow] = []

    for addr in addresses:
        try:
            site = await resolve_site(db, addr)
        except Exception:  # noqa: BLE001 — one bad row never sinks the batch
            log.warning("broker_resolve_failed")
            rows.append(
                BrokerEnrichRow(
                    input_address=addr,
                    transaction_likelihood=0,
                    band=band_for(0).value,
                    rationale="Could not resolve this address to a site.",
                    signal_summary=[],
                )
            )
            continue

        signals = await _signals_for(db, site.uprn)
        score = score_signals(signals)
        likelihood = score.conviction
        rationale = "No owner-situation signals on record for this address yet."

        # Best-effort inference blend; falls back silently to the deterministic score.
        try:
            payload = {
                "site": {"uprn": site.uprn, "address": site.address},
                "signals": [
                    {
                        "id": s.id,
                        "signal_type": s.signal_type,
                        "fired": True,
                        "strength": float(s.strength or 0.0),
                        "source": s.source,
                    }
                    for s in signals
                ],
                "conviction": score.conviction,
            }
            inf = await provider.complete("broker_situation", payload)
            inf_lik = int(inf.get("transaction_likelihood", likelihood) or likelihood)
            # Blend: average the inference and the deterministic score for stability.
            likelihood = max(0, min(100, round((inf_lik + score.conviction) / 2)))
            rationale = inf.get("rationale") or inf.get("owner_situation") or rationale
        except Exception:  # noqa: BLE001
            log.info("broker_inference_skipped", uprn=site.uprn)

        await db.commit()  # persist the resolved site/geocode cache
        rows.append(
            BrokerEnrichRow(
                input_address=addr,
                uprn=site.uprn,
                resolved_address=site.address,
                transaction_likelihood=likelihood,
                band=band_for(likelihood).value,
                rationale=rationale,
                signal_summary=_drivers(signals),
            )
        )

    log.info("broker_enriched", user_id=current_user.id, count=len(rows))
    return ok(BrokerEnrichOut(rows=rows, total=len(rows)).model_dump())


@router.get("/site/{uprn}/intelligence")
async def site_intelligence(
    uprn: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not _broker_allowed(current_user):
        return err("FORBIDDEN", "The broker console is available on broker and pro plans.")

    site = (
        await db.execute(
            select(Site)
            .where(Site.uprn == uprn)
            .options(selectinload(Site.ownership_links).selectinload(OwnershipLink.owner))
        )
    ).scalar_one_or_none()
    if site is None:
        return err("SITE_NOT_FOUND", "No site matches that reference.")

    signals = await _signals_for(db, uprn)
    score = score_signals(signals)
    likelihood = score.conviction
    situation = "No owner-situation signals currently indicate an imminent mortgage event."

    try:
        payload = {
            "site": {"uprn": site.uprn, "address": site.address},
            "signals": [
                {
                    "id": s.id,
                    "signal_type": s.signal_type,
                    "fired": True,
                    "strength": float(s.strength or 0.0),
                    "source": s.source,
                }
                for s in signals
            ],
            "conviction": score.conviction,
        }
        inf = await get_provider("cheap").complete("broker_situation", payload)
        situation = inf.get("owner_situation") or situation
        likelihood = max(
            0, min(100, int(inf.get("mortgage_event_likelihood", likelihood) or likelihood))
        )
    except Exception:  # noqa: BLE001
        log.info("broker_intel_inference_skipped", uprn=uprn)

    out = BrokerIntelligenceOut(
        site=SiteOut.model_validate(site),
        owner_situation=situation,
        mortgage_event_likelihood=likelihood,
        band=band_for(likelihood).value,
        drivers=_drivers(signals),
        ownership=[OwnershipLinkOut.model_validate(link) for link in site.ownership_links],
    )
    return ok(out.model_dump(mode="json"))
