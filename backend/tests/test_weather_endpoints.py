import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.schemas.location import LocationResult
from backend.schemas.weather import (
    NormalizedWeatherResponse,
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
)
from backend.schemas.climate import NasaPowerClimateResponse, MonthlyClimateMetric
from datetime import datetime

class TestWeatherEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.resolve_location")
    def test_location_search_endpoint(self, mock_resolve):
        mock_resolve.return_value = [
            LocationResult(
                id=1,
                name="Chennai",
                latitude=13.08,
                longitude=80.27,
                country="India",
                admin1="Tamil Nadu",
                timezone="Asia/Kolkata"
            )
        ]
        response = self.client.get("/api/location/search?q=Chennai&count=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["query"], "Chennai")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["name"], "Chennai")

    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_forecast")
    def test_weather_current_and_forecast_endpoints(self, mock_forecast):
        mock_resp = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=LocationResult(name="Test City", latitude=13.08, longitude=80.27),
            current=CurrentWeather(
                temperature_c=31.0,
                apparent_temperature_c=35.0,
                humidity_percent=75,
                precipitation_mm=0.0,
                wind_speed_kmh=12.0,
                wind_direction_deg=90,
                weather_code=1,
                weather_condition="Mainly Clear",
                icon_key="mainly-clear",
                observed_time=datetime.utcnow()
            ),
            daily=[
                DailyForecast(
                    date="2026-08-30",
                    temperature_max_c=34.0,
                    temperature_min_c=27.0,
                    precipitation_sum_mm=0.0,
                    weather_code=1,
                    weather_condition="Mainly Clear",
                    icon_key="mainly-clear",
                    wind_speed_max_kmh=15.0
                )
            ]
        )
        mock_forecast.return_value = mock_resp

        # Test current
        res_current = self.client.get("/api/weather/current?lat=13.08&lon=80.27")
        self.assertEqual(res_current.status_code, 200)
        self.assertEqual(res_current.json()["current"]["temperature_c"], 31.0)

        # Test forecast
        res_fc = self.client.get("/api/weather/forecast?lat=13.08&lon=80.27&days=5&hourly=true")
        self.assertEqual(res_fc.status_code, 200)
        self.assertEqual(res_fc.json()["provider"], "Open-Meteo")

    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.resolve_location")
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_forecast")
    def test_weather_by_city_endpoint(self, mock_forecast, mock_resolve):
        mock_loc = LocationResult(id=1, name="Chennai", latitude=13.08, longitude=80.27, country="India")
        mock_resolve.return_value = [mock_loc]
        mock_forecast.return_value = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=mock_loc,
            current=CurrentWeather(
                temperature_c=32.0,
                apparent_temperature_c=36.0,
                humidity_percent=70,
                precipitation_mm=0.0,
                wind_speed_kmh=10.0,
                wind_direction_deg=100,
                weather_code=0,
                weather_condition="Clear Sky",
                icon_key="clear-day",
                observed_time=datetime.utcnow()
            )
        )

        response = self.client.get("/api/weather/by-city?city=Chennai")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["location"]["name"], "Chennai")
        self.assertEqual(data["current"]["weather_condition"], "Clear Sky")

    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.resolve_location")
    def test_weather_by_city_not_found(self, mock_resolve):
        mock_resolve.return_value = []
        response = self.client.get("/api/weather/by-city?city=UnknownXYZ")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_type"], "LocationNotFound")

    def test_invalid_coordinates_validation(self):
        response = self.client.get("/api/weather/current?lat=95.0&lon=80.0")
        self.assertEqual(response.status_code, 422)

    @patch("backend.services.weather.nasa_power.NasaPowerProvider.get_climatology")
    def test_climate_historical_endpoint(self, mock_climate):
        mock_climate.return_value = NasaPowerClimateResponse(
            provider="NASA POWER",
            location=LocationResult(name="Test Loc", latitude=13.08, longitude=80.27),
            annual_averages={"T2M": 28.9, "PRECTOTCORR": 3.9},
            monthly_data=[MonthlyClimateMetric(month="JAN", temperature_2m_c=25.1)],
            parameters_explained={"T2M": "Temp"}
        )
        response = self.client.get("/api/climate/historical?lat=13.08&lon=80.27")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "NASA POWER")
        self.assertEqual(data["annual_averages"]["T2M"], 28.9)
