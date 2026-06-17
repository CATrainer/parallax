"""L2 — Entity resolution (the spine, §6.1).

Everything resolves to a canonical ``Site`` (UPRN) and ``Owner``. Address strings are
inputs to resolution, never identities (§3.3). Ownership links are probabilistic and
scored, never hard assertions.

GDPR: owner ``display_name`` is PII — it is never logged here or anywhere downstream.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from rapidfuzz.fuzz import token_sort_ratio
from sqlalchemy import func, select

from app.core.logging import get_logger
from app.models.entities import GeocodeCache, Owner, OwnershipLink, Site
from app.models.enums import OwnerType

log = get_logger("engine.resolution")

# Fuzzy-match threshold for individual owner identity (name token-sort ratio).
_OWNER_NAME_THRESHOLD = 88

# Common address-token standardisations (applied after upper-casing).
_STANDARDISE = {
    r"\bROAD\b": "RD",
    r"\bSTREET\b": "ST",
    r"\bAVENUE\b": "AVE",
    r"\bLANE\b": "LN",
    r"\bDRIVE\b": "DR",
    r"\bCLOSE\b": "CL",
    r"\bCOURT\b": "CT",
    r"\bPLACE\b": "PL",
    r"\bSQUARE\b": "SQ",
    r"\bTERRACE\b": "TER",
    r"\bCRESCENT\b": "CRES",
    r"\bGARDENS\b": "GDNS",
    r"\bFLAT\b": "FLAT",
    r"\bAPARTMENT\b": "FLAT",
}

# UK postcode (loose) — last whitespace-delimited token group.
_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b")


def normalise_address(address: str) -> dict:
    """Normalise a free-text address → ``{key, paon, saon, postcode}``.

    - strip / upper-case / collapse whitespace / standardise common street suffixes
    - parse a trailing postcode out
    - parse PAON (primary addressable object — leading number/name) and SAON (sub-building,
      e.g. ``FLAT 2``)

    ``key`` is the stable cache/fallback key: the cleaned address sans postcode, postcode
    appended in canonical (spaced) form so format variants collapse to one site.
    """
    if not address:
        return {"key": "", "paon": None, "saon": None, "postcode": None}

    cleaned = re.sub(r"\s+", " ", address.strip().upper())
    cleaned = cleaned.replace(",", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for pattern, repl in _STANDARDISE.items():
        cleaned = re.sub(pattern, repl, cleaned)

    postcode = None
    m = _POSTCODE_RE.search(cleaned)
    if m:
        raw_pc = re.sub(r"\s+", "", m.group(1))
        # Canonicalise: inward code is always the last 3 chars.
        postcode = f"{raw_pc[:-3]} {raw_pc[-3:]}".strip()
        cleaned = (cleaned[: m.start()] + " " + cleaned[m.end():]).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # SAON: a leading FLAT/UNIT/APARTMENT clause.
    saon = None
    saon_m = re.match(r"^(FLAT|UNIT|APARTMENT|FLAT)\s+([\w\-]+)\b", cleaned)
    if saon_m:
        saon = f"{saon_m.group(1)} {saon_m.group(2)}".strip()
        rest = cleaned[saon_m.end():].strip()
    else:
        rest = cleaned

    # PAON: the leading number (optionally with a letter, e.g. 14A) or first name token.
    paon = None
    paon_m = re.match(r"^(\d+[A-Z]?)\b", rest)
    if paon_m:
        paon = paon_m.group(1)

    key_parts = [p for p in (cleaned, postcode) if p]
    key = " ".join(key_parts).strip()
    return {"key": key, "paon": paon, "saon": saon, "postcode": postcode}


async def _get_or_create_geocode(db, address_key: str, address: str, postcode: str | None):
    """Return a GeocodeCache row, calling the geocoder on miss and caching permanently (§5.2)."""
    stmt = select(GeocodeCache).where(GeocodeCache.address_key == address_key)
    cached = (await db.execute(stmt)).scalar_one_or_none()
    if cached is not None:
        return cached

    from app.adapters.geocoder import get_geocoder  # lazy — avoid import cycle

    match = None
    try:
        match = await get_geocoder().resolve(address, postcode=postcode)
    except Exception:  # noqa: BLE001 — geocoder failure must not crash resolution
        log.warning("geocode_failed", address_key_len=len(address_key))

    if match is None:
        cache = GeocodeCache(
            address_key=address_key,
            uprn=None,
            lat=None,
            lng=None,
            match_confidence=0.0,
            provider="unresolved",
        )
    else:
        cache = GeocodeCache(
            address_key=address_key,
            uprn=match.uprn,
            lat=match.lat,
            lng=match.lng,
            match_confidence=match.match_confidence,
            provider=match.provider,
        )
    db.add(cache)
    await db.flush()
    return cache


async def _match_existing_site(
    db, address_key: str, postcode: str | None, paon: str | None
) -> Site | None:
    """Find an already-canonical site for this address (dedupe + connect pulls to the spine).

    The geocoder may not return a UPRN (e.g. SEED, or an unlicensed link), so we must not
    blindly mint a surrogate when a canonical site already exists for the same real address.
    Match on postcode, comparing normalised address keys; fall back to a unique postcode+PAON.
    """
    if not postcode:
        return None
    rows = list((await db.execute(select(Site).where(Site.postcode == postcode))).scalars().all())
    for s in rows:
        if normalise_address(s.address or "").get("key") == address_key:
            return s
    if paon:
        cands = [s for s in rows if (s.paon == paon)]
        if len(cands) == 1:
            return cands[0]
    return None


async def resolve_site(
    db,
    address: str,
    postcode: str | None = None,
    *,
    paon: str | None = None,
    saon: str | None = None,
    property_type: str | None = None,
    local_authority: str | None = None,
) -> Site:
    """Normalise address, geocode (cached), upsert the canonical ``Site``.

    Resolution order: an existing canonical site for the same real address wins (so pulls and
    broker enrichment attach to the seeded/owned spine); else the geocoder's UPRN; else a
    deterministic normalised-address surrogate so the record is still addressable.
    """
    norm = normalise_address(address)
    address_key = norm["key"] or address.strip().upper()
    eff_postcode = postcode or norm["postcode"]
    eff_paon = paon or norm["paon"]
    eff_saon = saon or norm["saon"]

    cache = await _get_or_create_geocode(db, address_key, address, eff_postcode)

    # 1) Reuse an existing canonical site for this address if one exists.
    site = await _match_existing_site(db, address_key, eff_postcode, eff_paon)

    # 2) Otherwise key by the geocoder's real UPRN, else a fallback surrogate (fits String(20)).
    if site is None:
        if cache.uprn:
            site_key = cache.uprn
        else:
            site_key = "ADDR" + str(abs(hash(address_key)) % (10**14)).zfill(14)
        site = await db.get(Site, site_key)
    else:
        site_key = site.uprn
    lat = cache.lat
    lng = cache.lng
    geom = (
        func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
        if (lat is not None and lng is not None)
        else None
    )

    if site is None:
        site = Site(
            uprn=site_key,
            address=address.strip(),
            postcode=eff_postcode,
            paon=eff_paon,
            saon=eff_saon,
            lat=lat,
            lng=lng,
            geom=geom,
            property_type=property_type,
            local_authority=local_authority,
            resolution_confidence=cache.match_confidence,
        )
        db.add(site)
    else:
        # Upsert: fill gaps, refresh coords/confidence; do not clobber with None.
        site.address = address.strip() or site.address
        site.postcode = eff_postcode or site.postcode
        site.paon = eff_paon or site.paon
        site.saon = eff_saon or site.saon
        if lat is not None and lng is not None:
            site.lat = lat
            site.lng = lng
            site.geom = geom
        site.property_type = property_type or site.property_type
        site.local_authority = local_authority or site.local_authority
        if cache.match_confidence:
            site.resolution_confidence = cache.match_confidence

    await db.flush()
    log.info(
        "site_resolved",
        uprn=site.uprn,
        resolved=bool(cache.uprn),
        confidence=round(cache.match_confidence, 2),
    )
    return site


async def resolve_owner(
    db,
    *,
    owner_type: str,
    display_name: str,
    company_number: str | None = None,
    dob_month: int | None = None,
    dob_year: int | None = None,
    last_known_address: str | None = None,
) -> Owner:
    """Fuzzy-upsert an Owner. PII (``display_name``) is never logged.

    - Companies match deterministically on ``company_number``.
    - Individuals fuzzy-match existing owners on name (token_sort_ratio ≥ 88) + DOB +
      postcode, to collapse the same person seen across sources into one identity (§6.1).
    """
    last_known_postcode = None
    if last_known_address:
        last_known_postcode = normalise_address(last_known_address).get("postcode")

    if owner_type == OwnerType.company.value and company_number:
        stmt = select(Owner).where(
            Owner.owner_type == OwnerType.company.value,
            Owner.company_number == company_number,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            existing.display_name = display_name or existing.display_name
            existing.last_known_address = last_known_address or existing.last_known_address
            existing.last_known_postcode = last_known_postcode or existing.last_known_postcode
            await db.flush()
            log.info("owner_matched", owner_type="company", company_number=company_number)
            return existing
        owner = Owner(
            owner_type=OwnerType.company.value,
            display_name=display_name,
            company_number=company_number,
            last_known_address=last_known_address,
            last_known_postcode=last_known_postcode,
        )
        db.add(owner)
        await db.flush()
        log.info("owner_created", owner_type="company", company_number=company_number)
        return owner

    # Individual: fuzzy identity on name + DOB + postcode.
    candidates = (
        await db.execute(
            select(Owner).where(Owner.owner_type == OwnerType.individual.value)
        )
    ).scalars().all()

    target = (display_name or "").strip().upper()
    best = None
    best_score = 0.0
    for cand in candidates:
        score = token_sort_ratio(target, (cand.display_name or "").strip().upper())
        if score < _OWNER_NAME_THRESHOLD:
            continue
        # DOB must be consistent where both sides have it.
        if dob_year and cand.dob_year and dob_year != cand.dob_year:
            continue
        if dob_month and cand.dob_month and dob_month != cand.dob_month:
            continue
        # Postcode corroboration nudges the match (not required).
        if (
            last_known_postcode
            and cand.last_known_postcode
            and last_known_postcode != cand.last_known_postcode
        ):
            score -= 10
        if score > best_score:
            best_score = score
            best = cand

    if best is not None and best_score >= _OWNER_NAME_THRESHOLD:
        best.dob_month = best.dob_month or dob_month
        best.dob_year = best.dob_year or dob_year
        best.last_known_address = last_known_address or best.last_known_address
        best.last_known_postcode = last_known_postcode or best.last_known_postcode
        await db.flush()
        log.info("owner_matched", owner_type="individual", score=round(best_score, 1))
        return best

    owner = Owner(
        owner_type=OwnerType.individual.value,
        display_name=display_name,
        dob_month=dob_month,
        dob_year=dob_year,
        last_known_address=last_known_address,
        last_known_postcode=last_known_postcode,
    )
    db.add(owner)
    await db.flush()
    log.info("owner_created", owner_type="individual")
    return owner


async def link_ownership(
    db,
    site: Site,
    owner: Owner,
    role: str,
    source: str,
    link_confidence: float,
    is_current: bool = True,
) -> OwnershipLink:
    """Upsert an ``OwnershipLink`` by (site, owner, role). Links are probabilistic (§6.1)."""
    stmt = select(OwnershipLink).where(
        OwnershipLink.site_uprn == site.uprn,
        OwnershipLink.owner_id == owner.id,
        OwnershipLink.role == role,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        existing.source = source
        existing.link_confidence = link_confidence
        existing.is_current = is_current
        if is_current and existing.valid_from is None:
            existing.valid_from = datetime.now(timezone.utc)
        await db.flush()
        log.info("ownership_updated", uprn=site.uprn, role=role, confidence=round(link_confidence, 2))
        return existing

    link = OwnershipLink(
        site_uprn=site.uprn,
        owner_id=owner.id,
        role=role,
        source=source,
        link_confidence=link_confidence,
        is_current=is_current,
        valid_from=datetime.now(timezone.utc) if is_current else None,
    )
    db.add(link)
    await db.flush()
    log.info("ownership_linked", uprn=site.uprn, role=role, confidence=round(link_confidence, 2))
    return link
