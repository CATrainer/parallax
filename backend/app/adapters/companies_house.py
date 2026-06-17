"""Companies House adapter (§5.1) — distress (late filings, charges, insolvency),
portfolios (SPVs), beneficial owners (PSC name + DOB). Free REST API, basic-auth with the
API key as username. Honour 600 req / 5 min. SEED → []; the seed carries CH-derived signals.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.companies_house")

_TIMEOUT = httpx.Timeout(15.0)
_BASE = "https://api.company-information.service.gov.uk"

# 600 req / 5 min ⇒ one request every ~0.5s is comfortably under the ceiling.
_MIN_INTERVAL_S = 0.5


class CompaniesHouseAdapter(SourceAdapter):
    name = "companies_house"
    cadence = "realtime"

    def __init__(self) -> None:
        self._last_call = 0.0

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_INTERVAL_S:
            await asyncio.sleep(_MIN_INTERVAL_S - elapsed)
        self._last_call = time.monotonic()

    async def _get(self, path: str) -> dict[str, Any]:
        if not settings.companies_house_api_key:
            raise NotImplementedError("CompaniesHouseAdapter requires settings.companies_house_api_key")
        await self._throttle()
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, auth=(settings.companies_house_api_key, "")
            ) as client:
                resp = await client.get(f"{_BASE}{path}")
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("ch_request_failed", path=path, error=str(exc))
            return {}

    async def fetch_company(self, number: str) -> dict[str, Any]:
        """Company profile (status, filings cadence, charges flag)."""
        return await self._get(f"/company/{number}")

    async def fetch_officers(self, number: str) -> dict[str, Any]:
        """Officers list (directors) for portfolio / owner-link resolution."""
        return await self._get(f"/company/{number}/officers")

    async def fetch(self, **params) -> list[dict[str, Any]]:
        # SEED: seed supplies CH-derived signals directly.
        if settings.data_mode == "SEED":
            return []
        number = params.get("number") or params.get("company_number")
        if not number:
            log.warning("ch_fetch_no_number")
            return []
        profile = await self.fetch_company(number)
        return [profile] if profile else []

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        number = raw.get("company_number") or raw.get("company_number".upper())
        accounts = (raw.get("accounts") or {}).get("next_accounts") or {}
        payload = {
            "company_number": number,
            "company_status": raw.get("company_status"),
            "company_name": raw.get("company_name"),
            "type": raw.get("type"),
            "date_of_creation": raw.get("date_of_creation"),
            "has_charges": raw.get("has_charges"),
            "has_insolvency_history": raw.get("has_insolvency_history"),
            "accounts_overdue": accounts.get("overdue"),
            "accounts_due_on": accounts.get("due_on"),
            "registered_office_address": raw.get("registered_office_address"),
            "officers": raw.get("officers") or raw.get("items"),
        }
        return RawItem(
            source=self.name,
            source_ref=f"{_BASE}/company/{number}" if number else None,
            payload=payload,
            source_version=raw.get("etag"),
        )
