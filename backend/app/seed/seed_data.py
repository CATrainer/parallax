"""Seed a realistic Bristol (BS) patch — sites, owners, ownership links, and a rich spread
of signals across the full §6.2 catalogue. Idempotent (upsert by PK). Briefings are NOT
computed here (see app.seed.run, which calls synthesis after seeding).

Engineered so scoring yields a believable band spread, with at least five sites landing
LIKELY/STRONG for probate_inherited / empty_vacant (e.g. probate + epc_lapsed +
long_distance_owner + no_listing on the same site).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.entities import (
    Owner,
    OwnershipLink,
    Patch,
    Signal,
    Site,
    User,
)
from app.models.enums import Decay, OwnershipRole, OwnerType, SignalType

log = get_logger("seed")

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_NOW = datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _NOW - timedelta(days=n)


# ──────────────────────────────────────── Sites ────────────────────────────────────────
# 25 plausible Bristol addresses around (51.45, -2.59). UPRNs are valid-looking 12-digit.
# fmt: off
SITES: list[dict] = [
    # uprn,          paon, street,                  postcode, lat,     lng,     ptype,         la
    ("100120010001", "14",  "Mill Lane",            "BS3 4QN", 51.4392, -2.5921, "terraced",     None),
    ("100120010002", "27",  "Sandy Park Road",      "BS4 3PD", 51.4421, -2.5648, "terraced",     None),
    ("100120010003", "8",   "Cromwell Road",        "BS6 5HD", 51.4684, -2.5897, "semi",         None),
    ("100120010004", "112", "Gloucester Road",      "BS7 8BN", 51.4751, -2.5887, "flat",         None),
    ("100120010005", "3",   "Birchwood Road",       "BS4 4QU", 51.4376, -2.5402, "detached",     None),
    ("100120010006", "45",  "Cotham Hill",          "BS6 6JY", 51.4623, -2.6018, "terraced",     None),
    ("100120010007", "19",  "Stackpool Road",       "BS3 1NW", 51.4438, -2.6121, "terraced",     None),
    ("100120010008", "76",  "North Street",         "BS3 1JD", 51.4408, -2.6155, "flat",         None),
    ("100120010009", "5",   "Henleaze Road",        "BS9 4EX", 51.4889, -2.6064, "semi",         None),
    ("100120010010", "33",  "Coronation Road",      "BS3 1RP", 51.4451, -2.6087, "terraced",     None),
    ("100120010011", "21",  "Air Balloon Road",     "BS5 8LA", 51.4628, -2.5421, "terraced",     None),
    ("100120010012", "9",   "Royal York Crescent",  "BS8 4JX", 51.4534, -2.6219, "flat",         None),
    ("100120010013", "58",  "Stapleton Road",       "BS5 0RA", 51.4641, -2.5667, "commercial",   None),
    ("100120010014", "2",   "Westbury Hill",        "BS9 3AA", 51.4901, -2.6201, "detached",     None),
    ("100120010015", "41",  "Church Road",          "BS5 8AA", 51.4577, -2.5503, "commercial",   None),
    ("100120010016", "17",  "Ashley Down Road",     "BS7 9JN", 51.4791, -2.5841, "semi",         None),
    ("100120010017", "88",  "Filton Avenue",        "BS7 0AE", 51.4861, -2.5731, "terraced",     None),
    ("100120010018", "12",  "Pembroke Road",        "BS8 3BB", 51.4609, -2.6151, "flat",         None),
    ("100120010019", "6",   "Bishop Road",          "BS7 8LS", 51.4773, -2.5901, "terraced",     None),
    ("100120010020", "30",  "Wells Road",           "BS4 2PN", 51.4361, -2.5779, "flat",         None),
    ("100120010021", "4",   "Downend Road",         "BS16 5DA", 51.4891, -2.5301, "semi",        None),
    ("100120010022", "23",  "Lower Cheltenham Place","BS6 5JZ", 51.4659, -2.5832, "terraced",   None),
    ("100120010023", "51",  "West Street",          "BS3 3NU", 51.4448, -2.6201, "terraced",    None),
    ("100120010024", "1",   "Sefton Park Road",     "BS7 9AL", 51.4781, -2.5798, "detached",     None),
    ("100120010025", "67",  "Two Mile Hill Road",   "BS15 1AZ", 51.4608, -2.5101, "terraced",   None),
]
# fmt: on


# ─────────────────────────────────────── Owners ────────────────────────────────────────
# key, owner_type, display_name, company_number, dob_m, dob_y, last_known_address, last_pc
OWNERS: list[dict] = [
    # Individuals (some deceased → probate; some long-distance)
    ("own_smith", "individual", "John Smith", None, 3, 1944, "14 Mill Lane, Bristol", "BS3 4QN"),
    ("own_okafor", "individual", "Grace Okafor", None, 11, 1951, "27 Sandy Park Road, Bristol", "BS4 3PD"),
    ("own_patel", "individual", "Rajesh Patel", None, 7, 1939, "8 Cromwell Road, Bristol", "BS6 5HD"),
    ("own_thomas", "individual", "Eleanor Thomas", None, 1, 1948, "Flat 2, 112 Gloucester Road", "BS7 8BN"),
    ("own_wright", "individual", "Margaret Wright", None, 5, 1936, "5 Birchwood Road, Bristol", "BS4 4QU"),
    ("own_doyle", "individual", "Brendan Doyle", None, 9, 1962, "44 Marine Parade, Penzance", "TR18 4EZ"),
    ("own_khan", "individual", "Aisha Khan", None, 2, 1958, "210 Kingsland Road, London", "E8 4DG"),
    ("own_evans", "individual", "David Evans", None, 6, 1955, "9 Royal York Crescent, Bristol", "BS8 4JX"),
    ("own_clarke", "individual", "Susan Clarke", None, 4, 1971, "17 Ashley Down Road, Bristol", "BS7 9JN"),
    ("own_mcgrath", "individual", "Peter McGrath", None, 12, 1949, "1 Sefton Park Road, Bristol", "BS7 9AL"),
    # Companies (CH-style 8-digit numbers; some distressed SPVs)
    ("own_oldfield", "company", "Oldfield Property Holdings Ltd", "07412095", None, None, "12 King Street, Bristol", "BS1 4EF"),
    ("own_severn", "company", "Severn Lettings Ltd", "09988221", None, None, "3 Queen Square, Bristol", "BS1 4JE"),
    ("own_brunel", "company", "Brunel SPV No.4 Ltd", "11223344", None, None, "55 Baldwin Street, Bristol", "BS1 1RG"),
    ("own_avon", "company", "Avon Commercial Estates Ltd", "06650012", None, None, "8 Corn Street, Bristol", "BS1 1JN"),
    ("own_redcliffe", "company", "Redcliffe Regeneration Ltd", "10500900", None, None, "2 Redcliff Street, Bristol", "BS1 6BG"),
]


# ─────────────────────────── Ownership links (site_uprn → owner key) ────────────────────
# site_uprn, owner_key, role, link_confidence
LINKS: list[tuple[str, str, str, float]] = [
    ("100120010001", "own_smith", OwnershipRole.proprietor.value, 0.88),
    ("100120010001", "own_okafor", OwnershipRole.executor.value, 0.72),  # executor on Smith estate
    ("100120010002", "own_okafor", OwnershipRole.proprietor.value, 0.84),
    ("100120010003", "own_patel", OwnershipRole.proprietor.value, 0.90),
    ("100120010004", "own_thomas", OwnershipRole.proprietor.value, 0.81),
    ("100120010005", "own_wright", OwnershipRole.proprietor.value, 0.86),
    ("100120010006", "own_doyle", OwnershipRole.proprietor.value, 0.78),
    ("100120010007", "own_khan", OwnershipRole.proprietor.value, 0.69),
    ("100120010008", "own_severn", OwnershipRole.proprietor.value, 0.83),
    ("100120010009", "own_evans", OwnershipRole.proprietor.value, 0.79),
    ("100120010010", "own_oldfield", OwnershipRole.proprietor.value, 0.85),
    ("100120010011", "own_severn", OwnershipRole.proprietor.value, 0.80),
    ("100120010012", "own_evans", OwnershipRole.proprietor.value, 0.74),
    ("100120010013", "own_avon", OwnershipRole.proprietor.value, 0.87),
    ("100120010014", "own_mcgrath", OwnershipRole.proprietor.value, 0.91),
    ("100120010015", "own_avon", OwnershipRole.proprietor.value, 0.82),
    ("100120010016", "own_clarke", OwnershipRole.proprietor.value, 0.88),
    ("100120010017", "own_oldfield", OwnershipRole.proprietor.value, 0.76),
    ("100120010018", "own_khan", OwnershipRole.proprietor.value, 0.70),
    ("100120010019", "own_brunel", OwnershipRole.proprietor.value, 0.84),
    ("100120010020", "own_severn", OwnershipRole.proprietor.value, 0.77),
    ("100120010021", "own_clarke", OwnershipRole.proprietor.value, 0.83),
    ("100120010022", "own_doyle", OwnershipRole.proprietor.value, 0.71),
    ("100120010023", "own_redcliffe", OwnershipRole.proprietor.value, 0.86),
    ("100120010024", "own_mcgrath", OwnershipRole.proprietor.value, 0.92),
    ("100120010025", "own_oldfield", OwnershipRole.proprietor.value, 0.75),
    # PSC / director links for company owners (owner-resolution synthesis)
    ("100120010019", "own_evans", OwnershipRole.psc.value, 0.66),
    ("100120010013", "own_mcgrath", OwnershipRole.director.value, 0.63),
    ("100120010003", "own_okafor", OwnershipRole.executor.value, 0.74),  # second probate estate
]


# ─────────────────────────────────────── Signals ───────────────────────────────────────
# Each: site_uprn, owner_key|None, SignalType, strength, decay, days_ago, raw_evidence, source, source_ref
S = SignalType
D = Decay
SIGNALS: list[tuple] = [
    # ── Site 1 (14 Mill Lane): PROBATE STRONG — probate + epc_lapsed + long_distance_owner + no_listing ──
    ("100120010001", "own_smith", S.probate_inherited.value, 0.92, D.slow.value, 95,
     "Gazette deceased estate notice: J. Smith, last address 14 Mill Lane, d. Mar 2026; executor named.",
     "gazette_deceased", "https://www.thegazette.co.uk/notice/4012001"),
    ("100120010001", None, S.epc_lapsed.value, 0.70, D.slow.value, 40,
     "EPC last lodged 2009, certificate expired; no re-lodgement on let or sale.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0001-1234"),
    ("100120010001", "own_okafor", S.long_distance_owner.value, 0.60, D.slow.value, 30,
     "Executor correspondence address differs from site; estate administered remotely.",
     "companies_house", "https://api.company-information.service.gov.uk/officers/x1"),
    ("100120010001", None, S.no_listing.value, 0.45, D.fast.value, 12,
     "No active sale or rental listing found across sanctioned aggregator feed.",
     "listing", "https://parallax.internal/listing-check/100120010001"),

    # ── Site 3 (8 Cromwell Road): PROBATE STRONG ──
    ("100120010003", "own_patel", S.probate_inherited.value, 0.90, D.slow.value, 70,
     "Gazette deceased estate notice: R. Patel, last address 8 Cromwell Road, d. Jan 2026.",
     "gazette_deceased", "https://www.thegazette.co.uk/notice/4012003"),
    ("100120010003", None, S.epc_lapsed.value, 0.68, D.slow.value, 55,
     "EPC lodged 2010, expired; floor area 96 sqm; no recent assessment.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0003-5678"),
    ("100120010003", "own_okafor", S.long_distance_owner.value, 0.58, D.slow.value, 50,
     "Named executor resident outside Bristol; estate likely to liquidate.",
     "companies_house", "https://api.company-information.service.gov.uk/officers/x3"),
    ("100120010003", None, S.no_listing.value, 0.44, D.fast.value, 10,
     "Property not listed for sale or to let.",
     "listing", "https://parallax.internal/listing-check/100120010003"),

    # ── Site 5 (5 Birchwood Road): EMPTY/VACANT LIKELY/STRONG (probate + epc + no_listing) ──
    ("100120010005", "own_wright", S.probate_inherited.value, 0.85, D.slow.value, 120,
     "Gazette deceased estate notice: M. Wright, last address 5 Birchwood Road, d. Nov 2025.",
     "gazette_deceased", "https://www.thegazette.co.uk/notice/4012005"),
    ("100120010005", None, S.epc_lapsed.value, 0.72, D.slow.value, 60,
     "Detached property, EPC expired 2021; large floor area 142 sqm.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0005-9012"),
    ("100120010005", None, S.no_listing.value, 0.46, D.fast.value, 8,
     "No marketing presence detected; consistent with carrying-cost vacancy.",
     "listing", "https://parallax.internal/listing-check/100120010005"),
    ("100120010005", "own_wright", S.single_property_owner.value, 0.50, D.slow.value, 60,
     "Owner holds no other title; heirs unlikely to retain and manage.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x5"),

    # ── Site 6 (45 Cotham Hill): EMPTY/VACANT — long_distance_owner + epc + no_listing ──
    ("100120010006", "own_doyle", S.long_distance_owner.value, 0.74, D.slow.value, 45,
     "Registered owner correspondence address in Penzance (~190mi); site held remotely.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x6"),
    ("100120010006", None, S.epc_lapsed.value, 0.66, D.slow.value, 50,
     "EPC expired; no re-lodgement indicating no recent tenancy or sale.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0006-3456"),
    ("100120010006", None, S.no_listing.value, 0.45, D.fast.value, 14,
     "No active listing; vacancy inferred.",
     "listing", "https://parallax.internal/listing-check/100120010006"),

    # ── Site 7 (19 Stackpool Road): EMPTY/VACANT — long_distance + epc + no_listing ──
    ("100120010007", "own_khan", S.long_distance_owner.value, 0.76, D.slow.value, 40,
     "Owner last-known address in Hackney, London; absentee ownership pattern.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x7"),
    ("100120010007", None, S.epc_lapsed.value, 0.64, D.slow.value, 35,
     "EPC lodged 2011, lapsed; no subsequent certificate.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0007-7890"),
    ("100120010007", None, S.no_listing.value, 0.44, D.fast.value, 9,
     "Not currently marketed for sale or rent.",
     "listing", "https://parallax.internal/listing-check/100120010007"),

    # ── Site 9 (5 Henleaze Road): below-market / tired stock ──
    ("100120010009", "own_evans", S.long_hold_unimproved.value, 0.66, D.slow.value, 200,
     "Last sale 2003 at £142k, well below current area trend; no improvement transactions since.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x9"),
    ("100120010009", None, S.epc_fg_refurb.value, 0.62, D.slow.value, 80,
     "EPC band F — refurbishment required to meet MEES; original condition.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0009-2345"),

    # ── Site 10 (33 Coronation Road): tired landlord / portfolio (Oldfield) ──
    ("100120010010", "own_oldfield", S.portfolio_regulatory_pressure.value, 0.60, D.slow.value, 90,
     "Owner holds multiple sub-EPC-E tenanted units; MEES exposure across portfolio.",
     "companies_house", "https://api.company-information.service.gov.uk/company/07412095"),
    ("100120010010", None, S.epc_fg_refurb.value, 0.58, D.slow.value, 75,
     "EPC band G on a let property; non-compliant for continued letting.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0010-6789"),

    # ── Site 13 (58 Stapleton Road): WRONG-USE commercial ──
    ("100120010013", "own_avon", S.commercial_empty.value, 0.78, D.medium.value, 60,
     "VOA list shows unit; rates records consistent with vacancy; shutters down on imagery.",
     "voa", "https://parallax.internal/voa/100120010013"),
    ("100120010013", None, S.wrong_use_gap.value, 0.55, D.slow.value, 100,
     "Retail use-class in a street shifting residential; higher-value conversion latent.",
     "voa", "https://parallax.internal/voa/usecls/100120010013"),
    ("100120010013", None, S.site_activity_decline.value, 0.60, D.medium.value, 45,
     "Footfall/opening-hours proxy declining over 18 months; reviews dwindling.",
     "imagery", "https://parallax.internal/activity/100120010013"),

    # ── Site 15 (41 Church Road): commercial empty (single signal → candidate) ──
    ("100120010015", "own_avon", S.commercial_empty.value, 0.70, D.medium.value, 30,
     "Business rates record shows void; unit empty on latest street imagery.",
     "voa", "https://parallax.internal/voa/100120010015"),

    # ── Site 19 (6 Bishop Road): DISTRESSED FINANCIAL (Brunel SPV) ──
    ("100120010019", "own_brunel", S.owner_spv_distress.value, 0.84, D.medium.value, 50,
     "Companies House: accounts overdue, outstanding charge registered against SPV.",
     "companies_house", "https://api.company-information.service.gov.uk/company/11223344"),
    ("100120010019", None, S.epc_lapsed.value, 0.60, D.slow.value, 70,
     "EPC expired on SPV-held unit; no re-let assessment.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0019-1111"),
    ("100120010019", "own_brunel", S.single_property_owner.value, 0.48, D.slow.value, 70,
     "SPV holds a single title; disposal likely on financial pressure.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x19"),

    # ── Site 23 (51 West Street): development / planning refusal (Redcliffe) ──
    ("100120010023", "own_redcliffe", S.planning_refusal.value, 0.82, D.medium.value, 110,
     "PlanIt: application for change of use REFUSED; owner tried and failed to extract value.",
     "planit", "https://www.planit.org.uk/planapplic/23-00451"),
    ("100120010023", None, S.long_hold_unimproved.value, 0.55, D.slow.value, 180,
     "Held since 2007, no improvement works; plot suitable for redevelopment.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x23"),

    # ── Site 25 (67 Two Mile Hill Road): tired landlord (Oldfield) ──
    ("100120010025", "own_oldfield", S.portfolio_regulatory_pressure.value, 0.56, D.slow.value, 85,
     "Part of a portfolio facing MEES/S24 regulatory burden.",
     "companies_house", "https://api.company-information.service.gov.uk/company/07412095"),
    ("100120010025", None, S.epc_fg_refurb.value, 0.54, D.slow.value, 65,
     "EPC band F; modernisation needed.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0025-2222"),

    # ── Lower-conviction / MONITOR & LOW sites (single weak signals) ──
    ("100120010002", None, S.epc_lapsed.value, 0.52, D.slow.value, 40,
     "EPC expired; awaiting corroboration.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0002-3333"),
    ("100120010004", None, S.no_listing.value, 0.40, D.fast.value, 20,
     "No listing detected (weak signal alone).",
     "listing", "https://parallax.internal/listing-check/100120010004"),
    ("100120010008", None, S.long_hold_unimproved.value, 0.50, D.slow.value, 150,
     "Long hold; no improvement transactions.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x8"),
    ("100120010011", None, S.epc_fg_refurb.value, 0.50, D.slow.value, 90,
     "EPC band F on tenanted unit.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0011-4444"),
    ("100120010012", None, S.no_listing.value, 0.38, D.fast.value, 18,
     "No active listing.",
     "listing", "https://parallax.internal/listing-check/100120010012"),
    ("100120010014", None, S.long_distance_owner.value, 0.42, D.slow.value, 60,
     "Owner address within Bristol but not at site; mild absentee signal.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x14"),
    ("100120010016", None, S.long_hold_unimproved.value, 0.45, D.slow.value, 160,
     "Held 18 years; condition uncertain.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x16"),
    ("100120010017", None, S.epc_lapsed.value, 0.48, D.slow.value, 45,
     "EPC lapsed; single signal.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0017-5555"),
    ("100120010020", None, S.no_listing.value, 0.36, D.fast.value, 22,
     "No listing found.",
     "listing", "https://parallax.internal/listing-check/100120010020"),
    ("100120010021", None, S.epc_fg_refurb.value, 0.46, D.slow.value, 70,
     "EPC band F.",
     "epc", "https://api.get-energy-performance-data.communities.gov.uk/certificate/0021-6666"),
    ("100120010022", None, S.long_distance_owner.value, 0.50, D.slow.value, 55,
     "Owner address in Penzance; absentee.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x22"),
    ("100120010024", None, S.long_hold_unimproved.value, 0.40, D.slow.value, 140,
     "Long hold, detached; weak alone.",
     "hmlr_price_paid", "https://landregistry.data.gov.uk/data/ppi/x24"),
    ("100120010018", None, S.no_listing.value, 0.34, D.fast.value, 25,
     "No listing.",
     "listing", "https://parallax.internal/listing-check/100120010018"),
]


# ─────────────────────────────────────── Upsert helpers ─────────────────────────────────
async def _upsert_site(db: AsyncSession, row: tuple) -> Site:
    uprn, paon, street, postcode, lat, lng, ptype, la = row
    existing = await db.get(Site, uprn)
    address = f"{paon} {street}, Bristol, {postcode}"
    la_name = la or "Bristol City Council"
    if existing:
        existing.address = address
        existing.postcode = postcode
        existing.paon = paon
        existing.lat = lat
        existing.lng = lng
        existing.property_type = ptype
        existing.local_authority = la_name
        existing.resolution_confidence = 0.95
        return existing
    site = Site(
        uprn=uprn,
        address=address,
        postcode=postcode,
        paon=paon,
        lat=lat,
        lng=lng,
        property_type=ptype,
        tenure="freehold" if ptype != "flat" else "leasehold",
        local_authority=la_name,
        resolution_confidence=0.95,
    )
    db.add(site)
    return site


async def _upsert_owner(db: AsyncSession, key: str, row: tuple, id_map: dict[str, str]) -> Owner:
    _, owner_type, display_name, company_number, dob_m, dob_y, addr, pc = row
    # Idempotency: companies match on company_number; individuals on display_name+dob.
    stmt = None
    if owner_type == OwnerType.company.value and company_number:
        stmt = select(Owner).where(Owner.company_number == company_number)
    else:
        stmt = select(Owner).where(
            Owner.display_name == display_name,
            Owner.dob_month == dob_m,
            Owner.dob_year == dob_y,
        )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        id_map[key] = existing.id
        existing.last_known_address = addr
        existing.last_known_postcode = pc
        return existing
    owner = Owner(
        owner_type=owner_type,
        display_name=display_name,
        company_number=company_number,
        dob_month=dob_m,
        dob_year=dob_y,
        last_known_address=addr,
        last_known_postcode=pc,
        data={},
    )
    db.add(owner)
    await db.flush()
    id_map[key] = owner.id
    return owner


async def _upsert_link(db: AsyncSession, site_uprn: str, owner_id: str, role: str, conf: float) -> None:
    stmt = select(OwnershipLink).where(
        OwnershipLink.site_uprn == site_uprn,
        OwnershipLink.owner_id == owner_id,
        OwnershipLink.role == role,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.link_confidence = conf
        existing.is_current = True
        return
    db.add(
        OwnershipLink(
            site_uprn=site_uprn,
            owner_id=owner_id,
            role=role,
            is_current=True,
            source="seed",
            link_confidence=conf,
        )
    )


async def _upsert_signal(db: AsyncSession, row: tuple, id_map: dict[str, str]) -> None:
    site_uprn, owner_key, stype, strength, decay, days_ago, evidence, source, source_ref = row
    owner_id = id_map.get(owner_key) if owner_key else None
    # Idempotency: one signal per (site, type, source_ref).
    stmt = select(Signal).where(
        Signal.site_uprn == site_uprn,
        Signal.signal_type == stype,
        Signal.source_ref == source_ref,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.strength = strength
        existing.raw_evidence = evidence
        existing.owner_id = owner_id
        existing.fired = True
        return
    db.add(
        Signal(
            site_uprn=site_uprn,
            owner_id=owner_id,
            signal_type=stype,
            fired=True,
            strength=strength,
            raw_evidence=evidence,
            source=source,
            source_ref=source_ref,
            observed_at=_days_ago(days_ago),
            decays=decay,
            data={},
        )
    )


async def _upsert_demo_user(db: AsyncSession) -> User:
    stmt = select(User).where(User.email == "demo@parallax.dev")
    user = (await db.execute(stmt)).scalar_one_or_none()
    hashed = _pwd.hash("demo1234")
    if user:
        user.hashed_password = hashed
        user.rung = "pro"
        user.credits_remaining = 50
        return user
    user = User(
        email="demo@parallax.dev",
        hashed_password=hashed,
        display_name="Demo Sourcer",
        rung="pro",
        credits_remaining=50,
    )
    db.add(user)
    await db.flush()
    return user


async def _upsert_demo_patch(db: AsyncSession, user: User) -> None:
    stmt = select(Patch).where(Patch.user_id == user.id, Patch.name == "Bristol patch")
    patch = (await db.execute(stmt)).scalar_one_or_none()
    postcodes = [f"BS{i}" for i in range(1, 9)]
    if patch:
        patch.postcodes = postcodes
        patch.conviction_floor = 31
        return
    db.add(
        Patch(
            user_id=user.id,
            name="Bristol patch",
            postcodes=postcodes,
            buy_box={"min_price": 150000, "max_price": 500000, "types": ["terraced", "semi", "flat"]},
            opportunity_types=["probate_inherited", "empty_vacant", "below_market_tired"],
            conviction_floor=31,
        )
    )


# ─────────────────────────────────────────── seed ──────────────────────────────────────
async def seed(db: AsyncSession) -> dict[str, int]:
    """Idempotent upsert of the full Bristol seed patch. Returns a count summary."""
    log.info("seed_start")

    for row in SITES:
        await _upsert_site(db, row)
    await db.flush()

    id_map: dict[str, str] = {}
    owner_by_key = {o[0]: o for o in OWNERS}
    for key, row in owner_by_key.items():
        await _upsert_owner(db, key, row, id_map)
    await db.flush()

    for site_uprn, owner_key, role, conf in LINKS:
        owner_id = id_map.get(owner_key)
        if owner_id:
            await _upsert_link(db, site_uprn, owner_id, role, conf)

    for row in SIGNALS:
        await _upsert_signal(db, row, id_map)

    user = await _upsert_demo_user(db)
    await db.flush()
    await _upsert_demo_patch(db, user)

    await db.flush()
    summary = {
        "sites": len(SITES),
        "owners": len(OWNERS),
        "links": len(LINKS),
        "signals": len(SIGNALS),
        "users": 1,
        "patches": 1,
    }
    log.info("seed_done", **summary)
    return summary
