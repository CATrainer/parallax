"""EPC register adapter (§5.1) — vacancy inference (lapsed/old EPC), refurb-need (F/G),
floor area, attributes.

New MHCLG service: ``api.get-energy-performance-data.communities.gov.uk`` (the old
opendatacommunities endpoint retired 30 May 2026). Auth is a **Bearer token** (from the
service's "My account → Bearer token (for developers)"). Search path is ``/api/domestic/search``
and the response is ``{data: [...], pagination: {...}}``. SEED → []; the seed carries EPC signals.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.epc")

_TIMEOUT = httpx.Timeout(20.0)
_BASE = "https://api.get-energy-performance-data.communities.gov.uk"


class EpcAdapter(SourceAdapter):
    name = "epc"
    cadence = "monthly"

    @staticmethod
    def _bearer() -> str:
        """The developer Bearer token (EPC_AUTH_TOKEN, or EPC_API_KEY as a fallback name)."""
        return (settings.epc_auth_token or settings.epc_api_key).strip()

    async def fetch(self, **params) -> list[dict[str, Any]]:
        if settings.data_mode == "SEED":
            return []

        token = self._bearer()
        if not token:
            raise NotImplementedError("EpcAdapter requires EPC_AUTH_TOKEN (the Bearer token)")

        query: dict[str, Any] = {"size": params.get("size", 100)}
        if params.get("postcode"):
            query["postcode"] = params["postcode"]
        if params.get("local_authority"):
            query["council"] = params["local_authority"]

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
                resp = await client.get(f"{_BASE}/api/domestic/search", params=query)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("epc_fetch_failed", error=str(exc))
            return []

        rows = (body or {}).get("data") or []
        return rows if isinstance(rows, list) else [rows]

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        # Search results are summaries (camelCase); full attributes (floor area, potential
        # rating) come from the certificate detail endpoint keyed by certificateNumber.
        addr_parts = [
            raw.get("addressLine1"),
            raw.get("addressLine2"),
            raw.get("addressLine3"),
            raw.get("addressLine4"),
        ]
        address = ", ".join(p for p in addr_parts if p)
        cert = raw.get("certificateNumber") or raw.get("lmk-key") or raw.get("lmk_key")
        payload = {
            "uprn": raw.get("uprn"),
            "address": address or None,
            "postcode": raw.get("postcode"),
            "current_energy_rating": (
                raw.get("currentEnergyEfficiencyBand")
                or raw.get("current-energy-rating")
                or raw.get("current_energy_rating")
            ),
            "potential_energy_rating": raw.get("potentialEnergyEfficiencyBand"),
            "lodgement_date": raw.get("registrationDate") or raw.get("lodgement-date"),
            "total_floor_area": raw.get("totalFloorArea"),
            "property_type": raw.get("propertyType") or raw.get("schemaType"),
            "local_authority": raw.get("council"),
            "lmk_key": cert,
        }
        return RawItem(
            source=self.name,
            source_ref=f"{_BASE}/api/domestic/certificate/{cert}" if cert else None,
            payload=payload,
        )
