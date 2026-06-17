"""L3 — Signal extraction (§6.2).

Raw records become typed, time-stamped, source-attributed weak signals attached to a
resolved Site (and Owner where relevant). Brittleness dies here: no opportunity is ever
defined by one signal, and the engine degrades gracefully when a source drops out.

In SEED mode adapters return fixtures and the seed path may construct signals directly,
so this extractor is exercised mainly in LIVE. It must stay correct and defensive — every
payload field is treated as possibly-missing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.entities import OwnershipLink, RawRecord, Signal, Site
from app.models.enums import SignalType

log = get_logger("engine.signals")


# ───────────────────────────────── Signal catalogue (§6.2 table) ────────────────────────────────
# strength: base 0–1 conviction weight of the signal when freshly fired.
# decays:   how its strength fades with time — slow|medium|fast (see decay_factor).
# default_source / label: provenance + display.
SIGNAL_CATALOGUE: dict[str, dict] = {
    SignalType.probate_inherited.value: {
        "strength": 0.85,
        "decays": "slow",
        "default_source": "gazette_deceased",
        "label": "Probate / inherited",
    },
    SignalType.epc_lapsed.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "epc",
        "label": "EPC lapsed (vacancy inference)",
    },
    SignalType.epc_fg_refurb.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "epc",
        "label": "EPC F/G (refurb need)",
    },
    SignalType.no_listing.value: {
        "strength": 0.3,
        "decays": "fast",
        "default_source": "listing",
        "label": "Not currently listed",
    },
    SignalType.owner_spv_distress.value: {
        "strength": 0.85,
        "decays": "medium",
        "default_source": "companies_house",
        "label": "Owner / SPV distress",
    },
    SignalType.long_hold_unimproved.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "hmlr_price_paid",
        "label": "Long hold, unimproved",
    },
    SignalType.planning_refusal.value: {
        "strength": 0.8,
        "decays": "medium",
        "default_source": "planit",
        "label": "Planning refusal (motivation)",
    },
    SignalType.commercial_empty.value: {
        "strength": 0.8,
        "decays": "medium",
        "default_source": "voa",
        "label": "Commercial empty",
    },
    SignalType.wrong_use_gap.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "voa",
        "label": "Wrong-use gap",
    },
    SignalType.site_activity_decline.value: {
        "strength": 0.7,
        "decays": "medium",
        "default_source": "imagery",
        "label": "Site activity decline",
    },
    SignalType.long_distance_owner.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "hmlr_price_paid",
        "label": "Long-distance owner",
    },
    SignalType.portfolio_regulatory_pressure.value: {
        "strength": 0.55,
        "decays": "slow",
        "default_source": "companies_house",
        "label": "Portfolio regulatory pressure",
    },
    SignalType.single_property_owner.value: {
        "strength": 0.5,
        "decays": "slow",
        "default_source": "companies_house",
        "label": "Single-property owner (corroborator)",
    },
}

# Half-life (days) per decay class — slow fades very gently, fast steeply.
_HALF_LIFE_DAYS = {"slow": 1825.0, "medium": 365.0, "fast": 60.0}


def decay_factor(decays: str, observed_at, now=None) -> float:
    """Time-decay multiplier in [0, 1] applied to a signal's strength.

    slow → very gentle (≈5yr half-life), medium → moderate (1yr), fast → steep (~2mo).
    Defensive: missing/naive ``observed_at`` or unknown class returns 1.0 (no decay).
    """
    if observed_at is None:
        return 1.0
    if now is None:
        now = datetime.now(timezone.utc)
    half_life = _HALF_LIFE_DAYS.get((decays or "slow"), _HALF_LIFE_DAYS["slow"])
    try:
        obs = observed_at
        if obs.tzinfo is None:
            obs = obs.replace(tzinfo=timezone.utc)
        age_days = (now - obs).total_seconds() / 86400.0
    except (AttributeError, TypeError):
        return 1.0
    if age_days <= 0:
        return 1.0
    return float(0.5 ** (age_days / half_life))


def _catalogue_for(signal_type: str) -> dict:
    return SIGNAL_CATALOGUE.get(
        signal_type, {"strength": 0.5, "decays": "slow", "default_source": "unknown", "label": signal_type}
    )


def _coerce_dt(value) -> datetime | None:
    """Best-effort parse of a payload date field into an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        v = value.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt = datetime.strptime(v, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _make_signal(
    *,
    site_uprn: str,
    signal_type: str,
    raw_evidence: str,
    source: str | None,
    source_ref: str | None,
    observed_at: datetime | None,
    owner_id: str | None = None,
    data: dict | None = None,
    strength: float | None = None,
) -> Signal:
    cat = _catalogue_for(signal_type)
    return Signal(
        site_uprn=site_uprn,
        owner_id=owner_id,
        signal_type=signal_type,
        fired=True,
        strength=float(strength if strength is not None else cat["strength"]),
        raw_evidence=raw_evidence,
        source=source or cat["default_source"],
        source_ref=source_ref,
        observed_at=observed_at or datetime.now(timezone.utc),
        decays=cat["decays"],
        data=data or {},
    )


async def _resolve_site_uprn(db, payload: dict) -> str | None:
    """Find the resolved site for a raw payload. Prefers an explicit UPRN, else address match."""
    uprn = payload.get("uprn") or payload.get("UPRN")
    if uprn:
        site = await db.get(Site, str(uprn))
        if site:
            return site.uprn
    # Fall back to the resolution spine on whatever address fields exist.
    address = payload.get("address") or payload.get("property_address") or payload.get("paon_address")
    if address:
        from app.engine.resolution import resolve_site  # lazy — avoid import cycle

        try:
            site = await resolve_site(
                db,
                address,
                postcode=payload.get("postcode"),
                paon=payload.get("paon"),
                saon=payload.get("saon"),
            )
            return site.uprn
        except Exception:  # noqa: BLE001 — resolution failure must not crash extraction
            log.warning("signal_site_resolution_failed", source=payload.get("_source"))
            return None
    return None


async def _owner_for_site(db, site_uprn: str) -> str | None:
    """Best current owner_id for a site, if any (for owner-attached signals)."""
    stmt = (
        select(OwnershipLink.owner_id)
        .where(OwnershipLink.site_uprn == site_uprn, OwnershipLink.is_current.is_(True))
        .order_by(OwnershipLink.link_confidence.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


# ─────────────────────────────────────── Per-source extractors ──────────────────────────────────
async def _extract_gazette_deceased(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    sig = _make_signal(
        site_uprn=uprn,
        signal_type=SignalType.probate_inherited.value,
        raw_evidence="Deceased-estate notice in The Gazette matched to this site's last-known proprietor.",
        source=raw.source,
        source_ref=raw.source_ref or p.get("notice_url"),
        observed_at=_coerce_dt(p.get("date_of_death") or p.get("publication_date") or raw.fetched_at),
        owner_id=owner_id,
        data={"executor_present": bool(p.get("executor"))},
    )
    return [sig]


async def _extract_gazette_insolvency(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    sig = _make_signal(
        site_uprn=uprn,
        signal_type=SignalType.owner_spv_distress.value,
        raw_evidence="Insolvency notice in The Gazette against the owning entity / individual.",
        source=raw.source,
        source_ref=raw.source_ref or p.get("notice_url"),
        observed_at=_coerce_dt(p.get("publication_date") or raw.fetched_at),
        owner_id=owner_id,
        data={"notice_type": p.get("notice_type")},
    )
    return [sig]


async def _extract_epc(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    out: list[Signal] = []
    rating = (p.get("current_energy_rating") or p.get("energy_rating") or "").strip().upper()
    lodged = _coerce_dt(p.get("lodgement_date") or p.get("inspection_date"))

    # Lapsed/old EPC → vacancy inference. An EPC older than ~10y (or flagged lapsed) fires.
    lapsed_flag = bool(p.get("lapsed"))
    stale = False
    if lodged is not None:
        stale = (datetime.now(timezone.utc) - lodged).days > 3650
    if lapsed_flag or stale:
        out.append(
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.epc_lapsed.value,
                raw_evidence="EPC certificate lapsed or markedly out of date — consistent with vacancy.",
                source=raw.source,
                source_ref=raw.source_ref or p.get("lmk_key"),
                observed_at=lodged or raw.fetched_at,
                owner_id=owner_id,
                data={"rating": rating or None, "lapsed": lapsed_flag},
            )
        )

    # F/G rating → refurb-need signal.
    if rating in {"F", "G"}:
        out.append(
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.epc_fg_refurb.value,
                raw_evidence=f"EPC band {rating} — significant refurbishment / MEES exposure.",
                source=raw.source,
                source_ref=raw.source_ref or p.get("lmk_key"),
                observed_at=lodged or raw.fetched_at,
                owner_id=owner_id,
                data={"rating": rating},
            )
        )
    return out


async def _extract_hmlr_price_paid(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    out: list[Signal] = []
    last_sale = _coerce_dt(p.get("date_of_transfer") or p.get("sale_date"))
    years_held = None
    if last_sale is not None:
        years_held = (datetime.now(timezone.utc) - last_sale).days / 365.25

    # Long hold without improvement (no intervening sale; held many years).
    if years_held is not None and years_held >= 15:
        out.append(
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.long_hold_unimproved.value,
                raw_evidence=f"Held ~{years_held:.0f} years with no recorded resale — long hold, likely unimproved.",
                source=raw.source,
                source_ref=raw.source_ref or p.get("transaction_id"),
                observed_at=last_sale,
                owner_id=owner_id,
                data={"years_held": round(years_held, 1)},
            )
        )
    return out


async def _extract_companies_house(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    out: list[Signal] = []

    distress = (
        p.get("insolvency")
        or p.get("has_charges")
        or p.get("late_filing")
        or (p.get("company_status") or "").lower() in {"liquidation", "administration", "dissolved"}
    )
    if distress:
        out.append(
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.owner_spv_distress.value,
                raw_evidence="Companies House signals on the owning entity (late filings / charges / insolvency).",
                source=raw.source,
                source_ref=raw.source_ref or p.get("company_number"),
                observed_at=_coerce_dt(p.get("last_event_date")) or raw.fetched_at,
                owner_id=owner_id,
                data={"company_status": p.get("company_status")},
            )
        )

    # Single-property SPV corroborator.
    title_count = p.get("title_count")
    if title_count == 1 or p.get("single_property") is True:
        out.append(
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.single_property_owner.value,
                raw_evidence="Owning entity appears to hold a single property — concentrated exposure.",
                source=raw.source,
                source_ref=raw.source_ref or p.get("company_number"),
                observed_at=raw.fetched_at,
                owner_id=owner_id,
                data={"title_count": title_count},
            )
        )
    return out


async def _extract_planit(db, raw, uprn, owner_id) -> list[Signal]:
    p = raw.payload or {}
    decision = (p.get("decision") or p.get("status") or "").strip().lower()
    if "refus" in decision or "dismiss" in decision or p.get("refused") is True:
        return [
            _make_signal(
                site_uprn=uprn,
                signal_type=SignalType.planning_refusal.value,
                raw_evidence="Planning application refused / appeal dismissed — owner tried and failed to add value.",
                source=raw.source,
                source_ref=raw.source_ref or p.get("reference") or p.get("url"),
                observed_at=_coerce_dt(p.get("decided_date") or p.get("decision_date")) or raw.fetched_at,
                owner_id=owner_id,
                data={"decision": decision},
            )
        ]
    return []


# source → extractor dispatch
_DISPATCH = {
    "gazette_deceased": _extract_gazette_deceased,
    "gazette_insolvency": _extract_gazette_insolvency,
    "epc": _extract_epc,
    "hmlr_price_paid": _extract_hmlr_price_paid,
    "companies_house": _extract_companies_house,
    "planit": _extract_planit,
}


async def extract_signals(db, raw: RawRecord) -> list[Signal]:
    """Dispatch on ``raw.source`` to derive zero+ typed Signals, persist them, mark processed.

    Defensive throughout: an unresolved site or a missing extractor yields an empty list and
    still marks the record processed (so the queue does not stall). Never raises on bad payloads.
    """
    extractor = _DISPATCH.get(raw.source)
    if extractor is None:
        log.info("signal_no_extractor", source=raw.source)
        raw.processed = True
        await db.flush()
        return []

    uprn = await _resolve_site_uprn(db, {**(raw.payload or {}), "_source": raw.source})
    if not uprn:
        log.info("signal_unresolved_site", source=raw.source)
        raw.processed = True
        await db.flush()
        return []

    owner_id = await _owner_for_site(db, uprn)

    try:
        signals = await extractor(db, raw, uprn, owner_id)
    except Exception:  # noqa: BLE001 — one bad record must not poison the batch
        log.warning("signal_extraction_error", source=raw.source)
        signals = []

    for sig in signals:
        db.add(sig)
    raw.processed = True
    await db.flush()
    log.info("signals_extracted", source=raw.source, count=len(signals))
    return signals
