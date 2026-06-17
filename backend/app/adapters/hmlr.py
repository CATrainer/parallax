"""HM Land Registry adapters (§5.1, §5.3, §6.4).

- HmlrPricePaidAdapter — free monthly Price Paid Data; sale history, hold length,
  below-market, BTL/repossession context. SEED → [].
- HmlrTitleAdapter — the per-title (~£3) *actual current owner* pull, used in the
  validation tier only (not bulk). In SEED mode title_pull() returns a fixture-shaped
  confirmed-owner result; LIVE is stubbed pending Business Gateway credentials.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.hmlr")

_TIMEOUT = httpx.Timeout(30.0)
_PPD_BASE = "https://landregistry.data.gov.uk"


class HmlrPricePaidAdapter(SourceAdapter):
    name = "hmlr_price_paid"
    cadence = "monthly"

    async def fetch(self, **params) -> list[dict[str, Any]]:
        if settings.data_mode == "SEED":
            return []

        query = {"_pageSize": params.get("page_size", 50)}
        if params.get("postcode"):
            query["postcode"] = params["postcode"]
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_PPD_BASE}/data/ppi/transaction-record.json", params=query
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("hmlr_ppd_fetch_failed", error=str(exc))
            return []

        items = (body or {}).get("result", {}).get("items") or []
        return items if isinstance(items, list) else [items]

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        addr = raw.get("propertyAddress") or {}
        payload = {
            "transaction_id": raw.get("transactionId"),
            "price_paid": raw.get("pricePaid"),
            "transaction_date": raw.get("transactionDate"),
            "property_type": raw.get("propertyType"),
            "new_build": raw.get("newBuild"),
            "estate_type": raw.get("estateType"),
            "postcode": addr.get("postcode"),
            "paon": addr.get("paon"),
            "saon": addr.get("saon"),
            "street": addr.get("street"),
            "town": addr.get("town"),
        }
        return RawItem(
            source=self.name,
            source_ref=raw.get("transactionId") or raw.get("_about"),
            payload=payload,
        )


class HmlrTitleAdapter:
    """Validation-tier title pull (~£3 per title). Not a bulk SourceAdapter — invoked
    on demand inside the validation flow to confirm true current ownership."""

    name = "hmlr_title"

    async def title_pull(self, uprn_or_title: str) -> dict[str, Any]:
        """Return a confirmed-owner result for a single title.

        SEED → a deterministic fixture shaped like a real title register extract.
        LIVE → stubbed (requires Business Gateway credentials).
        """
        if settings.data_mode == "SEED":
            return {
                "uprn_or_title": uprn_or_title,
                "title_number": f"BST{abs(hash(uprn_or_title)) % 900000 + 100000}",
                "tenure": "Freehold",
                "confirmed": True,
                "proprietors": [
                    {
                        "name": "[confirmed proprietor]",
                        "proprietor_type": "private_individual",
                        "address": "[registered correspondence address]",
                    }
                ],
                "price_stated": None,
                "registered_date": date(2009, 4, 14).isoformat(),
                "restrictions": [],
                "source": self.name,
                "source_ref": f"hmlr-title:{uprn_or_title}",
            }

        if not settings.hmlr_api_key:
            raise NotImplementedError("HmlrTitleAdapter live title pull requires settings.hmlr_api_key")
        raise NotImplementedError("HmlrTitleAdapter live title pull not yet implemented")
