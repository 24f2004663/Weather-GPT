import unittest
from datetime import datetime
from pydantic import ValidationError

from backend.schemas.location import LocationResult
from backend.schemas.weather import LocationCoordinates, CurrentWeather, HourlyForecast, DailyForecast, NormalizedWeatherResponse
from backend.schemas.climate import NasaPowerClimateResponse, MonthlyClimateMetric
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertStatus, AlertUrgency, AlertCertainty, GeographicScope
from backend.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from backend.schemas.notifications import NotificationPayload, NotificationChannel

class TestSchemaContracts(unittest.TestCase):
    def test_location_and_weather_validation(self):
        # Valid location
        loc = LocationCoordinates(latitude=13.08, longitude=80.27, city="Chennai")
        self.assertEqual(loc.city, "Chennai")

        # Invalid latitude
        with self.assertRaises(ValidationError):
            LocationCoordinates(latitude=95.0, longitude=80.27)

        # Current weather
        cw = CurrentWeather(
            temperature_c=32.0,
            apparent_temperature_c=36.5,
            humidity_percent=70,
            weather_code=1,
            weather_condition="Mainly Clear",
            icon_key="mainly-clear",
            observed_time=datetime.utcnow()
        )
        self.assertEqual(cw.temperature_c, 32.0)

    def test_climate_schema(self):
        metric = MonthlyClimateMetric(month="JAN", temperature_2m_c=25.4, precipitation_mm_day=1.2)
        climate = NasaPowerClimateResponse(
            provider="NASA POWER",
            location=LocationResult(name="Chennai", latitude=13.08, longitude=80.27),
            annual_averages={"T2M": 28.6},
            monthly_data=[metric],
            parameters_explained={"T2M": "Temperature"}
        )
        self.assertEqual(climate.annual_averages["T2M"], 28.6)

    def test_disaster_alert_schema(self):
        alert = DisasterAlert(
            alert_id="ALERT-001",
            title="Cyclone Warning",
            event_type="Cyclone",
            headline="Cyclone Approaching Coast",
            description="High winds and torrential rain.",
            severity=AlertSeverity.SEVERE,
            urgency=AlertUrgency.IMMEDIATE,
            certainty=AlertCertainty.OBSERVED,
            status=AlertStatus.ACTUAL,
            affected_area="Coastal Tamil Nadu",
            scope=GeographicScope.DISTRICT,
            affected_states=["Tamil Nadu"],
            affected_districts=["Chennai"],
            effective_time=datetime.utcnow(),
            expires_time=datetime.utcnow(),
            is_active=True
        )
        self.assertEqual(alert.severity, AlertSeverity.SEVERE)
        self.assertEqual(alert.event_type, "Cyclone")

    def test_chat_and_notification_schemas(self):
        msg = ChatMessage(role="user", content="What is the weather in Chennai?")
        req = ChatRequest(messages=[msg])
        self.assertEqual(len(req.messages), 1)

        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Weather Alert",
            message="Heavy rain alert for your area.",
        )
        self.assertEqual(payload.channel, NotificationChannel.SMS)
