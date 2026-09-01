import unittest
import asyncio
import httpx
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.alerts.sachet import SachetNdmaAlertProvider, sachet_alert_provider
from backend.services.ai.tools import execute_weather_tool, GetActiveAlertsArgs
from backend.services.notifications.events import alert_event_bus
from backend.schemas.alerts import AlertSeverity, AlertStatus, AlertUrgency, GeographicScope
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError
from backend.core.cache import cache

SAMPLE_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
  <channel>
    <title>SACHET NDMA Disaster Alert Feed</title>
    <link>https://sachet.ndma.gov.in</link>
    <description>National Disaster Management Authority Official Feed</description>
    <item>
      <title>Cyclone Warning: Severe Cyclone Alert for Coastal Tamil Nadu</title>
      <link>https://sachet.ndma.gov.in/alerts/101</link>
      <pubDate>Sun, 30 Aug 2026 06:00:00 GMT</pubDate>
      <guid>NDMA-ALERT-TN-101</guid>
      <cap:event>Cyclone</cap:event>
      <cap:severity>Extreme</cap:severity>
      <cap:urgency>Immediate</cap:urgency>
      <cap:certainty>Observed</cap:certainty>
      <cap:status>Actual</cap:status>
      <cap:headline>Severe Cyclone Warning along Tamil Nadu Coast</cap:headline>
      <cap:description>Heavy to very heavy rainfall expected across Chennai, Tiruvallur, and Kanchipuram districts.</cap:description>
      <cap:instruction>Fishermen are advised not to venture into sea. Stay indoors in secure shelters.</cap:instruction>
      <cap:effective>2026-08-30T06:00:00+00:00</cap:effective>
      <cap:expires>2026-09-30T18:00:00+00:00</cap:expires>
      <cap:areaDesc>Coastal Tamil Nadu (Chennai, Tiruvallur, Kanchipuram)</cap:areaDesc>
    </item>
    <item>
      <title>Heat Wave Advisory for Rajasthan</title>
      <link>https://sachet.ndma.gov.in/alerts/102</link>
      <pubDate>Sun, 30 Aug 2026 05:00:00 GMT</pubDate>
      <guid>NDMA-ALERT-RJ-102</guid>
      <cap:event>Heat Wave</cap:event>
      <cap:severity>Moderate</cap:severity>
      <cap:urgency>Expected</cap:urgency>
      <cap:certainty>Likely</cap:certainty>
      <cap:status>Actual</cap:status>
      <cap:headline>Heat Wave Conditions in Western Rajasthan</cap:headline>
      <cap:description>Day temperatures likely to exceed 43°C in parts of Rajasthan.</cap:description>
      <cap:instruction>Drink plenty of water and avoid direct sun exposure between 12 PM and 3 PM.</cap:instruction>
      <cap:effective>2026-08-30T05:00:00+00:00</cap:effective>
      <cap:expires>2026-09-30T12:00:00+00:00</cap:expires>
      <cap:areaDesc>Western Rajasthan</cap:areaDesc>
    </item>
    <item>
      <!-- Duplicate item in feed -->
      <title>Cyclone Warning: Severe Cyclone Alert for Coastal Tamil Nadu</title>
      <link>https://sachet.ndma.gov.in/alerts/101</link>
      <pubDate>Sun, 30 Aug 2026 06:00:00 GMT</pubDate>
      <guid>NDMA-ALERT-TN-101</guid>
      <cap:event>Cyclone</cap:event>
      <cap:severity>Extreme</cap:severity>
      <cap:description>Duplicate entry</cap:description>
      <cap:areaDesc>Coastal Tamil Nadu</cap:areaDesc>
    </item>
  </channel>
</rss>"""

EXPIRED_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
  <channel>
    <item>
      <title>Expired Flood Warning</title>
      <guid>NDMA-ALERT-OLD-001</guid>
      <cap:event>Flood</cap:event>
      <cap:severity>Severe</cap:severity>
      <cap:status>Actual</cap:status>
      <cap:effective>2020-01-01T00:00:00+00:00</cap:effective>
      <cap:expires>2020-01-02T00:00:00+00:00</cap:expires>
      <cap:areaDesc>Assam</cap:areaDesc>
    </item>
    <item>
      <title>Cancelled Cyclone Watch</title>
      <guid>NDMA-ALERT-CAN-002</guid>
      <cap:event>Cyclone</cap:event>
      <cap:severity>Severe</cap:severity>
      <cap:status>Cancelled</cap:status>
      <cap:areaDesc>Odisha</cap:areaDesc>
    </item>
  </channel>
</rss>"""

