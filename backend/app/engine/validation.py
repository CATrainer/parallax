"""L5 — the validation tier (§6.4).

Validation is the metered value moment: the engine spends its budget in escalating cost
order and returns **materially more** than the free briefing — title-confirmed ownership,
occupancy, a resolved contact route, and a per-check provenance log. That delta is what the
credit buys (§13.4).

This module computes ``credits_spent``; the actual debit against the user's balance is done
by the worker/endpoint. Each check is wrapped in try/except — a hard failure sets
``status="failed"`` with a non-PII error and never crashes the worker.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.entities import Site, Validation
from app.models.enums import ValidationStatus

log = get_logger("engine.validation")

# Provenance entries follow schemas.domain.ProvenanceEntry: {check, source, cost_credits, result}.


def _provenance(check: str, source: str, cost_credits: int, result: str) -> dict:
    return {"check": check, "source": source, "cost_credits": cost_credits, "result": result}


async def _check_companies_house(db, site: Site, provenance: list[dict]) -> int:
    """Cheap automated: deeper CH pull on the owning entity + a focused note. 0–1 credits."""
    cost = 0
    try:
        from app.adapters import companies_house  # lazy — avoid import cycle

        adapter = companies_house.CompaniesHouseAdapter()
        note = "No owning company on record for this site."
        # Look up the current company owner, if any, via the ownership spine.
        from sqlalchemy import select

        from app.models.entities import Owner, OwnershipLink

        stmt = (
            select(Owner)
            .join(OwnershipLink, OwnershipLink.owner_id == Owner.id)
            .where(
                OwnershipLink.site_uprn == site.uprn,
                OwnershipLink.is_current.is_(True),
                Owner.company_number.is_not(None),
            )
            .order_by(OwnershipLink.link_confidence.desc())
            .limit(1)
        )
        owner = (await db.execute(stmt)).scalars().first()
        if owner is not None and owner.company_number:
            profile = await adapter.fetch(company_number=owner.company_number)
            cost = 1
            status = None
            if profile:
                first = profile[0] if isinstance(profile, list) else profile
                status = (first or {}).get("company_status")
            note = (
                f"Companies House profile pulled; status={status or 'unknown'}."
                if status
                else "Companies House profile pulled."
            )
        provenance.append(_provenance("companies_house_pull", "companies_house", cost, note))
    except Exception:  # noqa: BLE001 — soft check; record and continue
        log.warning("validation_ch_check_failed", uprn=site.uprn)
        provenance.append(
            _provenance("companies_house_pull", "companies_house", cost, "Pull unavailable.")
        )
    return cost


async def _check_title_pull(db, site: Site, validation: Validation, provenance: list[dict]) -> int:
    """Confirm the current proprietor. The free briefing's ownership is a *probabilistic* link;
    this resolves the proprietor from the ownership register (always available), then upgrades to a
    title-confirmed reading via an HMLR title pull when available (SEED fixture, or LIVE + HMLR key).
    Returns the credit cost incurred."""
    from sqlalchemy import select

    from app.models.entities import Owner, OwnershipLink

    # 1) Proprietor from the resolved ownership spine — always available, no external cost.
    confirmed: dict | None = None
    try:
        stmt = (
            select(Owner, OwnershipLink)
            .join(OwnershipLink, OwnershipLink.owner_id == Owner.id)
            .where(OwnershipLink.site_uprn == site.uprn, OwnershipLink.role == "proprietor")
            .order_by(OwnershipLink.link_confidence.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is not None:
            owner, _link = row
            confirmed = {
                "proprietor": owner.display_name,
                "proprietor_type": "company" if owner.company_number else "private_individual",
                "tenure": site.tenure,
                "correspondence_address": owner.last_known_address or site.address,
                "basis": "registry-resolved",
            }
            if owner.company_number:
                confirmed["company_number"] = owner.company_number
    except Exception:  # noqa: BLE001
        log.warning("validation_owner_resolve_failed", uprn=site.uprn)

    # 2) Best-effort HMLR title pull to upgrade to a title-confirmed reading.
    cost = 0
    title: dict | None = None
    try:
        from app.adapters.hmlr import HmlrTitleAdapter  # lazy — avoid import cycle

        result = await HmlrTitleAdapter().title_pull(site.uprn)
        title = result if isinstance(result, dict) else None
        cost = 3
    except Exception:  # noqa: BLE001 — no HMLR key / unavailable; registry-resolved stands
        log.info("hmlr_title_unavailable", uprn=site.uprn)

    if title:
        if confirmed is None:
            props = title.get("proprietors") or [{}]
            confirmed = {
                "proprietor": props[0].get("name"),
                "proprietor_type": props[0].get("proprietor_type"),
                "correspondence_address": props[0].get("address"),
            }
        confirmed.update(
            {
                "title_number": title.get("title_number"),
                "tenure": title.get("tenure") or confirmed.get("tenure") or site.tenure,
                "registered_date": title.get("registered_date"),
                "basis": "title-confirmed",
            }
        )
        note = "Title register pulled; proprietor title-confirmed."
    elif confirmed is not None:
        note = "Proprietor confirmed from the ownership register (HMLR title pull not configured)."
    else:
        note = "No proprietor on record for this site."

    if confirmed is not None:
        validation.confirmed_ownership = confirmed
    provenance.append(
        _provenance(
            "hmlr_title_pull" if cost else "ownership_confirm",
            "hmlr_title" if cost else "ownership_register",
            cost,
            note,
        )
    )
    return cost


async def _check_occupancy(db, site: Site, validation: Validation, provenance: list[dict]) -> int:
    """Address-level occupancy inference (§6.4 — templated council/FOI route in production).

    In SEED we infer from the site's own empty/vacant signals; this is the occupancy delta the
    free briefing does not assert as a resolved status. No external cost in SEED.
    """
    try:
        from sqlalchemy import select

        from app.models.entities import Signal

        rows = list(
            (
                await db.execute(
                    select(Signal).where(Signal.site_uprn == site.uprn, Signal.fired.is_(True))
                )
            ).scalars().all()
        )
        types = {s.signal_type for s in rows}
        empty_markers = {"epc_lapsed", "no_listing", "probate_inherited", "long_distance_owner"}
        n = len(types & empty_markers)
        if n >= 2:
            status = "Likely empty — no occupancy on record; lapsed EPC and/or no current listing."
        elif n == 1:
            status = "Possibly empty — one occupancy-relevant signal present; confirm locally."
        else:
            status = "Likely occupied — no vacancy signals on record."
        validation.occupancy_status = status
        provenance.append(_provenance("occupancy_check", "council_foi_template", 0, status))
    except Exception:  # noqa: BLE001
        log.warning("validation_occupancy_failed", uprn=site.uprn)
        provenance.append(
            _provenance("occupancy_check", "council_foi_template", 0, "Occupancy check unavailable.")
        )
    return 0


def _resolve_contact_route(site: Site, validation: Validation, provenance: list[dict]) -> int:
    """Resolve a contact route from confirmed ownership. No external cost."""
    route: dict | None = None
    confirmed = validation.confirmed_ownership or {}
    correspondence = confirmed.get("correspondence_address") or confirmed.get("address")
    if correspondence:
        route = {"method": "correspondence_address", "detail": correspondence}
    elif site.address:
        route = {"method": "site_address", "detail": site.address}
    validation.contact_route = route
    provenance.append(
        _provenance(
            "contact_route",
            "engine",
            0,
            "Contact route resolved." if route else "No contact route available.",
        )
    )
    return 0


async def run_validation(db, validation_id: str) -> Validation:
    """Execute the validation tier in escalating cost order; persist results + provenance.

    Returns the updated ``Validation`` with confirmed ownership, occupancy, contact route,
    an updated conviction (rescore nudged up by confirmation), accumulated ``credits_spent``,
    and a full provenance log. On hard failure: ``status="failed"`` + non-PII error.
    """
    validation = await db.get(Validation, validation_id)
    if validation is None:
        raise ValueError("validation_not_found")

    site = await db.get(Site, validation.site_uprn)
    if site is None:
        validation.status = ValidationStatus.failed.value
        validation.error = "Site not found for validation."
        await db.flush()
        return validation

    validation.status = ValidationStatus.running.value
    provenance: list[dict] = list(validation.provenance_log or [])
    credits = int(validation.credits_spent or 0)

    try:
        # (1) cheap automated → (2) targeted paid → (3) contact route. Escalating cost.
        credits += await _check_companies_house(db, site, provenance)
        credits += await _check_title_pull(db, site, validation, provenance)
        credits += await _check_occupancy(db, site, validation, provenance)
        credits += _resolve_contact_route(site, validation, provenance)

        validation.provenance_log = provenance
        validation.credits_spent = credits

        # Re-run the score and nudge it up where confirmation strengthens conviction.
        from app.engine.scoring import rescore_site  # lazy — avoid import cycle

        result = await rescore_site(db, site.uprn)
        nudged = result.conviction
        if validation.confirmed_ownership:
            nudged = min(100, nudged + 8)
        if validation.occupancy_status and "empty" in (validation.occupancy_status or "").lower():
            nudged = min(100, nudged + 5)
        validation.updated_conviction = nudged

        validation.status = ValidationStatus.complete.value
        validation.error = None
        await db.flush()
        log.info(
            "validation_complete",
            validation_id=validation_id,
            uprn=site.uprn,
            credits=credits,
            updated_conviction=nudged,
        )
        return validation
    except Exception:  # noqa: BLE001 — never leak PII; mark failed and persist what we have
        log.warning("validation_failed", validation_id=validation_id, uprn=validation.site_uprn)
        validation.status = ValidationStatus.failed.value
        validation.error = "Validation could not be completed."
        validation.provenance_log = provenance
        validation.credits_spent = credits
        await db.flush()
        return validation
