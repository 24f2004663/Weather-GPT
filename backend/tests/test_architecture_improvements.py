import unittest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock

import httpx

from backend.core.cache import cache as global_cache, InMemoryTTLCache
from backend.core.http_client import HTTPClientManager
from backend.core.errors import WeatherGPTError
from backend.services.weather.nasa_power import NasaPowerProvider, _make_nasa_cache_key
from backend.services.weather.open_meteo import OpenMeteoProvider
from backend.services.alerts.sachet import SachetNdmaAlertProvider
from backend.services.audio.stt import GroqWhisperService, MAX_AUDIO_BYTES
from backend.services.notifications.orchestrator import NotificationOrchestrator
from backend.services.ai.session import SessionStore
from backend.services.ai.gemini import GeminiAIService
from backend.schemas.chat import ChatRequest, ChatMessage

class TestArchitectureImprovements(unittest.TestCase):

    def setUp(self):
        asyncio.run(global_cache.clear())

    # -----------------------------------------------------------------------
    # 1. HTTP Client Connection Manager
    # -----------------------------------------------------------------------
    def test_http_client_manager_reuse(self):
        manager = HTTPClientManager()
        client1 = asyncio.run(manager.get_client())
        client2 = asyncio.run(manager.get_client())
        self.assertIs(client1, client2)
        asyncio.run(manager.close())
        self.assertTrue(client1.is_closed)

    # -----------------------------------------------------------------------
    # 2. NASA POWER 1dp Coordinate Normalization & Cache Key
    # -----------------------------------------------------------------------
    def test_nasa_power_cache_key_normalization(self):
        # 13.0827 and 13.0878 should normalize to 13.1
        key1 = _make_nasa_cache_key(13.0827, 80.2707)
        key2 = _make_nasa_cache_key(13.0878, 80.2712)
        self.assertEqual(key1, key2)
        self.assertEqual(key1, "climate:nasa:13.1:80.3")

    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_nasa_power_stale_fallback(self, mock_get_client):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "properties": {
                "parameter": {
                    "T2M": {"ANN": 28.5, "JAN": 25.0, "FEB": 26.0, "MAR": 28.0, "APR": 30.0, "MAY": 32.0, "JUN": 31.0, "JUL": 30.0, "AUG": 29.5, "SEP": 29.0, "OCT": 28.0, "NOV": 26.5, "DEC": 25.0},
                    "PRECTOTCORR": {"ANN": 3.5},
                    "ALLSKY_SFC_SW_DWN": {"ANN": 5.2},
                    "RH2M": {"ANN": 65.0},
                    "WS10M": {"ANN": 4.1}
                }
            }
        }
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = NasaPowerProvider()
        # First call populates cache
        res = asyncio.run(provider.get_climatology(13.0827, 80.2707))
        self.assertFalse(res.cached)

        # Make mock fail to simulate timeout
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        
        # Second call with slightly different coords (same 1dp bin) hits fresh cache
        res_fresh = asyncio.run(provider.get_climatology(13.0849, 80.2710))
        self.assertTrue(res_fresh.cached)

    # -----------------------------------------------------------------------
    # 3. Geocoding Count-Agnostic Normalization
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_geocoding_count_agnostic_cache(self, mock_get_client):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"id": 1, "name": "Chennai", "latitude": 13.0827, "longitude": 80.2707, "country": "India"},
                {"id": 2, "name": "Chennai Central", "latitude": 13.0820, "longitude": 80.2750, "country": "India"},
                {"id": 3, "name": "Chennai Port", "latitude": 13.0900, "longitude": 80.2900, "country": "India"},
                {"id": 4, "name": "Chennai Airport", "latitude": 12.9900, "longitude": 80.1693, "country": "India"},
                {"id": 5, "name": "Chennai Beach", "latitude": 13.0920, "longitude": 80.2930, "country": "India"},
            ]
        }
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = OpenMeteoProvider()
        # First query with count=5
        res5 = asyncio.run(provider.resolve_location("Chennai", count=5))
        self.assertEqual(len(res5), 5)
        self.assertEqual(mock_client.get.call_count, 1)

        # Second query with count=1 should be served from cache without extra HTTP call
        res1 = asyncio.run(provider.resolve_location("Chennai", count=1))
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0].name, "Chennai")
        self.assertEqual(mock_client.get.call_count, 1)

    # -----------------------------------------------------------------------
    # 4. SACHET Alert Emergency Staleness
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_sachet_alert_fresh_and_stale(self, mock_get_client):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>SACHET Disaster Alert Feed</title>
            <item>
              <identifier>ALERT-TEST-001</identifier>
              <title>Cyclone Warning Coastal Tamil Nadu</title>
              <description>Severe cyclonic storm</description>
              <severity>Extreme</severity>
              <urgency>Immediate</urgency>
              <certainty>Observed</certainty>
              <areaDesc>Chennai, Tamil Nadu</areaDesc>
            </item>
          </channel>
        </rss>"""
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = SachetNdmaAlertProvider()
        alerts = asyncio.run(provider.fetch_active_alerts())
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_id, "ALERT-TEST-001")

        # Now simulate network error: should return stale alerts within emergency window
        mock_client.get.side_effect = httpx.ConnectError("Network down")
        alerts_stale = asyncio.run(provider.fetch_active_alerts())
        self.assertEqual(len(alerts_stale), 1)

    # -----------------------------------------------------------------------
    # 5. Groq STT File Size Validation
    # -----------------------------------------------------------------------
    def test_stt_size_validation(self):
        stt = GroqWhisperService(api_key="mock_key")
        oversized = b"x" * (MAX_AUDIO_BYTES + 1024)
        with self.assertRaises(WeatherGPTError) as ctx:
            asyncio.run(stt.transcribe_audio(oversized))
        self.assertIn("exceeds maximum size of 25MB", str(ctx.exception))

    # -----------------------------------------------------------------------
    # 6. Notification Rate Limit Cleanup
    # -----------------------------------------------------------------------
    def test_notification_rate_limit_cleanup(self):
        orchestrator = NotificationOrchestrator()
        # Add old timestamps
        old_time = time.time() - 4000.0
        orchestrator._recipient_hourly_counts["+919999999999"] = [old_time]
        orchestrator._sent_idempotency_keys["old_key"] = old_time - 100000.0

        purged = asyncio.run(orchestrator.cleanup_expired_tracking())
        self.assertGreaterEqual(purged, 1)
        self.assertNotIn("+919999999999", orchestrator._recipient_hourly_counts)
        self.assertNotIn("old_key", orchestrator._sent_idempotency_keys)

    # -----------------------------------------------------------------------
    # 7. Session Store Cleanup
    # -----------------------------------------------------------------------
    def test_session_store_cleanup(self):
        store = SessionStore(session_ttl_seconds=1)
        asyncio.run(store.append_messages("test_session", [ChatMessage(role="user", content="Hello")]))
        self.assertEqual(store.active_sessions_count(), 1)
        time.sleep(1.1)
        purged = asyncio.run(store.cleanup_expired())
        self.assertEqual(purged, 1)
        self.assertEqual(store.active_sessions_count(), 0)

if __name__ == "__main__":
    unittest.main()
