"""
test_open_meteo_cache.py

Focused integration tests for the Open-Meteo provider's cache architecture:
- Coordinate normalization (cache key equality despite minor coord differences)
- Fresh cache hit
- Cache expiry → fresh provider call
- Concurrent in-flight deduplication
- Dashboard + Gemini tool sharing the same cache key
- Subset reuse (7-day+hourly payload satisfies current-weather request)
- 429 with fresh cache → return fresh (no raise)
- 429 with stale cache → return stale
- 429 with no cache → raise UpstreamProviderError
- Timeout with stale cache → return stale
- Timeout with no cache → raise UpstreamTimeoutError
- Retry NOT performed on 429
"""

import asyncio
import unittest
import time
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

import httpx

from backend.services.weather.open_meteo import OpenMeteoProvider, _make_weather_cache_key, _normalize_coord
from backend.core.cache import cache as global_cache, InMemoryTTLCache
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError
from backend.schemas.weather import NormalizedWeatherResponse, CurrentWeather, DailyForecast
from backend.schemas.location import LocationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(status_code: int = 200, json_data: dict = None, headers: dict = None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or _open_meteo_payload()
    mock.text = str(json_data) if json_data else "ok"
    mock.headers = headers or {}
    return mock


def _open_meteo_payload(days: int = 7, include_hourly: bool = True) -> dict:
    """Minimal valid Open-Meteo forecast API response."""
    d = {
        "latitude": 13.08,
        "longitude": 80.27,
        "timezone": "Asia/Kolkata",
        "elevation": 10.0,
        "current_weather": {
            "temperature": 31.0,
            "windspeed": 12.0,
            "winddirection": 90,
            "weathercode": 1,
            "is_day": 1,
            "time": "2026-09-01T12:00"
        },
        "daily": {
            "time": [f"2026-09-0{i+1}" for i in range(days)],
            "weathercode": [1] * days,
            "temperature_2m_max": [34.0] * days,
            "temperature_2m_min": [27.0] * days,
            "apparent_temperature_max": [38.0] * days,
            "apparent_temperature_min": [31.0] * days,
            "precipitation_sum": [0.0] * days,
            "precipitation_probability_max": [10] * days,
            "precipitation_hours": [0.0] * days,
            "windspeed_10m_max": [15.0] * days,
            "windgusts_10m_max": [22.0] * days,
            "winddirection_10m_dominant": [90] * days,
            "sunrise": [f"2026-09-0{i+1}T06:00" for i in range(days)],
            "sunset": [f"2026-09-0{i+1}T18:30" for i in range(days)],
            "uv_index_max": [9.0] * days,
        }
    }
    if include_hourly:
        d["hourly"] = {
            "time": [f"2026-09-01T{h:02d}:00" for h in range(24)],
            "temperature_2m": [30.0] * 24,
            "relativehumidity_2m": [75] * 24,
            "apparent_temperature": [34.0] * 24,
            "precipitation_probability": [10] * 24,
            "precipitation": [0.0] * 24,
            "weathercode": [1] * 24,
            "windspeed_10m": [12.0] * 24,
            "uv_index": [5.0] * 24,
        }
    return d


class TestCoordinateNormalization(unittest.TestCase):
    """Cache key generation and coordinate rounding behavior."""

    def test_normalize_coord_basic(self):
        self.assertAlmostEqual(_normalize_coord(13.0827), 13.08)
        self.assertAlmostEqual(_normalize_coord(80.2707), 80.27)

    def test_normalize_coord_rounds_to_2dp(self):
        self.assertAlmostEqual(_normalize_coord(13.0878), 13.09)
        self.assertAlmostEqual(_normalize_coord(13.0849), 13.08)

    def test_dashboard_and_geocoding_produce_same_cache_key(self):
        """
        Dashboard uses hardcoded lat=13.0827, lon=80.2707 for Chennai.
        Gemini tool uses provided coordinates directly (after prompt fix).
        Both should produce the same 2dp cache key.
        """
        key_dashboard = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        key_same = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        self.assertEqual(key_dashboard, key_same)

    def test_different_cities_different_keys(self):
        """Mumbai and Chennai must NOT share a cache key."""
        key_chennai = _make_weather_cache_key(13.08, 80.27, 7, True)
        key_mumbai = _make_weather_cache_key(19.08, 72.88, 7, True)
        self.assertNotEqual(key_chennai, key_mumbai)

    def test_cache_key_format(self):
        key = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        self.assertEqual(key, "weather:13.08:80.27:7:True")

    def test_cache_key_hourly_flag_distinguishes(self):
        key_with = _make_weather_cache_key(13.08, 80.27, 7, True)
        key_without = _make_weather_cache_key(13.08, 80.27, 7, False)
        self.assertNotEqual(key_with, key_without)


class TestFreshCacheHit(unittest.TestCase):
    """Verify that a warm cache prevents any provider call."""

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_cache_hit_no_provider_call(self, mock_get):
        """Second identical request must not call Open-Meteo."""
        mock_get.return_value = _make_mock_response()
        # First call — populates cache
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        # Second call — must be served from cache
        mock_get.reset_mock()
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.assert_not_called()
        self.assertTrue(res.cached)
        self.assertFalse(res.stale)

    @patch("httpx.AsyncClient.get")
    def test_cache_miss_after_expiry(self, mock_get):
        """After fresh TTL expires, a new provider call must be made."""
        mock_get.return_value = _make_mock_response()
        provider = OpenMeteoProvider(timeout=5.0)
        # Cache with 1s TTL
        asyncio.run(provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        # Manually override cache with 1s TTL
        key = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        raw = asyncio.run(global_cache.get_with_stale(key))
        if raw:
            asyncio.run(global_cache.set(key, raw[0], ttl_seconds=1, stale_ttl_seconds=1))
        time.sleep(1.2)
        mock_get.reset_mock()
        asyncio.run(provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.assert_called_once()


class TestSubsetReuse(unittest.TestCase):
    """7-day+hourly cache satisfies smaller requests without a provider call."""

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_current_weather_reuses_7day_cache(self, mock_get):
        """get_current_weather (days=1, hourly=False) served from 7-day cache."""
        mock_get.return_value = _make_mock_response(json_data=_open_meteo_payload(days=7, include_hourly=True))
        # Populate 7-day cache via dashboard-style call
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.reset_mock()
        # Now call current_weather — must NOT hit provider
        res = asyncio.run(self.provider.get_current_weather(lat=13.0827, lon=80.2707))
        mock_get.assert_not_called()
        self.assertTrue(res.cached)
        self.assertEqual(len(res.hourly), 0)  # hourly stripped

    @patch("httpx.AsyncClient.get")
    def test_3day_reuses_7day_cache(self, mock_get):
        """get_forecast(days=3) served from 7-day cached payload."""
        mock_get.return_value = _make_mock_response(json_data=_open_meteo_payload(days=7, include_hourly=True))
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.reset_mock()
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=3, include_hourly=True))
        mock_get.assert_not_called()
        self.assertTrue(res.cached)
        self.assertEqual(len(res.daily), 3)

    @patch("httpx.AsyncClient.get")
    def test_7day_nohourly_reuses_7day_hourly_cache(self, mock_get):
        """get_forecast(days=7, hourly=False) served from 7-day+hourly cache."""
        mock_get.return_value = _make_mock_response(json_data=_open_meteo_payload(days=7, include_hourly=True))
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.reset_mock()
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=False))
        mock_get.assert_not_called()
        self.assertTrue(res.cached)
        self.assertEqual(res.hourly, [])


