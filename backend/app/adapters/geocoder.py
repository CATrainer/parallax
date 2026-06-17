"""Geocoder adapters (§5.2) — address↔UPRN resolution, the spine's hardest problem.

Default is PostcodesIoGeocoder (free, keyless): gives lat/lng for a postcode but no
UPRN, so a deterministic pseudo-UPRN is synthesised when used live. Paid providers are
stubbed. In SEED mode resolve() makes no network call — the seed carries real UPRNs/coords.
Cache writes are the resolution layer's job, not the geocoder's.
"""
from __future__ import annotations

import hashlib

import httpx

from app.adapters.base import GeocodeMatch, Geocoder
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("adapters.geocoder")

_TIMEOUT = httpx.Timeout(10.0)


def _synthetic_uprn(address: str, postcode: str | None) -> str:
    """Deterministic 12-digit pseudo-UPRN from address+postcode.

    Used ONLY for live PostcodesIo matches where no real UPRN is available. Stable so the
    same address always resolves to the same site key. Prefixed '9' to flag it as synthetic.
    """
    key = f"{(address or '').strip().lower()}|{(postcode or '').strip().lower()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    n = int(digest[:15], 16) % 10**11
    return f"9{n:011d}"


class PostcodesIoGeocoder(Geocoder):
    """Free, keyless geocoder via api.postcodes.io. Postcode → lat/lng (no UPRN)."""

    provider = "postcodes_io"
    base_url = "https://api.postcodes.io"

    async def resolve(self, address: str, postcode: str | None = None) -> GeocodeMatch:
        # SEED: no network — the seed already carries UPRNs/coords. Confidence 0.
        if settings.data_mode == "SEED":
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)

        if not postcode:
            log.warning("geocode_no_postcode", provider=self.provider)
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)

        url = f"{self.base_url}/postcodes/{postcode.replace(' ', '').upper()}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("geocode_failed", provider=self.provider, error=str(exc))
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)

        result = (body or {}).get("result") or {}
        lat = result.get("latitude")
        lng = result.get("longitude")
        if lat is None or lng is None:
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)

        # postcodes.io resolves to postcode-centroid only, hence modest confidence.
        return GeocodeMatch(
            uprn=_synthetic_uprn(address, postcode),
            lat=float(lat),
            lng=float(lng),
            match_confidence=0.55,
            provider=self.provider,
        )


class IdealPostcodesGeocoder(Geocoder):
    """Paid UPRN-grade geocoder (ideal-postcodes.co.uk). Stub until key wired."""

    provider = "ideal_postcodes"

    async def resolve(self, address: str, postcode: str | None = None) -> GeocodeMatch:
        if settings.data_mode == "SEED":
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)
        if not settings.ideal_postcodes_api_key:
            raise NotImplementedError("IdealPostcodesGeocoder requires settings.ideal_postcodes_api_key")
        raise NotImplementedError("IdealPostcodesGeocoder live resolution not yet implemented")


class PostcoderGeocoder(Geocoder):
    """Paid UPRN-grade geocoder (postcoder.com). Stub until key wired."""

    provider = "postcoder"

    async def resolve(self, address: str, postcode: str | None = None) -> GeocodeMatch:
        if settings.data_mode == "SEED":
            return GeocodeMatch(uprn=None, lat=None, lng=None, match_confidence=0.0, provider=self.provider)
        if not settings.postcoder_api_key:
            raise NotImplementedError("PostcoderGeocoder requires settings.postcoder_api_key")
        raise NotImplementedError("PostcoderGeocoder live resolution not yet implemented")


_PROVIDERS: dict[str, type[Geocoder]] = {
    "postcodes_io": PostcodesIoGeocoder,
    "ideal_postcodes": IdealPostcodesGeocoder,
    "postcoder": PostcoderGeocoder,
}


def get_geocoder() -> Geocoder:
    """Route to the configured geocoder via settings.geocoder_provider."""
    cls = _PROVIDERS.get(settings.geocoder_provider, PostcodesIoGeocoder)
    return cls()
