"""Adapter registry — name → instance for every bulk SourceAdapter (§5).

The Celery ingest task and the resolution layer look adapters up by name here. Validation-tier
pullers (HmlrTitleAdapter) are not bulk sources and are NOT registered.
"""
from __future__ import annotations

from app.adapters.base import SourceAdapter
from app.adapters.companies_house import CompaniesHouseAdapter
from app.adapters.epc import EpcAdapter
from app.adapters.gazette import GazetteDeceasedAdapter, GazetteInsolvencyAdapter
from app.adapters.hmlr import HmlrPricePaidAdapter
from app.adapters.planning import PlanItAdapter

ADAPTERS: dict[str, SourceAdapter] = {
    a.name: a
    for a in (
        CompaniesHouseAdapter(),
        GazetteDeceasedAdapter(),
        GazetteInsolvencyAdapter(),
        EpcAdapter(),
        HmlrPricePaidAdapter(),
        PlanItAdapter(),
    )
}


def get_adapter(name: str) -> SourceAdapter:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise KeyError(f"No adapter registered for source '{name}'") from exc
