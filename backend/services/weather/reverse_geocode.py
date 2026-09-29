"""
Reverse geocoding: coordinates -> a human place name.

Open-Meteo's geocoding API is forward-only (it has no /reverse endpoint), so a device
position previously had nowhere to resolve to and the UI fell back to the literal string
"My Location". That is also why a GPS-located user got weaker disaster-alert targeting:
without admin1/admin2 there is no state or district to match an alert against.

This runs server-side rather than in the browser for two reasons: Nominatim requires a
descriptive User-Agent, which a browser will not let a page set, and its usage policy
caps requests at roughly one per second, which is only enforceable behind a shared cache.
"""
import re
from typing import Any, Dict, Optional

import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
from backend.schemas.location import LocationResult

# Administrative suffixes that are correct in a database but wrong on a weather card:
# Nominatim returns "Chennai Corporation" and "Mundwa Tehsil" where a person says
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
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.NOMINATIM_REVERSE_URL
        self.timeout = timeout or settings.REVERSE_GEOCODE_TIMEOUT_SECONDS

    @staticmethod
    def _cache_key(lat: float, lon: float) -> str:
        # ~1.1 km buckets. Finer precision would just miss the cache for every small
        # GPS jitter while returning the same place name.
        return f"revgeo:{round(lat, 2):.2f}:{round(lon, 2):.2f}"

    def normalize(self, payload: Dict[str, Any], lat: float, lon: float) -> Optional[LocationResult]:
        """Maps a Nominatim response onto LocationResult, or None if it names nowhere."""
        address = payload.get("address") or {}

        raw_name = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("suburb")
            or address.get("county")
            or address.get("state_district")
            or payload.get("name")
        )
        if not raw_name:
            # Open ocean, or a point Nominatim cannot place. Better to keep the caller's
            # fallback than to invent a name.
            return None

        country_code = address.get("country_code")
        return LocationResult(
            name=_clean_place_name(str(raw_name)),
            latitude=lat,
            longitude=lon,
            country=address.get("country"),
            country_code=country_code.upper() if country_code else None,
            admin1=address.get("state") or address.get("region"),
            admin2=address.get("state_district") or address.get("county"),
        )

    async def reverse(self, lat: float, lon: float) -> Optional[LocationResult]:
        key = self._cache_key(lat, lon)
        cached = await cache.get(key)
        if cached is not None:
            logger.debug(f"[Cache HIT] reverse geocode ({lat:.2f},{lon:.2f})")
            return LocationResult(**cached) if cached else None

        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 10,          # settlement level: city/town/village rather than a street
            "addressdetails": 1,
        }
        headers = {"User-Agent": settings.REVERSE_GEOCODE_USER_AGENT}

        try:
            client = await http_client_manager.get_client()
            response = await client.get(
                self.base_url, params=params, headers=headers, timeout=self.timeout
            )
        except httpx.TimeoutException:
            logger.warning(f"[Reverse geocode timeout] ({lat:.2f},{lon:.2f})")
            return None
        except Exception as e:
            logger.warning(f"[Reverse geocode error] ({lat:.2f},{lon:.2f}): {e}")
            return None

        if response.status_code != 200:
            logger.warning(f"[Reverse geocode HTTP {response.status_code}] ({lat:.2f},{lon:.2f})")
            return None

        try:
            payload = response.json()
        except Exception:
            logger.warning(f"[Reverse geocode malformed JSON] ({lat:.2f},{lon:.2f})")
            return None

        resolved = self.normalize(payload, lat, lon)

        # Place names do not move, so this is cached for a long time. A negative result is
        # cached too, so an ocean tap does not re-hit the provider on every page load.
        await cache.set(
            key,
            resolved.dict() if resolved else None,
            ttl_seconds=settings.REVERSE_GEOCODE_CACHE_TTL_SECONDS,
        )
        return resolved


reverse_geocode_provider = ReverseGeocodeProvider()
