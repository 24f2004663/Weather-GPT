"""
Tests for present-moment current-weather normalization.

The provider previously requested the legacy `current_weather=true` block, which
returns only temperature, wind and weather code. Everything else was either null or
reconstructed wrongly:
  - apparent_temperature_c was set to the actual temperature
  - humidity/apparent/precipitation were backfilled from hourly[0], i.e. MIDNIGHT
  - uv_index, cloud_cover_percent, pressure_hpa and wind_gusts_kmh were always null
  - observed_time reported the fetch time rather than the observation time
"""
import unittest
from datetime import datetime

from backend.services.weather.open_meteo import (
    open_meteo_provider,
    _parse_observation_time,
)

# 11:30 local, +05:30 -> 06:00Z. Deliberately unlike the hourly[0] (midnight) values.
MODERN_PAYLOAD = {
    "timezone": "Asia/Kolkata",
    "utc_offset_seconds": 19800,
    "elevation": 15.0,
    "current": {
        "time": "2026-09-29T11:30",
        "temperature_2m": 34.2,
        "apparent_temperature": 40.3,
        "relative_humidity_2m": 49,
        "precipitation": 0.0,
        "weather_code": 0,
        "wind_speed_10m": 6.6,
        "wind_direction_10m": 287,
        "wind_gusts_10m": 25.6,
        "cloud_cover": 11,
        "pressure_msl": 1011.3,
        "uv_index": 6.35,
        "is_day": 1,
    },
    "hourly": {
        "time": ["2026-09-29T00:00", "2026-09-29T01:00"],
        "temperature_2m": [25.9, 26.7],
        "apparent_temperature": [30.0, 31.9],
        "relativehumidity_2m": [92, 89],
        "precipitation": [2.3, 0.3],
        "precipitation_probability": [32, 56],
        "weathercode": [80, 51],
        "windspeed_10m": [15.9, 8.6],
        "uv_index": [0.0, 0.0],
    },
}

LEGACY_PAYLOAD = {
    "timezone": "Asia/Kolkata",
    "utc_offset_seconds": 19800,
    "current_weather": {
        "time": "2026-09-29T11:30",
        "temperature": 34.2,
        "windspeed": 6.6,
        "winddirection": 287,
        "weathercode": 0,
        "is_day": 1,
    },
}


def _normalize(payload):
    return open_meteo_provider._normalize_open_meteo_payload(payload, 13.08, 80.27, None)


class TestObservationTime(unittest.TestCase):
    def test_local_time_is_converted_to_utc(self):
        self.assertEqual(_parse_observation_time("2026-09-29T11:30", 19800),
                         datetime(2026, 9, 29, 6, 0))

    def test_offset_aware_timestamp_is_converted_to_utc(self):
        self.assertEqual(_parse_observation_time("2026-09-29T11:30:00+05:30", 19800),
                         datetime(2026, 9, 29, 6, 0))

    def test_missing_or_malformed_time_falls_back_without_raising(self):
        for value in (None, "", "not-a-timestamp"):
            self.assertIsInstance(_parse_observation_time(value, 19800), datetime)

    def test_absent_offset_leaves_time_unshifted(self):
        self.assertEqual(_parse_observation_time("2026-09-29T11:30", None),
                         datetime(2026, 9, 29, 11, 30))


class TestCurrentWeatherNormalization(unittest.TestCase):
    def setUp(self):
        self.current = _normalize(MODERN_PAYLOAD).current

    def test_no_advertised_field_is_null(self):
        for field in ("apparent_temperature_c", "humidity_percent", "precipitation_mm",
                      "wind_gusts_kmh", "uv_index", "cloud_cover_percent", "pressure_hpa"):
            with self.subTest(field=field):
                self.assertIsNotNone(getattr(self.current, field),
                                     f"{field} is surfaced in the UI and must not be null")

    def test_apparent_temperature_is_not_a_copy_of_the_actual_temperature(self):
        self.assertEqual(self.current.temperature_c, 34.2)
        self.assertEqual(self.current.apparent_temperature_c, 40.3)
        self.assertNotEqual(self.current.apparent_temperature_c, self.current.temperature_c)

    def test_humidity_is_the_present_reading_not_the_midnight_one(self):
        """Regression: hourly[0] is midnight; using it reported 92% instead of 49%."""
        self.assertEqual(self.current.humidity_percent, 49)
        self.assertNotEqual(self.current.humidity_percent, 92)

    def test_precipitation_is_the_present_reading_not_the_midnight_one(self):
        self.assertEqual(self.current.precipitation_mm, 0.0)
        self.assertNotEqual(self.current.precipitation_mm, 2.3)

    def test_remaining_current_fields_are_read_from_the_current_block(self):
        self.assertEqual(self.current.wind_gusts_kmh, 25.6)
        self.assertEqual(self.current.cloud_cover_percent, 11)
        self.assertEqual(self.current.pressure_hpa, 1011.3)
        self.assertEqual(self.current.uv_index, 6.35)

    def test_observed_time_is_the_observation_not_the_fetch(self):
        self.assertEqual(self.current.observed_time, datetime(2026, 9, 29, 6, 0))

    def test_hourly_series_is_still_parsed(self):
        hourly = _normalize(MODERN_PAYLOAD).hourly
        self.assertEqual(len(hourly), 2)
        self.assertEqual(hourly[0].humidity_percent, 92)  # midnight, correctly placed


class TestLegacyPayloadFallback(unittest.TestCase):
    """A cached or replayed legacy payload must still normalize rather than crash."""

    def setUp(self):
        self.current = _normalize(LEGACY_PAYLOAD).current

    def test_core_fields_survive(self):
        self.assertEqual(self.current.temperature_c, 34.2)
        self.assertEqual(self.current.wind_speed_kmh, 6.6)
        self.assertEqual(self.current.weather_code, 0)

    def test_fields_absent_from_the_legacy_block_are_null_not_fabricated(self):
        self.assertIsNone(self.current.humidity_percent)
        self.assertIsNone(self.current.cloud_cover_percent)

    def test_observed_time_still_resolves(self):
        self.assertEqual(self.current.observed_time, datetime(2026, 9, 29, 6, 0))


class TestEmptyPayloadSafety(unittest.TestCase):
    def test_missing_current_block_does_not_raise(self):
        current = _normalize({"timezone": "UTC"}).current
        self.assertEqual(current.temperature_c, 0.0)
        self.assertIsInstance(current.observed_time, datetime)


if __name__ == "__main__":
    unittest.main()
