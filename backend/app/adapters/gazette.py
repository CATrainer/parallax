"""The Gazette adapters (§5.1) — deceased estates (probate/inherited signal) and
insolvency (financial-distress signal). Free OGL JSON listing API at
thegazette.co.uk/all-notices/notice/data.json. Honour the 10s crawl-delay between pulls.
SEED → []; the seed carries Gazette-derived signals.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.gazette")

_TIMEOUT = httpx.Timeout(20.0)
_DATA_URL = "https://www.thegazette.co.uk/all-notices/notice/data.json"
# Crawl-delay: the Gazette robots policy asks for a 10s gap between requests.
_CRAWL_DELAY_S = 10.0


class _GazetteBase(SourceAdapter):
    """Shared fetch/normalise over the Gazette notice listing API."""

    notice_code: str = ""  # filter (e.g. G205000001 deceased estates) — set by subclass
    cadence = "daily"

    async def fetch(self, **params) -> list[dict[str, Any]]:
        if settings.data_mode == "SEED":
            return []

        query: dict[str, Any] = {"results-page-size": params.get("page_size", 50)}
        if self.notice_code:
            query["noticetypes"] = self.notice_code
        if params.get("start"):
            query["start-publish-date"] = params["start"]

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_DATA_URL, params=query)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("gazette_fetch_failed", adapter=self.name, error=str(exc))
            return []
        finally:
            # Be a good citizen — honour the crawl delay before the next pull.
            await asyncio.sleep(_CRAWL_DELAY_S)

        entries = (body or {}).get("entry") or []
        return entries if isinstance(entries, list) else [entries]


class GazetteDeceasedAdapter(_GazetteBase):
    name = "gazette_deceased"
    notice_code = "G205000000"  # Deceased estates (Trustee Act / s.27)

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        # Detail fields may live on the entry directly or under an extracted block.
        deceased = raw.get("deceased") or {}
        payload = {
            "notice_id": raw.get("id"),
            "title": raw.get("title"),
            "deceased_name": deceased.get("name") or raw.get("deceased_name"),
            "last_address": deceased.get("address") or raw.get("last_address"),
            "date_of_death": deceased.get("date_of_death") or raw.get("date_of_death"),
            "executor": raw.get("executor") or raw.get("personalRepresentative"),
            "publication_date": raw.get("publication-date") or raw.get("updated"),
        }
        return RawItem(
            source=self.name,
            source_ref=raw.get("link") or raw.get("id"),
            payload=payload,
        )


class GazetteInsolvencyAdapter(_GazetteBase):
    name = "gazette_insolvency"
    notice_code = "G24000000"  # Insolvency / corporate insolvency

    def normalise(self, raw: dict[str, Any]) -> RawItem:
        payload = {
            "notice_id": raw.get("id"),
            "title": raw.get("title"),
            "subject_name": raw.get("subject_name") or raw.get("company_name"),
            "company_number": raw.get("company_number"),
            "address": raw.get("address"),
            "publication_date": raw.get("publication-date") or raw.get("updated"),
            "notice_type": raw.get("notice_type"),
        }
        return RawItem(
            source=self.name,
            source_ref=raw.get("link") or raw.get("id"),
            payload=payload,
        )
