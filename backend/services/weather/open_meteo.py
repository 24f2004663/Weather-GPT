import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
from backend.core.errors import (
    LocationNotFoundError,
    UpstreamProviderError,
    UpstreamTimeoutError,
    InvalidCoordinatesError,
)
from backend.services.weather.base import BaseWeatherProvider
from backend.services.weather.wmo_codes import decode_wmo_code
from backend.schemas.location import LocationResult
from backend.schemas.weather import (
    CurrentWeather,
    HourlyForecast,
    DailyForecast,
    NormalizedWeatherResponse,
)

# ---------------------------------------------------------------------------
# In-flight deduplication registry
# Prevents concurrent identical requests from all hitting Open-Meteo at once.
# Scoped to the current process.
# ---------------------------------------------------------------------------
_inflight_weather: Dict[str, asyncio.Event] = {}


def _normalize_coord(value: float, decimals: int = 2) -> float:
    """
    Round a coordinate to `decimals` decimal places for cache-key generation.
    2 dp ≈ 1.1 km — merges dashboard coords (e.g. 13.0827) with Open-Meteo
    geocoding results (e.g. 13.0878) for the same city.
    """
    return round(value, decimals)


def _make_weather_cache_key(lat: float, lon: float, days: int, include_hourly: bool) -> str:
    """Build a normalized cache key using 2dp coordinate rounding."""
    return f"weather:{_normalize_coord(lat):.2f}:{_normalize_coord(lon):.2f}:{days}:{include_hourly}"