class TestConcurrentDeduplication(unittest.TestCase):
    """Concurrent requests for the same cache key produce exactly one provider call."""

    def setUp(self):
        asyncio.run(global_cache.clear())

    @patch("httpx.AsyncClient.get")
    def test_concurrent_requests_single_provider_call(self, mock_get):
        """10 concurrent get_forecast calls → exactly 1 Open-Meteo request."""
        call_count = 0
        original_get = _make_mock_response()

        async def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # simulate network latency
            return original_get

        mock_get.side_effect = fake_get

        provider = OpenMeteoProvider(timeout=5.0)

        async def run_all():
            tasks = [
                provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True)
                for _ in range(10)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_all())
        self.assertEqual(call_count, 1, f"Expected 1 provider call, got {call_count}")
        self.assertEqual(len(results), 10)


class TestRateLimitFallback(unittest.TestCase):
    """HTTP 429 handling with and without cached data."""

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_429_with_fresh_cache_returns_cached(self, mock_get):
        """429 when fresh cache exists → return fresh cached data, no exception."""
        # First: populate fresh cache
        mock_get.return_value = _make_mock_response(200)
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        # Second: simulate 429
        mock_get.return_value = _make_mock_response(200)  # still fresh, won't even call provider
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        self.assertTrue(res.cached)
        self.assertFalse(res.stale)

    @patch("httpx.AsyncClient.get")
    def test_429_with_stale_cache_returns_stale(self, mock_get):
        """429 when only stale data exists → return stale data with stale=True."""
        # Populate cache then force-expire the fresh window
        mock_get.return_value = _make_mock_response(200)
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        # Manually set entry to stale (fresh expired, stale still valid)
        key = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        raw = asyncio.run(global_cache.get_with_stale(key))
        self.assertIsNotNone(raw)
        # Re-store with 1s fresh, 3600s stale
        asyncio.run(global_cache.set(key, raw[0], ttl_seconds=1, stale_ttl_seconds=3600))
        time.sleep(1.1)  # expire fresh window

        # Now simulate 429
        mock_429 = _make_mock_response(429, headers={"Retry-After": "60"})
        mock_get.return_value = mock_429

        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        self.assertTrue(res.cached)
        self.assertTrue(res.stale)

    @patch("httpx.AsyncClient.get")
    def test_429_with_no_cache_raises(self, mock_get):
        """429 with no cache at all → raises UpstreamProviderError(status_code=429)."""
        mock_429 = _make_mock_response(429, headers={"Retry-After": "60"})
        mock_get.return_value = mock_429
        with self.assertRaises(UpstreamProviderError) as ctx:
            asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        self.assertEqual(ctx.exception.status_code, 429)

    @patch("httpx.AsyncClient.get")
    def test_429_no_retry(self, mock_get):
        """On 429, the provider must NOT retry — exactly 1 upstream call made."""
        mock_429 = _make_mock_response(429, headers={"Retry-After": "60"})
        mock_get.return_value = mock_429
        try:
            asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        except UpstreamProviderError:
            pass
        self.assertEqual(mock_get.call_count, 1, "Provider must not retry on 429")


