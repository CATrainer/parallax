"""Domain response/request models — the typed API contract the frontend builds against."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────── Signals ───────────────────────────────
class SignalOut(BaseModel):
    id: str
    signal_type: str
    fired: bool
    strength: float
    raw_evidence: str
    source: str
    source_ref: Optional[str] = None
    observed_at: datetime
    decays: str

    class Config:
        from_attributes = True


# ─────────────────────────────── Ownership ───────────────────────────────
class OwnerOut(BaseModel):
    id: str
    owner_type: str
    display_name: str
    company_number: Optional[str] = None

    class Config:
        from_attributes = True


class OwnershipLinkOut(BaseModel):
    id: str
    role: str
    is_current: bool
    source: str
    link_confidence: float
    owner: OwnerOut

    class Config:
        from_attributes = True


# ─────────────────────────────── Site ───────────────────────────────
class SiteOut(BaseModel):
    uprn: str
    address: str
    postcode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    property_type: Optional[str] = None
    tenure: Optional[str] = None
    local_authority: Optional[str] = None
    resolution_confidence: float

    class Config:
        from_attributes = True


class SiteDetail(SiteOut):
    ownership: list[OwnershipLinkOut] = []
    signals: list[SignalOut] = []
    headline_conviction: Optional[int] = None
    headline_band: Optional[str] = None


# ─────────────────────────────── Briefing ───────────────────────────────
class BriefingParagraph(BaseModel):
    text: str
    cited_signal_ids: list[str] = []


class Conclusion(BaseModel):
    type: str
    statement: str
    confidence: float
    contributing_signal_ids: list[str] = []


class BriefingOut(BaseModel):
    id: str
    site_uprn: str
    lede: str
    paragraphs: list[BriefingParagraph]
    takeaway: str
    conclusions: list[Conclusion]
    conviction: int
    band: str
    opportunity_types: list[str]
    headline_opportunity: Optional[str] = None
    signals: list[SignalOut] = []
    ownership: list[OwnershipLinkOut] = []
    site: SiteOut
    synthesis_model: Optional[str] = None
    is_stale: bool = False
    computed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BriefingCard(BaseModel):
    """Compact card for the patch feed / search results."""

    id: str
    site_uprn: str
    address: str
    postcode: Optional[str] = None
    lede: str
    conviction: int
    band: str
    headline_opportunity: Optional[str] = None
    opportunity_types: list[str] = []
    signal_count: int = 0
    updated_at: Optional[datetime] = None


# ─────────────────────────────── Validation ───────────────────────────────
class ProvenanceEntry(BaseModel):
    check: str
    source: str
    cost_credits: int
    result: str


class ValidationOut(BaseModel):
    id: str
    site_uprn: str
    status: str
    credits_spent: int
    confirmed_ownership: Optional[dict] = None
    occupancy_status: Optional[str] = None
    contact_route: Optional[dict] = None
    updated_conviction: Optional[int] = None
    provenance_log: list[ProvenanceEntry] = []
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ValidationJob(BaseModel):
    id: str
    status: str
    credits_remaining: int


# ─────────────────────────────── Patch ───────────────────────────────
class BuyBox(BaseModel):
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    property_types: list[str] = []


class PatchIn(BaseModel):
    name: str = "My patch"
    postcodes: list[str] = []
    buy_box: BuyBox = Field(default_factory=BuyBox)
    opportunity_types: list[str] = []
    conviction_floor: int = 31


class PatchOut(PatchIn):
    id: str

    class Config:
        from_attributes = True


# ─────────────────────────────── Watchlist / status ───────────────────────────────
class WatchlistIn(BaseModel):
    site_uprn: str
    status: Literal["pursuing", "watching", "dead"] = "watching"
    note: Optional[str] = None


class WatchlistOut(BaseModel):
    id: str
    site_uprn: str
    status: str
    note: Optional[str] = None
    address: Optional[str] = None
    conviction: Optional[int] = None
    band: Optional[str] = None

    class Config:
        from_attributes = True


class StatusIn(BaseModel):
    status: Literal["pursuing", "dead"]


# ─────────────────────────────── Usage / auth ───────────────────────────────
class UsageOut(BaseModel):
    rung: str
    credits_remaining: int
    deep_dives_used: int


class SearchResult(BaseModel):
    kind: Literal["site", "company", "person"]
    uprn: Optional[str] = None
    label: str
    sublabel: Optional[str] = None
    conviction: Optional[int] = None
    band: Optional[str] = None


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rung: str
    is_broker: bool = False


# ─────────────────────────────── Broker (Product 2, §11) ───────────────────────────────
class BrokerEnrichRow(BaseModel):
    input_address: str
    uprn: Optional[str] = None
    resolved_address: Optional[str] = None
    transaction_likelihood: int  # 0-100
    band: str
    rationale: str
    signal_summary: list[str] = []


class BrokerEnrichOut(BaseModel):
    rows: list[BrokerEnrichRow]
    total: int


class BrokerIntelligenceOut(BaseModel):
    site: SiteOut
    owner_situation: str
    mortgage_event_likelihood: int
    band: str
    drivers: list[str]
    ownership: list[OwnershipLinkOut] = []
