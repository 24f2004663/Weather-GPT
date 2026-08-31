import unittest
import asyncio
from unittest.mock import patch, MagicMock
from backend.services.weather.open_meteo import OpenMeteoProvider
from backend.services.weather.nasa_power import NasaPowerProvider
from backend.services.ai.gemini import GeminiAIService
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.services.notifications.whatsapp import WhatsAppNotificationAdapter
from backend.schemas.chat import ChatRequest, ChatMessage
from backend.schemas.notifications import NotificationPayload, NotificationChannel, NotificationStatus

class TestServiceAdapters(unittest.TestCase):
    @patch("httpx.AsyncClient.get")
    def test_open_meteo_adapter(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latitude": 13.08,
            "longitude": 80.27,
            "timezone": "Asia/Kolkata",
            "current_weather": {
                "temperature": 31.5,
                "windspeed": 14.2,
                "winddirection": 120,
                "weathercode": 1,
                "is_day": 1
            },
            "daily": {
                "time": ["2026-08-30"],
                "weathercode": [1],
                "temperature_2m_max": [34.0],
                "temperature_2m_min": [27.0],
                "precipitation_sum": [0.5],
                "windspeed_10m_max": [16.0]
            }
        }
        mock_get.return_value = mock_response

        provider = OpenMeteoProvider()
        res = asyncio.run(provider.get_current_weather(lat=13.08, lon=80.27))
        self.assertEqual(res.provider, "Open-Meteo")
        self.assertAlmostEqual(res.current.temperature_c, 31.5)

    @patch("httpx.AsyncClient.get")
    def test_nasa_power_adapter(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "properties": {
                "parameter": {
                    "T2M": {"ANN": 28.5, "JAN": 25.0}
                }
            }
        }
        mock_get.return_value = mock_response

        provider = NasaPowerProvider()
        res = asyncio.run(provider.get_climatology(lat=13.08, lon=80.27))
        self.assertEqual(res.provider, "NASA POWER")
        self.assertIn("T2M", res.annual_averages)

    @patch("httpx.AsyncClient.post")
    def test_gemini_ai_adapter(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "WeatherGPT is active and ready."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Is it raining?")])
        res = asyncio.run(service.generate_weather_response(req))
        self.assertIn("WeatherGPT", res.response_message.content)

    def test_notification_adapters(self):
        exotel = ExotelSMSAdapter(dry_run=True)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Alert",
            message="Cyclone alert",
        )
        status = asyncio.run(exotel.send_notification(payload))
        self.assertEqual(status.status, NotificationStatus.SIMULATED)

        whatsapp = WhatsAppNotificationAdapter(dry_run=True)
        wa_status = asyncio.run(whatsapp.send_notification(payload))
        self.assertEqual(wa_status.status, NotificationStatus.SIMULATED)
