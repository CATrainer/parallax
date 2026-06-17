"""Canonical entities — the entity-resolution spine (§6.1) and everything attached.

UPRN is the canonical site key (§3.3). Ownership links are probabilistic and scored,
never hard assertions (§6.1).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ─────────────────────────────────────────── Site ───────────────────────────────────────────
class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    uprn: Mapped[str] = mapped_column(String(20), primary_key=True)
    address: Mapped[str] = mapped_column(Text)
    postcode: Mapped[str | None] = mapped_column(String(12), index=True)
    paon: Mapped[str | None] = mapped_column(String(120))
    saon: Mapped[str | None] = mapped_column(String(120))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(40))
    tenure: Mapped[str | None] = mapped_column(String(40))
    local_authority: Mapped[str | None] = mapped_column(String(120), index=True)
    resolution_confidence: Mapped[float] = mapped_column(Float, default=1.0)

    signals: Mapped[list["Signal"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    ownership_links: Mapped[list["OwnershipLink"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    briefings: Mapped[list["Briefing"]] = relationship(back_populates="site", cascade="all, delete-orphan")


# ─────────────────────────────────────────── Owner ──────────────────────────────────────────
class Owner(Base, TimestampMixin):
    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_type: Mapped[str] = mapped_column(String(20))  # OwnerType
    display_name: Mapped[str] = mapped_column(Text)  # PII — never log
    company_number: Mapped[str | None] = mapped_column(String(20), index=True)
    dob_month: Mapped[int | None] = mapped_column(Integer)
    dob_year: Mapped[int | None] = mapped_column(Integer)
    last_known_address: Mapped[str | None] = mapped_column(Text)
    last_known_postcode: Mapped[str | None] = mapped_column(String(12))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    ownership_links: Mapped[list["OwnershipLink"]] = relationship(back_populates="owner")


# ─────────────────────────────────── OwnershipLink (probabilistic) ──────────────────────────
class OwnershipLink(Base, TimestampMixin):
    __tablename__ = "ownership_links"
    __table_args__ = (UniqueConstraint("site_uprn", "owner_id", "role", name="uq_ownership"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_uprn: Mapped[str] = mapped_column(ForeignKey("sites.uprn", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # OwnershipRole
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(60))
    link_confidence: Mapped[float] = mapped_column(Float, default=0.5)

    site: Mapped["Site"] = relationship(back_populates="ownership_links")
    owner: Mapped["Owner"] = relationship(back_populates="ownership_links")


# ─────────────────────────────────────────── Signal ─────────────────────────────────────────
class Signal(Base, TimestampMixin):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_uprn: Mapped[str] = mapped_column(ForeignKey("sites.uprn", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"))
    signal_type: Mapped[str] = mapped_column(String(40), index=True)  # SignalType
    fired: Mapped[bool] = mapped_column(Boolean, default=True)
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    raw_evidence: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60))
    source_ref: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decays: Mapped[str] = mapped_column(String(10), default="slow")  # Decay
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    site: Mapped["Site"] = relationship(back_populates="signals")


# ─────────────────────────────────────────── Briefing ───────────────────────────────────────
class Briefing(Base, TimestampMixin):
    __tablename__ = "briefings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_uprn: Mapped[str] = mapped_column(ForeignKey("sites.uprn", ondelete="CASCADE"), index=True)
    lede: Mapped[str] = mapped_column(Text)
    paragraphs: Mapped[list] = mapped_column(JSONB, default=list)  # [{text, cited_signal_ids}]
    takeaway: Mapped[str] = mapped_column(Text)
    conclusions: Mapped[list] = mapped_column(JSONB, default=list)  # [{type,statement,confidence,...}]
    conviction: Mapped[int] = mapped_column(Integer, default=0, index=True)
    band: Mapped[str] = mapped_column(String(10), index=True)  # Band
    opportunity_types: Mapped[list] = mapped_column(JSONB, default=list)
    headline_opportunity: Mapped[str | None] = mapped_column(String(40))
    signal_ids: Mapped[list] = mapped_column(JSONB, default=list)
    synthesis_model: Mapped[str | None] = mapped_column(String(60))
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    site: Mapped["Site"] = relationship(back_populates="briefings")


# ─────────────────────────────────────────── Validation ─────────────────────────────────────
class Validation(Base, TimestampMixin):
    __tablename__ = "validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_uprn: Mapped[str] = mapped_column(ForeignKey("sites.uprn", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # ValidationStatus
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_ownership: Mapped[dict | None] = mapped_column(JSONB)
    occupancy_status: Mapped[str | None] = mapped_column(String(200))
    contact_route: Mapped[dict | None] = mapped_column(JSONB)
    updated_conviction: Mapped[int | None] = mapped_column(Integer)
    provenance_log: Mapped[list] = mapped_column(JSONB, default=list)  # [{check, source, cost, result}]
    error: Mapped[str | None] = mapped_column(Text)


# ─────────────────────────────────────────── User ───────────────────────────────────────────
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    rung: Mapped[str] = mapped_column(String(20), default="entry")  # PlanRung
    credits_remaining: Mapped[int] = mapped_column(Integer, default=10)
    deep_dives_used: Mapped[int] = mapped_column(Integer, default=0)
    is_broker: Mapped[bool] = mapped_column(Boolean, default=False)

    patches: Mapped[list["Patch"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ─────────────────────────────────────────── Patch ──────────────────────────────────────────
class Patch(Base, TimestampMixin):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="My patch")
    postcodes: Mapped[list] = mapped_column(JSONB, default=list)  # ["BS1", "BS2", ...]
    buy_box: Mapped[dict] = mapped_column(JSONB, default=dict)  # {min_price, max_price, types:[...]}
    opportunity_types: Mapped[list] = mapped_column(JSONB, default=list)
    conviction_floor: Mapped[int] = mapped_column(Integer, default=31)  # MONITOR

    user: Mapped["User"] = relationship(back_populates="patches")


# ─────────────────────────────────────────── Watchlist ──────────────────────────────────────
class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "site_uprn", name="uq_watch"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    site_uprn: Mapped[str] = mapped_column(ForeignKey("sites.uprn", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="watching")  # WatchStatus
    note: Mapped[str | None] = mapped_column(Text)


# ─────────────────────────────────── Raw store + geocode cache ──────────────────────────────
class RawRecord(Base, TimestampMixin):
    """L1 raw store: source payload + fetch timestamp + version, for provenance (§5.6)."""

    __tablename__ = "raw_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(60), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_version: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class GeocodeCache(Base, TimestampMixin):
    """Permanent cache of address→UPRN resolutions — pay once per unique address (§5.2)."""

    __tablename__ = "geocode_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    address_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    uprn: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(40))
