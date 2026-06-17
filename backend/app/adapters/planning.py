"""PlanIt adapter (§5.1) — planning applications + decisions incl. refusals & appeals
(the `planning_refusal` motivation signal). Free community API at planit.org.uk, ~420 LAs.
SEED → []; the seed carries planning-derived signals.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.planning")

_TIMEOUT = httpx.Timeout(20.0)
_BASE = "https://www.planit.org.uk/api/applics/json"


class PlanItAdapter(SourceAdapter):
    name = "planit"
    cadence = "frequent"

    async def fetch(self, **params) -> list[dict[str, Any]]:
        if settings.data_mode == "SEED":
            return []

        query: dict[str, Any] = {"pg_sz": params.get("page_size", 50), "sort": "-start_date"}
        if params.get("postcode"):
            query["search"] = params["postcode"]
        if params.get("lat") is not None and params.get("lng") is not None:
            query["lat"] = params["lat"]
            query["lng"] = params["lng"]
            query["krad"] = params.get("radius_km", 2)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE, params=query)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("planit_fetch_failed", error=str(exc))
            return []

        records = (body or {}).get("records") or []
        return records if isinstance(records, list) else [records]

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        payload = {
            "reference": raw.get("reference") or raw.get("name"),
            "authority": raw.get("authority") or raw.get("area_name"),
            "address": raw.get("address"),
            "postcode": raw.get("postcode"),
            "description": raw.get("description"),
            "app_type": raw.get("app_type"),
            "app_state": raw.get("app_state"),  # e.g. Refused, Permitted, Withdrawn
            "decision": raw.get("decision"),
            "is_refusal": (raw.get("app_state") or "").lower() in {"refused", "rejected"},
            "is_appeal": "appeal" in (raw.get("app_type") or "").lower(),
            "start_date": raw.get("start_date"),
            "decided_date": raw.get("decided_date"),
            "url": raw.get("url"),
            "uprn": raw.get("uprn"),
        }
        return RawItem(
            source=self.name,
            source_ref=raw.get("url") or raw.get("reference"),
            payload=payload,
        )
