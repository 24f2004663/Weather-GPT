import unittest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.alerts.gdacs import GdacsAlertProvider, gdacs_alert_provider
from backend.schemas.alerts import AlertSeverity, GeographicScope, AlertSource

SAMPLE_GDACS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:gdacs="http://www.gdacs.org" xmlns:georss="http://www.georss.org/georss">
  <channel>
    <title>GDACS RSS Feed</title>
    <item>
      <title>Green Flood in Japan</title>
      <guid>https://www.gdacs.org/report.aspx?eventid=1001</guid>
      <pubDate>Wed, 02 Sep 2026 08:00:00 GMT</pubDate>
      <gdacs:eventid>1001</gdacs:eventid>
      <gdacs:eventtype>FL</gdacs:eventtype>
      <gdacs:alertlevel>green</gdacs:alertlevel>
      <gdacs:todate>Wed, 02 Sep 2026 03:00:00 GMT</gdacs:todate>
      <gdacs:country>Japan</gdacs:country>
      <georss:point>35.6762 139.6503</georss:point>
    </item>
    <item>
      <title>Red Tropical Cyclone in India</title>
      <guid>https://www.gdacs.org/report.aspx?eventid=1002</guid>
      <pubDate>Wed, 02 Sep 2026 09:00:00 GMT</pubDate>
      <gdacs:eventid>1002</gdacs:eventid>
      <gdacs:eventtype>TC</gdacs:eventtype>
      <gdacs:alertlevel>red</gdacs:alertlevel>
      <gdacs:todate>Wed, 02 Sep 2026 04:00:00 GMT</gdacs:todate>
      <gdacs:country>India</gdacs:country>
      <georss:point>13.0827 80.2707</georss:point>
    </item>
    <item>
      <title>Orange Earthquake in Chile</title>
      <guid>https://www.gdacs.org/report.aspx?eventid=1003</guid>
      <pubDate>Wed, 02 Sep 2026 07:00:00 GMT</pubDate>
      <gdacs:eventid>1003</gdacs:eventid>
      <gdacs:eventtype>EQ</gdacs:eventtype>
      <gdacs:alertlevel>orange</gdacs:alertlevel>
      <gdacs:country>Chile</gdacs:country>
      <georss:point>-33.4489 -70.6693</georss:point>
    </item>
    <item>
      <title>Orange Flood in India</title>
      <guid>https://www.gdacs.org/report.aspx?eventid=1004</guid>
      <pubDate>Wed, 02 Sep 2026 06:00:00 GMT</pubDate>
      <gdacs:eventid>1004</gdacs:eventid>
      <gdacs:eventtype>FL</gdacs:eventtype>
      <gdacs:alertlevel>orange</gdacs:alertlevel>
      <gdacs:country>India</gdacs:country>
      <georss:point>22.5726 88.3639</georss:point>
    </item>
  </channel>
</rss>"""


class TestGdacsTop7Alerts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.provider = GdacsAlertProvider()

    def test_parse_gdacs_feed_and_india_relevance_ranking(self):
        alerts = self.provider.parse_feed_xml(SAMPLE_GDACS_RSS)
        self.assertEqual(len(alerts), 4)

        top7 = self.provider.get_top_alerts(alerts, max_count=7)
        # Should rank India events first!
        self.assertEqual(top7[0].alert_id, "gdacs-1002")  # Red Cyclone in India (highest)
        self.assertEqual(top7[0].severity, AlertSeverity.EXTREME)
        self.assertEqual(top7[0].affected_area, "India")
        self.assertEqual(top7[0].scope, GeographicScope.NATIONAL)

        self.assertEqual(top7[1].alert_id, "gdacs-1004")  # Orange Flood in India
        self.assertEqual(top7[1].severity, AlertSeverity.SEVERE)

        # Global non-India events come after
        self.assertEqual(top7[2].alert_id, "gdacs-1003")  # Orange Earthquake in Chile
        self.assertEqual(top7[3].alert_id, "gdacs-1001")  # Green Flood in Japan

    def test_todate_in_past_does_not_falsely_expire_live_rss_record(self):
        alerts = self.provider.parse_feed_xml(SAMPLE_GDACS_RSS)
        self.assertTrue(all(a.is_active for a in alerts))
        top7 = self.provider.get_top_alerts(alerts, max_count=7)
        self.assertEqual(len(top7), 4)

    def test_get_top_alerts_respects_max_count(self):
        alerts = self.provider.parse_feed_xml(SAMPLE_GDACS_RSS)
        top2 = self.provider.get_top_alerts(alerts, max_count=2)
        self.assertEqual(len(top2), 2)
        self.assertEqual(top2[0].alert_id, "gdacs-1002")
        self.assertEqual(top2[1].alert_id, "gdacs-1004")

    @patch("backend.services.alerts.gdacs.gdacs_alert_provider.fetch_active_alerts")
    def test_endpoint_get_gdacs_top7(self, mock_fetch):
        mock_fetch.return_value = self.provider.parse_feed_xml(SAMPLE_GDACS_RSS)

        response = self.client.get("/api/alerts/gdacs/top7")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["source"], "GDACS")
        self.assertEqual(data["total_count"], 4)
        self.assertEqual(data["highest_severity"], "Extreme")
        self.assertEqual(data["alerts"][0]["title"], "Red Tropical Cyclone in India")
        self.assertEqual(data["alerts"][0]["polygon_coordinates"], [[13.0827, 80.2707]])


if __name__ == "__main__":
    unittest.main()
