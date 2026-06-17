"""Adapter interfaces (§5). Every source is behind an adapter so free→paid swaps are
config, not rewrites. Adapters NEVER infer — they normalise into the raw store."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RawItem:
    """One normalised record headed for the raw store / signal extraction."""

    source: str
    source_ref: str | None
    payload: dict[str, Any]
    source_version: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GeocodeMatch:
    uprn: str | None
    lat: float | None
    lng: float | None
    match_confidence: float
    provider: str


class SourceAdapter(abc.ABC):
    """fetch → normalise; declares its cadence (§5)."""

    name: str = "source"
    cadence: str = "daily"  # daily | weekly | monthly | realtime

    @abc.abstractmethod
    async def fetch(self, **params) -> list[dict[str, Any]]:
        """Pull raw payloads from the source (or seed fixtures in SEED mode)."""

    @abc.abstractmethod
    def normalise(self, raw: dict[str, Any]) -> RawItem:
        """Normalise a raw payload into a RawItem. No inference here."""


class Geocoder(abc.ABC):
    """address↔UPRN resolution (§5.2). Swappable; results cached permanently."""

    provider: str = "geocoder"

    @abc.abstractmethod
    async def resolve(self, address: str, postcode: str | None = None) -> GeocodeMatch:
        ...
