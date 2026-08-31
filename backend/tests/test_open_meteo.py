import unittest
import asyncio
from unittest.mock import patch, MagicMock
import httpx

from backend.services.weather.open_meteo import OpenMeteoProvider
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError, InvalidCoordinatesError
from backend.core.cache import cache

class TestOpenMeteoProvider(unittest.TestCase):
    def setUp(self):
        self.provider = OpenMeteoProvider(timeout=2.0)
        asyncio.run(cache.clear())

    @patch("httpx.AsyncClient.get")
    def test_geocoding_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1264527,
                    "name": "Chennai",
                    "latitude": 13.0878,
                    "longitude": 80.2785,
                    "country": "India",
                    "country_code": "IN",
                    "admin1": "Tamil Nadu",
                    "timezone": "Asia/Kolkata",
                    "population": 4681087
                }
            ]
        }
        mock_get.return_value = mock_response

        results = asyncio.run(self.provider.resolve_location("Chennai", count=1))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Chennai")
        self.assertEqual(results[0].country, "India")
        self.assertEqual(results[0].admin1, "Tamil Nadu")
        self.assertAlmostEqual(results[0].latitude, 13.0878)

    @patch("httpx.AsyncClient.get")
    def test_geocoding_empty_results(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        results = asyncio.run(self.provider.resolve_location("NonExistentCityXYZ", count=1))
        self.assertEqual(len(results), 0)

    @patch("httpx.AsyncClient.get")
    def test_geocoding_upstream_timeout(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("Connection timed out")
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(self.provider.resolve_location("Chennai"))

    @patch("httpx.AsyncClient.get")
    def test_geocoding_upstream_500_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.provider.resolve_location("Chennai"))

    @patch("httpx.AsyncClient.get")
    def test_forecast_normalization_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latitude": 13.08,
            "longitude": 80.28,
            "elevation": 12.0,
            "timezone": "Asia/Kolkata",
            "current_weather": {
                "temperature": 32.4,
                "windspeed": 14.8,
                "winddirection": 110,
                "weathercode": 1,
                "is_day": 1,
                "time": "2026-08-30T12:00"
            },
            "hourly": {
                "time": ["2026-08-30T00:00", "2026-08-30T01:00"],
                "temperature_2m": [28.2, 27.9],
                "relativehumidity_2m": [82, 84],
                "apparent_temperature": [33.1, 32.5],
                "precipitation_probability": [10, 20],
                "precipitation": [0.0, 0.1],
                "weathercode": [1, 2],
                "windspeed_10m": [12.0, 11.5],
                "uv_index": [0.0, 0.0]
            },
            "daily": {
                "time": ["2026-08-30"],
                "weathercode": [1],
                "temperature_2m_max": [35.2],
                "temperature_2m_min": [27.0],
                "apparent_temperature_max": [39.1],
                "apparent_temperature_min": [31.0],
                "precipitation_sum": [0.2],
                "precipitation_probability_max": [30],
                "precipitation_hours": [0.5],
                "windspeed_10m_max": [16.5],
                "windgusts_10m_max": [24.0],
                "winddirection_10m_dominant": [115],
                "sunrise": ["2026-08-30T06:01"],
                "sunset": ["2026-08-30T18:24"],
                "uv_index_max": [9.8]
            }
        }
        mock_get.return_value = mock_response

        res = asyncio.run(self.provider.get_forecast(lat=13.08, lon=80.28, days=1, include_hourly=True))
        self.assertEqual(res.provider, "Open-Meteo")
        self.assertEqual(res.timezone, "Asia/Kolkata")
        self.assertEqual(res.current.temperature_c, 32.4)
        self.assertEqual(res.current.weather_condition, "Mainly Clear")
        self.assertEqual(len(res.hourly), 2)
        self.assertEqual(res.hourly[0].temperature_c, 28.2)
        self.assertEqual(len(res.daily), 1)
        self.assertEqual(res.daily[0].temperature_max_c, 35.2)

    def test_invalid_coordinates(self):
        with self.assertRaises(InvalidCoordinatesError):
            asyncio.run(self.provider.get_forecast(lat=95.0, lon=80.0))
        with self.assertRaises(InvalidCoordinatesError):
            asyncio.run(self.provider.get_forecast(lat=13.0, lon=200.0))
