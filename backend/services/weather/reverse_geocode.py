"""
Reverse geocoding: coordinates -> a human place name.

Open-Meteo's geocoding API is forward-only (it has no /reverse endpoint), so a device
position previously had nowhere to resolve to and the UI fell back to the literal string
"My Location". That also weakened disaster-alert targeting for GPS-located users: without
admin1/admin2 there is no state or district to match an alert against.

Provider order matters here. Nominatim is the obvious OSM choice and works fine from a
residential IP, but its usage policy forbids bulk/datacenter use and it returns nothing to
our deployed host — every lookup from production came back empty while the same lookup
from a laptop succeeded. BigDataCloud's reverse-geocode-client endpoint is keyless, built
for per-user volume, and answers from datacenter IPs, so it leads; Nominatim stays as a
fallback for environments where it does work.
"""
import re
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
from backend.schemas.location import LocationResult

# Administrative suffixes that are correct in a database but wrong on a weather card:
# providers return "Chennai Corporation" and "Mundwa Tehsil" where a person says
# "Chennai" and "Mundwa".
_ADMIN_SUFFIXES = re.compile(
    r"\s+(Municipal\s+Corporation|Corporation|Municipality|Municipal\s+Council|"
    r"Nagar\s+Panchayat|Nagar\s+Palika|Tehsil|Taluk|Taluka|Mandal|Block|"
    r"Sub-?District|District|City)$",
    re.IGNORECASE,
)


def _clean_place_name(name: str) -> str:
    cleaned = _ADMIN_SUFFIXES.sub("", (name or "").strip())
    return cleaned.strip(" ,") or (name or "").strip()


class ReverseGeocodeProvider:
    def __init__(self, timeout: Optional[float] = None):
        self.timeout = timeout or settings.REVERSE_GEOCODE_TIMEOUT_SECONDS

    @staticmethod
    def _cache_key(lat: float, lon: float) -> str:
        # ~1.1 km buckets. Finer precision would just miss the cache on GPS jitter while
        # returning the same place name.
        return f"revgeo:{round(lat, 2):.2f}:{round(lon, 2):.2f}"

    # ------------------------------------------------------------------
    # Providers. Each returns (location, provider_answered).
    #
    # The second value separates "the provider replied and this point has no name"
    # from "the provider did not reply". Only the former is a fact worth caching.
    # ------------------------------------------------------------------
    def _normalize_bigdatacloud(self, p: Dict[str, Any], lat: float, lon: float) -> Optional[LocationResult]:
        raw = p.get("city") or p.get("locality") or p.get("principalSubdivision")
        if not raw:
            return None
        code = p.get("countryCode")
        return LocationResult(
            name=_clean_place_name(str(raw)),
            latitude=lat,
            longitude=lon,
            country=p.get("countryName") or None,
            country_code=code.upper() if code else None,
            admin1=p.get("principalSubdivision") or None,
            admin2=self._bdc_admin2(p),
        )

    @staticmethod
    def _bdc_admin2(p: Dict[str, Any]) -> Optional[str]:
        """Most specific administrative level BigDataCloud reports, if any.

        Over open water `administrative` comes back as an empty list, so this cannot
        index blindly -- doing so raised IndexError and turned an unnameable point into
        a 500 instead of a clean null.
        """
        info = p.get("localityInfo")
        if not isinstance(info, dict):
            return None
        levels = info.get("administrative")
        if not isinstance(levels, list) or not levels:
            return None
        last = levels[-1]
        return last.get("name") if isinstance(last, dict) else None

    def _normalize_nominatim(self, p: Dict[str, Any], lat: float, lon: float) -> Optional[LocationResult]:
        a = p.get("address") or {}
        raw = (
            a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
            or a.get("suburb") or a.get("county") or a.get("state_district") or p.get("name")
        )
        if not raw:
            return None
        code = a.get("country_code")
        return LocationResult(
            name=_clean_place_name(str(raw)),
            latitude=lat,
            longitude=lon,
            country=a.get("country"),
            country_code=code.upper() if code else None,
            admin1=a.get("state") or a.get("region"),
            admin2=a.get("state_district") or a.get("county"),
        )

    async def _fetch(self, url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        try:
            client = await http_client_manager.get_client()
            response = await client.get(
                url, params=params, headers=headers, timeout=self.timeout, follow_redirects=True
            )
        except Exception as e:
            logger.warning(f"[Reverse geocode] {url} unreachable: {e}")
            return None
        if response.status_code != 200:
            logger.warning(f"[Reverse geocode] {url} HTTP {response.status_code}")
            return None
        try:
            return response.json()
        except Exception:
            logger.warning(f"[Reverse geocode] {url} returned malformed JSON")
            return None

    async def _try_providers(self, lat: float, lon: float) -> Tuple[Optional[LocationResult], bool]:
        payload = await self._fetch(
            settings.BIGDATACLOUD_REVERSE_URL,
            {"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            {"Accept": "application/json"},
        )
        if payload is not None:
            return self._normalize_bigdatacloud(payload, lat, lon), True

        payload = await self._fetch(
            settings.NOMINATIM_REVERSE_URL,
            {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "addressdetails": 1},
            {"User-Agent": settings.REVERSE_GEOCODE_USER_AGENT},
        )
        if payload is not None:
            return self._normalize_nominatim(payload, lat, lon), True

        return None, False

    async def reverse(self, lat: float, lon: float) -> Optional[LocationResult]:
        key = self._cache_key(lat, lon)
        cached = await cache.get(key)
        if cached is not None:
            logger.debug(f"[Cache HIT] reverse geocode ({lat:.2f},{lon:.2f})")
            return LocationResult(**cached) if cached else None

        resolved, answered = await self._try_providers(lat, lon)

        if not answered:
            # Every provider failed. Returning None is right for this request, but caching
            # it is not: a transient outage or a rate-limit would otherwise pin this
            # coordinate to "unnameable" for the whole TTL. Retry on the next request.
            logger.warning(f"[Reverse geocode] all providers failed for ({lat:.2f},{lon:.2f}); not caching")
            return None

        # A provider answered. Place names do not move, so a hit is cached for a long
        # time; a genuine "nowhere" (open ocean) is cached briefly, since it is a real
        # answer but a cheap one to re-check.
        await cache.set(
            key,
            resolved.dict() if resolved else None,
            ttl_seconds=(
                settings.REVERSE_GEOCODE_CACHE_TTL_SECONDS if resolved
                else settings.REVERSE_GEOCODE_EMPTY_CACHE_TTL_SECONDS
            ),
        )
        return resolved


reverse_geocode_provider = ReverseGeocodeProvider()