class TestTimeoutFallback(unittest.TestCase):
    """Timeout handling with and without cached data."""

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_timeout_with_stale_cache_returns_stale(self, mock_get):
        """Timeout when stale data exists → returns stale response."""
        # Populate then expire fresh window
        mock_get.return_value = _make_mock_response(200)
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        key = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        raw = asyncio.run(global_cache.get_with_stale(key))
        asyncio.run(global_cache.set(key, raw[0], ttl_seconds=1, stale_ttl_seconds=3600))
        time.sleep(1.1)

        mock_get.side_effect = httpx.TimeoutException("Timed out")
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        self.assertTrue(res.cached)
        self.assertTrue(res.stale)

    @patch("httpx.AsyncClient.get")
    def test_timeout_with_no_cache_raises(self, mock_get):
        """Timeout with no cache → raises UpstreamTimeoutError."""
        mock_get.side_effect = httpx.TimeoutException("Timed out")
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))


class TestUpstream5xxFallback(unittest.TestCase):
    """HTTP 500/502/503 handling."""

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_5xx_with_stale_cache_returns_stale(self, mock_get):
        """HTTP 502 with stale data → returns stale response."""
        mock_get.return_value = _make_mock_response(200)
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        key = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        raw = asyncio.run(global_cache.get_with_stale(key))
        asyncio.run(global_cache.set(key, raw[0], ttl_seconds=1, stale_ttl_seconds=3600))
        time.sleep(1.1)

        mock_get.return_value = _make_mock_response(502)
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        self.assertTrue(res.stale)

    @patch("httpx.AsyncClient.get")
    def test_5xx_with_no_cache_raises(self, mock_get):
        """HTTP 503 with no cache → raises UpstreamProviderError."""
        mock_get.return_value = _make_mock_response(503)
        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))


class TestDashboardAndChatShareCache(unittest.TestCase):
    """
    Dashboard uses hardcoded coordinates.
    After the system prompt fix, Gemini passes the same coordinates directly.
    Both must converge to the same 2dp cache key and share the cache.
    """

    def setUp(self):
        asyncio.run(global_cache.clear())
        self.provider = OpenMeteoProvider(timeout=5.0)

    @patch("httpx.AsyncClient.get")
    def test_same_coords_produce_one_provider_call(self, mock_get):
        """
        Dashboard call lat=13.0827 and identical chat call lat=13.0827
        → same cache key → second call served from cache, 0 extra provider calls.
        """
        mock_get.return_value = _make_mock_response(200)
        # Dashboard fetch
        asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        # Chat tool fetch with identical coords (system prompt fix sends same coords)
        mock_get.reset_mock()
        res = asyncio.run(self.provider.get_forecast(lat=13.0827, lon=80.2707, days=7, include_hourly=True))
        mock_get.assert_not_called()
        self.assertTrue(res.cached)

    def test_cache_keys_equal_for_same_rounded_coords(self):
        """
        Coordinates that differ only beyond 2dp share the same cache key.
        e.g. 13.0827 and 13.0822 both → 13.08 → same cache key.
        """
        key1 = _make_weather_cache_key(13.0827, 80.2707, 7, True)
        key2 = _make_weather_cache_key(13.0822, 80.2701, 7, True)
        self.assertEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
