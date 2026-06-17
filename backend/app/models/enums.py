"""Enumerations shared across the engine."""
from __future__ import annotations

import enum


class OwnerType(str, enum.Enum):
    individual = "individual"
    company = "company"


class OwnershipRole(str, enum.Enum):
    proprietor = "proprietor"
    executor = "executor"
    psc = "psc"
    director = "director"


class Decay(str, enum.Enum):
    slow = "slow"
    medium = "medium"
    fast = "fast"


class Band(str, enum.Enum):
    LOW = "LOW"
    MONITOR = "MONITOR"
    LIKELY = "LIKELY"
    STRONG = "STRONG"


class OpportunityType(str, enum.Enum):
    empty_vacant = "empty_vacant"
    probate_inherited = "probate_inherited"
    distressed_financial = "distressed_financial"
    distressed_life = "distressed_life"
    below_market_tired = "below_market_tired"
    development_planning = "development_planning"
    tired_landlord = "tired_landlord"
    wrong_use_commercial = "wrong_use_commercial"


class SignalType(str, enum.Enum):
    probate_inherited = "probate_inherited"
    epc_lapsed = "epc_lapsed"
    epc_fg_refurb = "epc_fg_refurb"
    no_listing = "no_listing"
    owner_spv_distress = "owner_spv_distress"
    long_hold_unimproved = "long_hold_unimproved"
    planning_refusal = "planning_refusal"
    commercial_empty = "commercial_empty"
    wrong_use_gap = "wrong_use_gap"
    site_activity_decline = "site_activity_decline"
    long_distance_owner = "long_distance_owner"
    portfolio_regulatory_pressure = "portfolio_regulatory_pressure"
    single_property_owner = "single_property_owner"


class WatchStatus(str, enum.Enum):
    pursuing = "pursuing"
    watching = "watching"
    dead = "dead"


class ValidationStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class PlanRung(str, enum.Enum):
    entry = "entry"
    sourcer = "sourcer"
    pro = "pro"
    broker = "broker"


def band_for(score: int) -> Band:
    """LOCKED band cutoffs (§6.4)."""
    if score <= 30:
        return Band.LOW
    if score <= 55:
        return Band.MONITOR
    if score <= 80:
        return Band.LIKELY
    return Band.STRONG
