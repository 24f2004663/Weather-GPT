"""
Regression tests for coordinate-keyed weather cache preserving caller location metadata.

The weather cache is keyed by rounded coordinates only. A caller holding just lat/lon
(the AI tool path) caches a payload whose `location` is a bare-coordinate placeholder.
Without re-application, every later city lookup for those coordinates inherits that
placeholder — and because the dashboard derives disaster-alert targeting from
location.admin1 / location.name, the user is shown "no active warnings" while a real
warning is in force.
"""
import unittest
from datetime import datetime

from backend.core.cache import cache
from backend.schemas.location import LocationResult
from backend.services.weather.open_meteo import (
    open_meteo_provider,
    _apply_location_meta,
    _is_placeholder_location,
    _make_weather_cache_key,
)
from backend.schemas.weather import NormalizedWeatherResponse, CurrentWeather


CHENNAI = LocationResult(
    id=1264527, name="Chennai", latitude=13.08784, longitude=80.27847,
    country="India", country_code="IN", admin1="Tamil Nadu",
    admin2="Chennai district", timezone="Asia/Kolkata",
)


def _placeholder(lat, lon):
    return LocationResult(name=f"Location ({lat:.2f}, {lon:.2f})", latitude=lat, longitude=lon)


def _resp(loc):
    return NormalizedWeatherResponse(
        provider="Open-Meteo", location=loc,
        current=CurrentWeather(temperature_c=33.4, weather_code=0,
                               weather_condition="Clear Sky", icon_key="clear-day",
                               observed_time=datetime.utcnow()),
        hourly=[], daily=[], timezone="Asia/Kolkata",
    )


class TestPlaceholderDetection(unittest.TestCase):
    def test_bare_coordinate_location_is_placeholder(self):
        self.assertTrue(_is_placeholder_location(_placeholder(13.08784, 80.27847)))

    def test_geocoded_location_is_not_placeholder(self):
        self.assertFalse(_is_placeholder_location(CHENNAI))

    def test_none_is_placeholder(self):
        self.assertTrue(_is_placeholder_location(None))


class TestApplyLocationMeta(unittest.TestCase):
    def test_resolved_meta_overrides_cached_placeholder(self):
        resp = _apply_location_meta(_resp(_placeholder(13.08784, 80.27847)), CHENNAI)
        self.assertEqual(resp.location.name, "Chennai")
        self.assertEqual(resp.location.admin1, "Tamil Nadu")

    def test_absent_meta_leaves_cached_location_intact(self):
        resp = _apply_location_meta(_resp(CHENNAI), None)
        self.assertEqual(resp.location.name, "Chennai")

    def test_placeholder_meta_does_not_clobber_good_cached_location(self):
        resp = _apply_location_meta(_resp(CHENNAI), _placeholder(13.08784, 80.27847))
        self.assertEqual(resp.location.admin1, "Tamil Nadu")


class TestCachePoisoningRegression(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await cache.clear()

    async def test_ai_tool_path_does_not_poison_later_city_lookup(self):
        """
        Order of operations that produced the live Chennai false negative:
          1. AI tool calls get_forecast(lat, lon) with NO location_meta -> caches placeholder
          2. Dashboard calls get_forecast(lat, lon, location_meta=Chennai) -> must NOT
             inherit the placeholder, or alert targeting silently breaks.
        """
        lat, lon = 13.08784, 80.27847
        key = _make_weather_cache_key(lat, lon, 3, True)

        # Step 1: seed the cache exactly as the metadata-less AI path would
        await cache.set(key, _resp(_placeholder(lat, lon)).dict(),
                        ttl_seconds=900, stale_ttl_seconds=7200)

        # Step 2: dashboard lookup for the same coords, carrying resolved geocoding
        resp = await open_meteo_provider.get_forecast(
            lat=lat, lon=lon, days=3, include_hourly=True, location_meta=CHENNAI
        )

        self.assertTrue(resp.cached, "expected a cache hit for this scenario")
        self.assertEqual(resp.location.name, "Chennai")
        self.assertEqual(resp.location.admin1, "Tamil Nadu",
                         "admin1 is what the dashboard sends as the alert `state` filter")
        self.assertEqual(resp.location.admin2, "Chennai district")

    async def test_alert_targeting_params_survive_a_cache_hit(self):
        """The two fields page.tsx forwards to /api/alerts must be usable after a hit."""
        lat, lon = 13.08784, 80.27847
        await cache.set(_make_weather_cache_key(lat, lon, 7, True),
                        _resp(_placeholder(lat, lon)).dict(),
                        ttl_seconds=900, stale_ttl_seconds=7200)

        resp = await open_meteo_provider.get_forecast(
            lat=lat, lon=lon, days=7, include_hourly=True, location_meta=CHENNAI
        )
        state, district = resp.location.admin1, resp.location.name
        self.assertTrue(state and not state.startswith("Location ("))
        self.assertTrue(district and not district.startswith("Location ("))


if __name__ == "__main__":
    unittest.main()
