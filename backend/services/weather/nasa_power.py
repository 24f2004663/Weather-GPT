from datetime import datetime
from typing import Dict, Any, Optional, List
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
from backend.core.errors import (
    UpstreamProviderError,
    UpstreamTimeoutError,
    InvalidCoordinatesError,
)
from backend.schemas.location import LocationResult
from backend.schemas.climate import NasaPowerClimateResponse, MonthlyClimateMetric

MONTH_KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

PARAMETER_DESCRIPTIONS = {
    "T2M": "Temperature at 2 Meters (°C)",
    "PRECTOTCORR": "Precipitation Corrected (mm/day)",
    "ALLSKY_SFC_SW_DWN": "All Sky Surface Solar Irradiance (kW-hr/m²/day)",
    "RH2M": "Relative Humidity at 2 Meters (%)",
    "WS10M": "Wind Speed at 10 Meters (m/s)"
}

def _make_nasa_cache_key(lat: float, lon: float) -> str:
    """
    Normalizes coordinates to 1 decimal place (~11.1 km).
    NASA POWER Climatology uses a coarse 0.5° x 0.5° grid (~55 km).
    1dp binning ensures points within the same municipal/district cluster reuse
    identical 30-year climatological baselines without duplicate API calls.
    """
    return f"climate:nasa:{round(lat, 1):.1f}:{round(lon, 1):.1f}"

class NasaPowerProvider:
    """
    NASA POWER Agroclimatology and Meteorology Provider for baseline climate insights.
    Strictly used for historical 30-year climatology averages, not real-time forecasts.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.base_url = (base_url or settings.NASA_POWER_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.NASA_POWER_TIMEOUT_SECONDS

    async def get_climatology(
        self,
        lat: float,
        lon: float,
        location_meta: Optional[LocationResult] = None
    ) -> NasaPowerClimateResponse:
        """
        Retrieves 30-year NASA POWER climatology averages for coordinates with caching,
        connection reuse, and stale-fallback resilience.
        """
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise InvalidCoordinatesError(f"Coordinates ({lat}, {lon}) are out of valid range [-90..90, -180..180]")

        cache_key = _make_nasa_cache_key(lat, lon)
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"[Cache HIT] NASA POWER climate at key={cache_key}")
            resp = NasaPowerClimateResponse(**cached_data)
            resp.cached = True
            return resp

        params = {
            "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,WS10M",
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "format": "JSON"
        }

        try:
            client = await http_client_manager.get_client()
            response = await client.get(self.base_url, params=params, timeout=self.timeout)

        except httpx.TimeoutException:
            logger.error(f"[Upstream timeout] NASA POWER for ({lat}, {lon}) after {self.timeout}s")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Returning stale NASA POWER data for {cache_key}")
                resp = NasaPowerClimateResponse(**val)
                resp.cached = True
                return resp
            raise UpstreamTimeoutError(provider="NASA POWER", timeout_seconds=self.timeout)

        except Exception as e:
            logger.error(f"[Network error] NASA POWER: {str(e)}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Returning stale NASA POWER data for {cache_key}")
                resp = NasaPowerClimateResponse(**val)
                resp.cached = True
                return resp
            raise UpstreamProviderError(provider="NASA POWER", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"[Upstream {response.status_code}] NASA POWER: {response.text[:200]}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Returning stale NASA POWER data for {cache_key}")
                resp = NasaPowerClimateResponse(**val)
                resp.cached = True
                return resp
            raise UpstreamProviderError(
                provider="NASA POWER",
                status_code=response.status_code,
                message=f"NASA POWER API returned status {response.status_code}"
            )

        try:
            raw = response.json()
        except Exception:
            raise UpstreamProviderError(provider="NASA POWER", status_code=200, message="Malformed JSON response from NASA POWER")

        normalized = self._normalize_nasa_payload(raw, lat, lon, location_meta)
        
        # Cache for configured long-term TTL with 14-day stale window
        await cache.set(
            cache_key,
            normalized.dict(),
            ttl_seconds=settings.CLIMATE_CACHE_TTL_SECONDS,
            stale_ttl_seconds=settings.CLIMATE_CACHE_TTL_SECONDS * 2
        )
        return normalized

    def _normalize_nasa_payload(
        self,
        raw: Dict[str, Any],
        lat: float,
        lon: float,
        location_meta: Optional[LocationResult]
    ) -> NasaPowerClimateResponse:
        properties = raw.get("properties", {})
        parameter_data = properties.get("parameter", {})

        loc = location_meta or LocationResult(
            name=f"Location ({lat:.2f}, {lon:.2f})",
            latitude=lat,
            longitude=lon
        )

        annual_averages: Dict[str, float] = {}
        for param, desc in PARAMETER_DESCRIPTIONS.items():
            param_vals = parameter_data.get(param, {})
            if "ANN" in param_vals and param_vals["ANN"] is not None and param_vals["ANN"] != -999:
                annual_averages[param] = float(param_vals["ANN"])

        monthly_data: List[MonthlyClimateMetric] = []
        for month in MONTH_KEYS:
            metric = MonthlyClimateMetric(month=month)
            t2m = parameter_data.get("T2M", {}).get(month)
            precip = parameter_data.get("PRECTOTCORR", {}).get(month)
            solar = parameter_data.get("ALLSKY_SFC_SW_DWN", {}).get(month)
            rh = parameter_data.get("RH2M", {}).get(month)
            ws = parameter_data.get("WS10M", {}).get(month)

            if t2m is not None and t2m != -999:
                metric.temperature_2m_c = float(t2m)
            if precip is not None and precip != -999:
                metric.precipitation_mm_day = float(precip)
            if solar is not None and solar != -999:
                metric.solar_radiation_kwh_m2_day = float(solar)
            if rh is not None and rh != -999:
                metric.relative_humidity_percent = float(rh)
            if ws is not None and ws != -999:
                metric.wind_speed_10m_ms = float(ws)

            monthly_data.append(metric)

        return NasaPowerClimateResponse(
            provider="NASA POWER",
            location=loc,
            annual_averages=annual_averages,
            monthly_data=monthly_data,
            parameters_explained=PARAMETER_DESCRIPTIONS,
            cached=False,
            retrieved_at=datetime.utcnow()
        )

nasa_power_provider = NasaPowerProvider()