class TestDisasterAlerts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.provider = SachetNdmaAlertProvider()
        asyncio.run(cache.clear())

    # 1. Valid feed parsing & deduplication
    def test_parse_valid_feed_and_deduplication(self):
        alerts = self.provider.parse_feed_xml(SAMPLE_CAP_XML)
        # Should have parsed exactly 2 unique alerts (skipping the 3rd duplicate)
        self.assertEqual(len(alerts), 2)
        
        # Verify Alert 1 (Cyclone in Tamil Nadu)
        tn_alert = alerts[0]
        self.assertEqual(tn_alert.alert_id, "NDMA-ALERT-TN-101")
        self.assertEqual(tn_alert.event_type, "Cyclone")
        self.assertEqual(tn_alert.severity, AlertSeverity.EXTREME)
        self.assertEqual(tn_alert.urgency, AlertUrgency.IMMEDIATE)
        self.assertIn("Tamil Nadu", tn_alert.affected_states)
        self.assertIn("Chennai", tn_alert.affected_districts)
        self.assertEqual(tn_alert.scope, GeographicScope.DISTRICT)
        self.assertTrue(tn_alert.is_active)
        self.assertIn("Stay indoors", tn_alert.instruction)

        # Verify Alert 2 (Heat Wave in Rajasthan)
        rj_alert = alerts[1]
        self.assertEqual(rj_alert.alert_id, "NDMA-ALERT-RJ-102")
        self.assertEqual(rj_alert.event_type, "Heat Wave")
        self.assertEqual(rj_alert.severity, AlertSeverity.MODERATE)
        self.assertIn("Rajasthan", rj_alert.affected_states)
        self.assertEqual(rj_alert.scope, GeographicScope.STATE)

    # 2. Empty XML handling
    def test_parse_empty_feed(self):
        alerts = self.provider.parse_feed_xml("")
        self.assertEqual(alerts, [])
        alerts2 = self.provider.parse_feed_xml("<rss><channel></channel></rss>")
        self.assertEqual(alerts2, [])

    # 3. Malformed XML handling
    def test_parse_malformed_xml_raises_error(self):
        with self.assertRaises(UpstreamProviderError):
            self.provider.parse_feed_xml("<unclosed_tag>This is not valid XML")

    # 4. Expiration & Status handling
    def test_expired_and_cancelled_alerts(self):
        alerts = self.provider.parse_feed_xml(EXPIRED_CAP_XML)
        self.assertEqual(len(alerts), 2)
        # Both should be marked is_active = False
        self.assertFalse(alerts[0].is_active) # Expired
        self.assertFalse(alerts[1].is_active) # Cancelled

    # 5. Geographic location filtering
    def test_geographic_filtering(self):
        with patch.object(self.provider, "fetch_active_alerts") as mock_fetch:
            mock_fetch.return_value = self.provider.parse_feed_xml(SAMPLE_CAP_XML)

            # Query for Chennai (matches Tamil Nadu & Chennai district)
            chennai_alerts = asyncio.run(
                self.provider.get_alerts_for_location(state="Tamil Nadu", district="Chennai")
            )
            self.assertEqual(len(chennai_alerts), 1)
            self.assertEqual(chennai_alerts[0].alert_id, "NDMA-ALERT-TN-101")

            # Query for Jaipur, Rajasthan (matches Rajasthan state)
            rj_alerts = asyncio.run(
                self.provider.get_alerts_for_location(state="Rajasthan", district="Jaipur")
            )
            self.assertEqual(len(rj_alerts), 1)
            self.assertEqual(rj_alerts[0].alert_id, "NDMA-ALERT-RJ-102")

            # Query for Kerala (no alerts match)
            kerala_alerts = asyncio.run(
                self.provider.get_alerts_for_location(state="Kerala", district="Kochi")
            )
            self.assertEqual(len(kerala_alerts), 0)

    # 6. HTTP Upstream Timeout & Provider Error
    @patch("httpx.AsyncClient.get")
    def test_upstream_timeout(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("timeout")
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(self.provider.fetch_active_alerts(force_refresh=True))

    @patch("httpx.AsyncClient.get")
    def test_upstream_500_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.provider.fetch_active_alerts(force_refresh=True))

    # 7. Endpoint GET /api/alerts
    @patch("backend.services.alerts.sachet.sachet_alert_provider.fetch_active_alerts")
    def test_get_alerts_endpoint(self, mock_fetch):
        mock_fetch.return_value = self.provider.parse_feed_xml(SAMPLE_CAP_XML)

        # 7a. Query for Tamil Nadu
        response = self.client.get("/api/alerts?state=Tamil%20Nadu&district=Chennai")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "SACHET/NDMA")
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["highest_severity"], "Extreme")
        self.assertEqual(data["alerts"][0]["event_type"], "Cyclone")

        # 7b. Query with no matches
        res_empty = self.client.get("/api/alerts?state=Kerala")
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(res_empty.json()["total_count"], 0)
        self.assertIsNone(res_empty.json()["highest_severity"])

    # 8. Gemini tool execution: get_active_alerts
    @patch("backend.services.alerts.sachet.sachet_alert_provider.get_alerts_for_location")
    def test_gemini_get_active_alerts_tool(self, mock_loc_alerts):
        mock_loc_alerts.return_value = [self.provider.parse_feed_xml(SAMPLE_CAP_XML)[0]]

        res, provider_name = asyncio.run(
            execute_weather_tool("get_active_alerts", {"state": "Tamil Nadu", "district": "Chennai"})
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(provider_name, "SACHET/NDMA")
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["alerts"][0]["event_type"], "Cyclone")

    # 9. Notification Event Bus Emission
    def test_alert_event_bus_emission(self):
        alert = self.provider.parse_feed_xml(SAMPLE_CAP_XML)[0]
        received = []

        def test_subscriber(event):
            received.append(event)

        alert_event_bus.subscribe(test_subscriber)
        event = asyncio.run(alert_event_bus.emit_alert_triggered(alert))

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].alert.alert_id, "NDMA-ALERT-TN-101")
        self.assertIn("Tamil Nadu", received[0].target_regions)
