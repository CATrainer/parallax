"""L4 — Synthesis (the hero). Produces and persists the Briefing (§6.3).

Flow (`synthesize_briefing`):
  1. Load Site + its fired Signals + ownership links.
  2. Score the signals (`score_signals`) → ScoreResult (conviction/band/headline/opportunities).
  3. Build a compact payload (site facts, signals, ownership, the scored opportunity picture).
  4. Cheap pass (classify/cluster) for breadth; premium pass for the narrative IF premium AND the
     score clears the conviction floor (31) — else cheap/template renders it. Route via get_provider.
  5. Validate the returned JSON; ENFORCE that every cited / contributing signal id is a real id from
     the payload (drop invalid refs). Force conviction/band to the ScoreResult — the model explains the
     computed number, it never invents it.
  6. Upsert the single current Briefing for the site; record synthesis_model. Return the ORM object.

Guardrails live in the prompts; the validation here is the belt-and-braces that holds for ANY provider,
including the deterministic template. The app runs fully with no Anthropic key.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.engine.inference import get_provider
from app.models.entities import Briefing, OwnershipLink, Signal, Site

log = get_logger("parallax.synthesis")

# §6.4 — premium synthesis is gated to candidates above the conviction floor (MONITOR = 31).
CONVICTION_FLOOR = 31


# ─────────────────────────────────────── payload builders ───────────────────────────────────────
def _signal_payload(sig: Signal) -> dict:
    return {
        "id": sig.id,
        "signal_type": sig.signal_type,
        "fired": bool(sig.fired),
        "strength": round(float(sig.strength or 0.0), 3),
        "raw_evidence": sig.raw_evidence,
        "source": sig.source,
        "observed_at": sig.observed_at.isoformat() if sig.observed_at else None,
        "decays": sig.decays,
    }


def _ownership_payload(link: OwnershipLink) -> dict:
    owner = link.owner
    return {
        "role": link.role,
        "link_confidence": round(float(link.link_confidence or 0.0), 3),
        "is_current": bool(link.is_current),
        "source": link.source,
        "owner_type": owner.owner_type if owner else None,
        "owner_display": owner.display_name if owner else None,  # PII — payload only, never logged
        "company_number": owner.company_number if owner else None,
    }


def _build_payload(site: Site, signals: list[Signal], ownership: list[OwnershipLink], score) -> dict:
    return {
        "site": {
            "uprn": site.uprn,
            "address": site.address,
            "postcode": site.postcode,
            "property_type": site.property_type,
            "tenure": site.tenure,
            "local_authority": site.local_authority,
            "resolution_confidence": round(float(site.resolution_confidence or 0.0), 3),
        },
        "signals": [_signal_payload(s) for s in signals],
        "ownership": [_ownership_payload(o) for o in ownership],
        "conviction": score.conviction,
        "band": score.band,
        "headline_opportunity": score.headline_opportunity,
        "opportunity_scores": score.opportunity_scores,
        "matched_opportunity_types": score.matched_opportunity_types,
    }


# ──────────────────────────────────────── id enforcement ────────────────────────────────────────
def _filter_ids(ids, valid: set[str]) -> list[str]:
    if not isinstance(ids, list):
        return []
    return [i for i in ids if i in valid]


def _sanitize_briefing_json(data: dict, valid_ids: set[str], score) -> dict:
    """Drop invalid signal-id references; force conviction/band to the computed ScoreResult."""
    paragraphs = []
    for p in data.get("paragraphs", []) or []:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        paragraphs.append(
            {"text": str(p["text"]), "cited_signal_ids": _filter_ids(p.get("cited_signal_ids"), valid_ids)}
        )

    conclusions = []
    for c in data.get("conclusions", []) or []:
        if not isinstance(c, dict) or not c.get("statement"):
            continue
        try:
            conf = float(c.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        conclusions.append(
            {
                "type": str(c.get("type", "inference")),
                "statement": str(c["statement"]),
                "confidence": max(0.0, min(1.0, conf)),
                "contributing_signal_ids": _filter_ids(c.get("contributing_signal_ids"), valid_ids),
            }
        )

    opp_types = data.get("opportunity_types") or score.matched_opportunity_types or []
    if score.headline_opportunity and score.headline_opportunity not in opp_types:
        opp_types = [score.headline_opportunity, *opp_types]

    return {
        "lede": str(data.get("lede") or "").strip()
        or "This briefing summarises the available signals for the site.",
        "paragraphs": paragraphs,
        "takeaway": str(data.get("takeaway") or "").strip()
        or "Review the signals below and validate before acting.",
        "conclusions": conclusions,
        # The model never gets to invent the number — synthesis prose explains the computed score.
        "conviction": int(score.conviction),
        "band": score.band,
        "opportunity_types": [o for o in opp_types if o],
        "headline_opportunity": score.headline_opportunity,
    }


# ──────────────────────────────────────── core synthesis ────────────────────────────────────────
async def synthesize_briefing(db: AsyncSession, uprn: str, *, premium: bool = True) -> Briefing:
    """Score, synthesise (premium gated to the floor), persist one current Briefing, return it."""
    # Lazy import to avoid an import cycle with the scoring module (built in parallel).
    from app.engine.scoring import score_signals

    site = (
        await db.execute(
            select(Site)
            .where(Site.uprn == uprn)
            .options(
                selectinload(Site.signals),
                selectinload(Site.ownership_links).selectinload(OwnershipLink.owner),
            )
        )
    ).scalar_one_or_none()
    if site is None:
        raise ValueError(f"site not found: {uprn}")

    fired = [s for s in site.signals if s.fired]
    ownership = list(site.ownership_links)
    score = score_signals(fired)
    valid_ids = {s.id for s in fired}

    payload = _build_payload(site, fired, ownership, score)

    # Cheap pass first — cluster/classify for breadth. Best-effort; never blocks the briefing.
    try:
        cheap = get_provider("cheap")
        await cheap.complete("classify_signals", payload)
    except Exception as exc:  # noqa: BLE001 — cheap pass is optional triage
        log.info("classify_pass_skipped", uprn=uprn, error=str(exc))

    # Premium pass only when asked AND the score clears the conviction floor; else cheap tier.
    use_premium = premium and score.conviction >= CONVICTION_FLOOR
    tier = "premium" if use_premium else "cheap"
    provider = get_provider(tier)

    raw: dict
    model_used: str
    try:
        raw = await provider.complete("synthesize_briefing", payload)
        model_used = getattr(provider, "name", tier)
    except Exception as exc:  # noqa: BLE001 — any provider failure falls back to the template
        log.warning("synthesis_provider_failed", uprn=uprn, tier=tier, error=str(exc))
        from app.engine.inference import TemplateProvider

        fallback = TemplateProvider()
        raw = await fallback.complete("synthesize_briefing", payload)
        model_used = fallback.name

    clean = _sanitize_briefing_json(raw, valid_ids, score)

    briefing = await _upsert_briefing(db, site, clean, score, model_used)
    log.info(
        "briefing_synthesised",
        uprn=uprn,
        tier=tier,
        model=model_used,
        conviction=score.conviction,
        band=score.band,
        signal_count=len(fired),
    )
    return briefing


async def _upsert_briefing(
    db: AsyncSession, site: Site, clean: dict, score, model_used: str
) -> Briefing:
    """One current briefing per site — overwrite the existing row, else insert."""
    existing = (
        await db.execute(select(Briefing).where(Briefing.site_uprn == site.uprn))
    ).scalars().all()

    briefing = existing[0] if existing else Briefing(site_uprn=site.uprn)
    # Any stragglers (shouldn't happen) get marked stale rather than orphaned.
    for extra in existing[1:]:
        extra.is_stale = True

    briefing.lede = clean["lede"]
    briefing.paragraphs = clean["paragraphs"]
    briefing.takeaway = clean["takeaway"]
    briefing.conclusions = clean["conclusions"]
    briefing.conviction = clean["conviction"]
    briefing.band = clean["band"]
    briefing.opportunity_types = clean["opportunity_types"]
    briefing.headline_opportunity = clean["headline_opportunity"]
    briefing.signal_ids = list(score.signal_ids)
    briefing.synthesis_model = model_used
    briefing.is_stale = False

    if briefing not in existing:
        db.add(briefing)
    await db.commit()
    await db.refresh(briefing)
    return briefing


# ───────────────────────────────────────── freshness gate ────────────────────────────────────────
async def get_or_build_briefing(
    db: AsyncSession, uprn: str, *, premium: bool = True, max_age_minutes: int = 1440
) -> Briefing:
    """Return the persisted briefing if fresh and not stale, else (re)synthesise. API entry point."""
    existing = (
        await db.execute(
            select(Briefing)
            .where(Briefing.site_uprn == uprn, Briefing.is_stale.is_(False))
            .order_by(Briefing.updated_at.desc())
        )
    ).scalars().first()

    if existing is not None:
        updated = existing.updated_at
        if updated is not None:
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - updated
            if age <= timedelta(minutes=max_age_minutes):
                return existing

    return await synthesize_briefing(db, uprn, premium=premium)


# ───────────────────────────────────── API mapping helper ─────────────────────────────────────────
def briefing_to_out(briefing: Briefing, site: Site, signals, ownership) -> dict:
    """Build a BriefingOut-shaped dict for the API (tolerant; the API may map itself instead)."""

    def _sig(s: Signal) -> dict:
        return {
            "id": s.id,
            "signal_type": s.signal_type,
            "fired": bool(s.fired),
            "strength": float(s.strength or 0.0),
            "raw_evidence": s.raw_evidence,
            "source": s.source,
            "source_ref": s.source_ref,
            "observed_at": s.observed_at,
            "decays": s.decays,
        }

    def _own(link: OwnershipLink) -> dict:
        owner = link.owner
        return {
            "id": link.id,
            "role": link.role,
            "is_current": bool(link.is_current),
            "source": link.source,
            "link_confidence": float(link.link_confidence or 0.0),
            "owner": {
                "id": owner.id,
                "owner_type": owner.owner_type,
                "display_name": owner.display_name,
                "company_number": owner.company_number,
            }
            if owner
            else None,
        }

    return {
        "id": briefing.id,
        "site_uprn": briefing.site_uprn,
        "lede": briefing.lede,
        "paragraphs": briefing.paragraphs or [],
        "takeaway": briefing.takeaway,
        "conclusions": briefing.conclusions or [],
        "conviction": briefing.conviction,
        "band": briefing.band,
        "opportunity_types": briefing.opportunity_types or [],
        "headline_opportunity": briefing.headline_opportunity,
        "signals": [_sig(s) for s in (signals or [])],
        "ownership": [_own(o) for o in (ownership or [])],
        "site": {
            "uprn": site.uprn,
            "address": site.address,
            "postcode": site.postcode,
            "lat": site.lat,
            "lng": site.lng,
            "property_type": site.property_type,
            "tenure": site.tenure,
            "local_authority": site.local_authority,
            "resolution_confidence": float(site.resolution_confidence or 0.0),
        },
        "synthesis_model": briefing.synthesis_model,
        "is_stale": bool(briefing.is_stale),
        "computed_at": briefing.updated_at,
    }