class OpenMeteoProvider(BaseWeatherProvider):
    """
    Production-ready Open-Meteo Weather and Geocoding Provider.

    Features:
    - Persistent HTTP connection pooling across requests
    - 15-minute fresh cache with 2-hour stale fallback
    - 2dp coordinate normalization: merges coordinate variations for same location
    - Canonical geocoding caching: count=1 and count=5 share identical geocoding entry
    - Stale geocoding fallback on upstream failure
    - Subset reuse: cached 7-day+hourly payload satisfies current-weather and shorter requests
    - In-flight deduplication: concurrent requests share a single upstream request
    - Explicit HTTP 429 handling with zero aggressive retry
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        geocoding_url: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.base_url = (base_url or settings.OPEN_METEO_BASE_URL).rstrip("/")
        self.geocoding_url = (geocoding_url or settings.OPEN_METEO_GEOCODING_URL).rstrip("/")
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    async def resolve_location(self, query: str, count: int = 5) -> List[LocationResult]:
        """
        Geocodes a place query to a list of normalized LocationResult models.
        Normalized cache key is query-based so count=1 and count=5 share the same entry.
        Results are cached for 24 hours with stale fallback.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        cache_key = f"geo:{clean_query.lower()}"
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"[Cache HIT] Geocoding: '{clean_query}' (request count={count})")
            results = [LocationResult(**item) for item in cached_data]
            return results[:count]

        # Fetch up to 10 candidate matches so cache entry satisfies future higher-count queries
        fetch_count = max(count, 10)
        params = {
            "name": clean_query,
            "count": fetch_count,
            "language": "en",
            "format": "json"
        }

        try:
            client = await http_client_manager.get_client()
            response = await client.get(self.geocoding_url, params=params, timeout=self.timeout)

        except httpx.TimeoutException:
            logger.error(f"[Upstream timeout] Open-Meteo Geocoding for '{clean_query}'")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Geocoding for '{clean_query}'")
                return [LocationResult(**item) for item in val][:count]
            raise UpstreamTimeoutError(provider="Open-Meteo Geocoding", timeout_seconds=self.timeout)

        except Exception as e:
            logger.error(f"[Network error] Open-Meteo Geocoding for '{clean_query}': {e}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Geocoding for '{clean_query}'")
                return [LocationResult(**item) for item in val][:count]
            raise UpstreamProviderError(provider="Open-Meteo Geocoding", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"[Upstream {response.status_code}] Open-Meteo Geocoding: {response.text[:200]}")
            stale_entry = await cache.get_with_stale(cache_key)
            if stale_entry is not None:
                val, _ = stale_entry
                logger.warning(f"[Cache STALE FALLBACK] Geocoding for '{clean_query}'")
                return [LocationResult(**item) for item in val][:count]
            raise UpstreamProviderError(
                provider="Open-Meteo Geocoding",
                status_code=response.status_code,
                message=f"Geocoding service returned status {response.status_code}"
            )

        try:
            data = response.json()
        except Exception:
            raise UpstreamProviderError(
                provider="Open-Meteo Geocoding", status_code=200,
                message="Malformed JSON response from geocoding service"
            )

        raw_results = data.get("results") or []
        normalized_results: List[LocationResult] = []
        for item in raw_results:
            normalized_results.append(LocationResult(
                id=item.get("id"),
                name=item.get("name", clean_query),
                latitude=float(item.get("latitude")),
                longitude=float(item.get("longitude")),
                country=item.get("country"),
                country_code=item.get("country_code"),
                admin1=item.get("admin1"),
                admin2=item.get("admin2"),
                timezone=item.get("timezone", "UTC"),
                elevation=item.get("elevation"),
                population=item.get("population"),
            ))

        logger.info(f"[Provider request] Open-Meteo Geocoding '{clean_query}' -> {len(normalized_results)} results")
        await cache.set(
            cache_key,
            [item.dict() for item in normalized_results],
            ttl_seconds=settings.GEOCODING_CACHE_TTL_SECONDS,
            stale_ttl_seconds=settings.GEOCODING_CACHE_TTL_SECONDS * 2
        )
        return normalized_results[:count]

    # ------------------------------------------------------------------
    # Current weather (convenience wrapper with subset reuse)
    # ------------------------------------------------------------------

    async def get_current_weather(
        self, lat: float, lon: float,
        location_meta: Optional[LocationResult] = None
    ) -> NormalizedWeatherResponse:
        """
        Fetches current weather conditions.
        Transparently satisfied from cached 7-day+hourly forecast payload where available.
        """
        return await self.get_forecast(lat=lat, lon=lon, days=1, include_hourly=False, location_meta=location_meta)

    # ------------------------------------------------------------------
    # Forecast (primary method)
    # ------------------------------------------------------------------

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        include_hourly: bool = True,
        location_meta: Optional[LocationResult] = None
    ) -> NormalizedWeatherResponse:
        """
        Fetches current conditions, daily forecast, and optional hourly forecast.
        """
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise InvalidCoordinatesError(f"Coordinates ({lat}, {lon}) are out of valid range [-90..90, -180..180]")

        days_clamped = max(1, min(days, 16))
        cache_key = _make_weather_cache_key(lat, lon, days_clamped, include_hourly)
        canonical_key = _make_weather_cache_key(lat, lon, 7, True)

        # 1. Fresh cache hit
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"[Cache HIT fresh] ({lat},{lon}) days={days_clamped} hourly={include_hourly}")
            resp = NormalizedWeatherResponse(**cached_data)
            resp.cached = True
            return resp

        # 2. Subset reuse: serve from canonical 7-day+hourly cache
        if cache_key != canonical_key:
            canonical_data = await cache.get(canonical_key)
            if canonical_data is not None:
                logger.info(
                    f"[Cache SUBSET HIT] ({lat},{lon}) serving days={days_clamped}/hourly={include_hourly} "
                    f"from cached 7d+hourly payload"
                )
                resp = NormalizedWeatherResponse(**canonical_data)
                if days_clamped < len(resp.daily):
                    resp.daily = resp.daily[:days_clamped]
                if not include_hourly:
                    resp.hourly = []
                resp.cached = True
                return resp

        # 3. In-flight deduplication
        if cache_key in _inflight_weather:
            logger.debug(f"[In-flight JOINED] ({lat},{lon}) waiting for concurrent request")
            try:
                await asyncio.wait_for(_inflight_weather[cache_key].wait(), timeout=35.0)
            except asyncio.TimeoutError:
                logger.warning(f"[In-flight JOINED timeout] ({lat},{lon}) — proceeding independently")
            
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                resp = NormalizedWeatherResponse(**cached_data)
                resp.cached = True
                return resp
            if cache_key != canonical_key:
                canonical_data = await cache.get(canonical_key)
                if canonical_data is not None:
                    resp = NormalizedWeatherResponse(**canonical_data)
                    if days_clamped < len(resp.daily):
                        resp.daily = resp.daily[:days_clamped]
                    if not include_hourly:
                        resp.hourly = []
                    resp.cached = True
                    return resp

        inflight_event = asyncio.Event()
        _inflight_weather[cache_key] = inflight_event

        # 4. Build and execute provider request
        hourly_vars = [
            "temperature_2m",
            "relativehumidity_2m",
            "apparent_temperature",
            "precipitation_probability",
            "precipitation",
            "weathercode",
            "windspeed_10m",
            "uv_index"
        ] if include_hourly else []

        daily_vars = [
            "weathercode",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "precipitation_hours",
            "windspeed_10m_max",
            "windgusts_10m_max",
            "winddirection_10m_dominant",
            "sunrise",
            "sunset",
            "uv_index_max"
        ]

        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "daily": ",".join(daily_vars),
            "forecast_days": days_clamped,
            "timezone": "auto"
        }
        if include_hourly:
            params["hourly"] = ",".join(hourly_vars)

        endpoint = f"{self.base_url}/forecast"

        try:
            try:
                logger.info(f"[Provider request] Open-Meteo forecast ({lat},{lon}) days={days_clamped} hourly={include_hourly}")
                client = await http_client_manager.get_client()
                response = await client.get(endpoint, params=params, timeout=self.timeout)

            except httpx.TimeoutException:
                logger.error(f"[Upstream timeout] Open-Meteo forecast ({lat},{lon}) after {self.timeout}s")
                stale = await self._try_stale(cache_key, canonical_key, days_clamped, include_hourly, "timeout")
                if stale is not None:
                    return stale
                raise UpstreamTimeoutError(provider="Open-Meteo Forecast", timeout_seconds=self.timeout)

            except Exception as e:
                logger.error(f"[Network error] Open-Meteo forecast ({lat},{lon}): {e}")
                stale = await self._try_stale(cache_key, canonical_key, days_clamped, include_hourly, "network error")
                if stale is not None:
                    return stale
                raise UpstreamProviderError(provider="Open-Meteo Forecast", status_code=None, message=str(e))

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                logger.warning(
                    f"[Upstream 429] Open-Meteo rate-limited for ({lat},{lon}). "
                    f"Retry-After: {retry_after}. Checking stale cache."
                )
                stale = await self._try_stale(cache_key, canonical_key, days_clamped, include_hourly, "429 rate-limit")
                if stale is not None:
                    return stale
                raise UpstreamProviderError(
                    provider="Open-Meteo Forecast",
                    status_code=429,
                    message=(
                        f"Weather provider rate-limited (HTTP 429). "
                        f"Please retry in {retry_after} seconds. This usually resolves within 1 minute."
                    )
                )

            if response.status_code != 200:
                logger.error(f"[Upstream {response.status_code}] Open-Meteo forecast ({lat},{lon}): {response.text[:200]}")
                stale = await self._try_stale(cache_key, canonical_key, days_clamped, include_hourly, f"HTTP {response.status_code}")
                if stale is not None:
                    return stale
                raise UpstreamProviderError(
                    provider="Open-Meteo Forecast",
                    status_code=response.status_code,
                    message=f"Weather service returned status {response.status_code}"
                )

            try:
                raw = response.json()
            except Exception:
                raise UpstreamProviderError(
                    provider="Open-Meteo Forecast", status_code=200,
                    message="Malformed JSON response from weather service"
                )

            normalized = self._normalize_open_meteo_payload(raw, lat, lon, location_meta)

            await cache.set(
                cache_key,
                normalized.dict(),
                ttl_seconds=settings.WEATHER_CACHE_TTL_SECONDS,
                stale_ttl_seconds=settings.WEATHER_STALE_CACHE_TTL_SECONDS
            )
            logger.info(
                f"[Cache SET] ({lat},{lon}) days={days_clamped} hourly={include_hourly} "
                f"fresh={settings.WEATHER_CACHE_TTL_SECONDS}s stale={settings.WEATHER_STALE_CACHE_TTL_SECONDS}s"
            )
            return normalized

        finally:
            if cache_key in _inflight_weather:
                _inflight_weather[cache_key].set()
                del _inflight_weather[cache_key]

    async def _try_stale(
        self,
        cache_key: str,
        canonical_key: str,
        days: int,
        include_hourly: bool,
        reason: str
    ) -> Optional[NormalizedWeatherResponse]:
        stale_entry = await cache.get_with_stale(cache_key)
        if stale_entry is not None:
            value, is_stale = stale_entry
            if is_stale:
                logger.warning(f"[Cache STALE FALLBACK] ({reason}) returning stale data for key={cache_key}")
                resp = NormalizedWeatherResponse(**value)
                resp.cached = True
                resp.stale = True
                return resp
            else:
                logger.info(f"[Cache HIT fresh (stale-path)] key={cache_key}")
                resp = NormalizedWeatherResponse(**value)
                resp.cached = True
                return resp

        if cache_key != canonical_key:
            stale_canonical = await cache.get_with_stale(canonical_key)
            if stale_canonical is not None:
                value, is_stale = stale_canonical
                logger.warning(
                    f"[Cache STALE SUPERSET FALLBACK] ({reason}) returning {'stale' if is_stale else 'fresh'} "
                    f"superset data for key={cache_key}"
                )
                resp = NormalizedWeatherResponse(**value)
                if days < len(resp.daily):
                    resp.daily = resp.daily[:days]
                if not include_hourly:
                    resp.hourly = []
                resp.cached = True
                resp.stale = is_stale
                return resp

        logger.error(f"[No cache available] ({reason}) for key={cache_key} — returning None")
        return None

    def _normalize_open_meteo_payload(
        self,
        raw: Dict[str, Any],
        lat: float,
        lon: float,
        location_meta: Optional[LocationResult]
    ) -> NormalizedWeatherResponse:
        tz = raw.get("timezone", "UTC")
        elevation = raw.get("elevation")

        loc = location_meta or LocationResult(
            name=f"Location ({lat:.2f}, {lon:.2f})",
            latitude=lat,
            longitude=lon,
            timezone=tz,
            elevation=elevation
        )

        cw_raw = raw.get("current_weather") or {}
        w_code = int(cw_raw.get("weathercode", 0))
        cond_name, _, icon_key = decode_wmo_code(w_code)

        temp_val = cw_raw.get("temperature")
        wind_val = cw_raw.get("windspeed")
        wind_dir_val = cw_raw.get("winddirection")
        is_day_val = cw_raw.get("is_day")

        current = CurrentWeather(
            temperature_c=float(temp_val) if temp_val is not None else 0.0,
            apparent_temperature_c=float(temp_val) if temp_val is not None else None,
            humidity_percent=None,
            precipitation_mm=None,
            wind_speed_kmh=float(wind_val) if wind_val is not None else None,
            wind_direction_deg=int(wind_dir_val) if wind_dir_val is not None else None,
            weather_code=w_code,
            weather_condition=cond_name,
            icon_key=icon_key,
            is_day=int(is_day_val) if is_day_val is not None else 1,
            observed_time=datetime.utcnow()
        )

        hourly_list: List[HourlyForecast] = []
        h_raw = raw.get("hourly")
        if h_raw and "time" in h_raw:
            times = h_raw["time"]
            temps = h_raw.get("temperature_2m") or []
            app_temps = h_raw.get("apparent_temperature") or []
            precips = h_raw.get("precipitation") or []
            precip_probs = h_raw.get("precipitation_probability") or []
            codes = h_raw.get("weathercode") or []
            winds = h_raw.get("windspeed_10m") or []
            humidities = h_raw.get("relativehumidity_2m") or []
            uvs = h_raw.get("uv_index") or []

            if humidities and len(humidities) > 0 and humidities[0] is not None:
                current.humidity_percent = int(humidities[0])
            if app_temps and len(app_temps) > 0 and app_temps[0] is not None:
                current.apparent_temperature_c = float(app_temps[0])
            if precips and len(precips) > 0 and precips[0] is not None:
                current.precipitation_mm = float(precips[0])

            for idx, t_str in enumerate(times[:48]):
                h_code = int(codes[idx]) if idx < len(codes) and codes[idx] is not None else 0
                h_cond, _, h_icon = decode_wmo_code(h_code)
                hourly_list.append(HourlyForecast(
                    time=str(t_str),
                    temperature_c=float(temps[idx]) if idx < len(temps) and temps[idx] is not None else 0.0,
                    apparent_temperature_c=float(app_temps[idx]) if idx < len(app_temps) and app_temps[idx] is not None else None,
                    precipitation_probability=int(precip_probs[idx]) if idx < len(precip_probs) and precip_probs[idx] is not None else None,
                    precipitation_mm=float(precips[idx]) if idx < len(precips) and precips[idx] is not None else None,
                    weather_code=h_code,
                    weather_condition=h_cond,
                    icon_key=h_icon,
                    wind_speed_kmh=float(winds[idx]) if idx < len(winds) and winds[idx] is not None else None,
                    humidity_percent=int(humidities[idx]) if idx < len(humidities) and humidities[idx] is not None else None,
                    uv_index=float(uvs[idx]) if idx < len(uvs) and uvs[idx] is not None else None,
                ))

        daily_list: List[DailyForecast] = []
        d_raw = raw.get("daily")
        if d_raw and "time" in d_raw:
            d_times = d_raw["time"]
            t_max = d_raw.get("temperature_2m_max") or []
            t_min = d_raw.get("temperature_2m_min") or []
            app_max = d_raw.get("apparent_temperature_max") or []
            app_min = d_raw.get("apparent_temperature_min") or []
            p_sum = d_raw.get("precipitation_sum") or []
            p_prob_max = d_raw.get("precipitation_probability_max") or []
            p_hours = d_raw.get("precipitation_hours") or []
            d_codes = d_raw.get("weathercode") or []
            w_max = d_raw.get("windspeed_10m_max") or []
            w_gusts = d_raw.get("windgusts_10m_max") or []
            w_dirs = d_raw.get("winddirection_10m_dominant") or []
            sunrises = d_raw.get("sunrise") or []
            sunsets = d_raw.get("sunset") or []
            uv_max = d_raw.get("uv_index_max") or []

            for idx, date_str in enumerate(d_times):
                d_code = int(d_codes[idx]) if idx < len(d_codes) and d_codes[idx] is not None else 0
                d_cond, _, d_icon = decode_wmo_code(d_code)
                daily_list.append(DailyForecast(
                    date=str(date_str),
                    temperature_max_c=float(t_max[idx]) if idx < len(t_max) and t_max[idx] is not None else 0.0,
                    temperature_min_c=float(t_min[idx]) if idx < len(t_min) and t_min[idx] is not None else 0.0,
                    apparent_temperature_max_c=float(app_max[idx]) if idx < len(app_max) and app_max[idx] is not None else None,
                    apparent_temperature_min_c=float(app_min[idx]) if idx < len(app_min) and app_min[idx] is not None else None,
                    precipitation_sum_mm=float(p_sum[idx]) if idx < len(p_sum) and p_sum[idx] is not None else None,
                    precipitation_probability_max=int(p_prob_max[idx]) if idx < len(p_prob_max) and p_prob_max[idx] is not None else None,
                    precipitation_hours=float(p_hours[idx]) if idx < len(p_hours) and p_hours[idx] is not None else None,
                    weather_code=d_code,
                    weather_condition=d_cond,
                    icon_key=d_icon,
                    wind_speed_max_kmh=float(w_max[idx]) if idx < len(w_max) and w_max[idx] is not None else None,
                    wind_gusts_max_kmh=float(w_gusts[idx]) if idx < len(w_gusts) and w_gusts[idx] is not None else None,
                    wind_direction_dominant_deg=int(w_dirs[idx]) if idx < len(w_dirs) and w_dirs[idx] is not None else None,
                    sunrise=str(sunrises[idx]) if idx < len(sunrises) and sunrises[idx] is not None else None,
                    sunset=str(sunsets[idx]) if idx < len(sunsets) and sunsets[idx] is not None else None,
                    uv_index_max=float(uv_max[idx]) if idx < len(uv_max) and uv_max[idx] is not None else None,
                ))

        return NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=loc,
            current=current,
            hourly=hourly_list,
            daily=daily_list,
            timezone=tz,
            elevation_m=elevation,
            cached=False,
            stale=False,
            retrieved_at=datetime.utcnow()
        )


open_meteo_provider = OpenMeteoProvider()
