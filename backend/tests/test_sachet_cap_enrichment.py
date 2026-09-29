"""
Tests for SACHET CAP detail enrichment and coordinate-based alert targeting.

The public RSS index carries only title/link/pubDate. Severity, urgency, expiry,
official instructions and a structured areaDesc live in the per-alert CAP document.
Without enrichment every alert normalizes to severity=Unknown with no expiry, which
silently disables severity targeting, expiry filtering and escalation detection.
"""
import unittest
from datetime import datetime, timedelta, timezone

from backend.schemas.alerts import (
    DisasterAlert, AlertSeverity, AlertUrgency, AlertCertainty,
    AlertStatus, AlertSource, GeographicScope,
)
from backend.services.alerts.sachet import sachet_alert_provider as provider


CAP_DOC = """<cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
<cap:identifier>IN-1790656981155013_13</cap:identifier>
<cap:sender>Uttar-Pradesh-SDMA</cap:sender>
<cap:status>Actual</cap:status>
<cap:msgType>Update</cap:msgType>
<cap:info>
<cap:language>en-IN</cap:language>
<cap:event>Flood</cap:event>
<cap:urgency>Expected</cap:urgency>
<cap:severity>Severe</cap:severity>
<cap:certainty>Observed</cap:certainty>
<cap:effective>2026-09-29T08:00:00+05:30</cap:effective>
<cap:expires>2026-09-29T21:00:00+05:30</cap:expires>
<cap:headline>River Ghaghra at Turtipar in Ballia district of Uttar Pradesh.</cap:headline>
<cap:description>Flowing 0.48 m above its Danger Level of 64.01 m.</cap:description>
<cap:instruction>Move to higher ground immediately.</cap:instruction>
<cap:area><cap:areaDesc>Ghaghra, Turtipar, Ballia, Uttar Pradesh</cap:areaDesc></cap:area>
</cap:info>
<cap:info>
<cap:language>HI</cap:language>
<cap:event>Flood</cap:event>
<cap:urgency>Expected</cap:urgency>
<cap:severity>Severe</cap:severity>
<cap:headline>घाघरा नदी भीषण बाढ़ की स्थिति में बह रही है।</cap:headline>
<cap:description>खतरे के निशान से ऊपर।</cap:description>
</cap:info>
</cap:alert>"""


def _rss_alert():
    """An alert as the RSS index alone produces it: no severity, no expiry, no area."""
    return DisasterAlert(
        alert_id="1790656981155013",
        source=AlertSource.SACHET_NDMA,
        title="उत्तर प्रदेश के बलिया ज़िले में घाघरा नदी",
        event_type="Severe Weather",
        severity=AlertSeverity.UNKNOWN,
        urgency=AlertUrgency.UNKNOWN,
        certainty=AlertCertainty.UNKNOWN,
        description="उत्तर प्रदेश के बलिया ज़िले में घाघरा नदी",
        affected_area="उत्तर प्रदेश के बलिया ज़िले में घाघरा नदी",
        issued_time=datetime.utcnow(),
        source_url="https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier=1790656981155013",
    )


class TestCapDocumentParsing(unittest.TestCase):
    def setUp(self):
        self.detail = provider.parse_cap_detail(CAP_DOC)

    def test_reads_structured_fields_from_english_info_block(self):
        self.assertEqual(self.detail["severity"], "Severe")
        self.assertEqual(self.detail["urgency"], "Expected")
        self.assertEqual(self.detail["certainty"], "Observed")
        self.assertEqual(self.detail["event"], "Flood")

    def test_reads_expiry_and_instruction(self):
        self.assertTrue(self.detail["expires"].startswith("2026-09-29T21:00"))
        self.assertEqual(self.detail["instruction"], "Move to higher ground immediately.")

    def test_reads_structured_area_desc(self):
        self.assertEqual(self.detail["area_desc"], "Ghaghra, Turtipar, Ballia, Uttar Pradesh")

    def test_preserves_official_regional_language_block(self):
        self.assertIn("घाघरा", self.detail["headline_local"])
        self.assertEqual(self.detail["local_language"], "hi")

    def test_malformed_document_returns_none_rather_than_raising(self):
        self.assertIsNone(provider.parse_cap_detail("<not-xml"))
        self.assertIsNone(provider.parse_cap_detail(""))

    def test_document_without_info_block_returns_none(self):
        self.assertIsNone(provider.parse_cap_detail(
            '<cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">'
            "<cap:identifier>x</cap:identifier></cap:alert>"))


class TestApplyCapDetail(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
        self.alert = provider.apply_cap_detail(
            _rss_alert(), provider.parse_cap_detail(CAP_DOC), self.now)

    def test_severity_and_urgency_are_classified(self):
        self.assertEqual(self.alert.severity, AlertSeverity.SEVERE)
        self.assertEqual(self.alert.urgency, AlertUrgency.EXPECTED)
        self.assertEqual(self.alert.certainty, AlertCertainty.OBSERVED)
        self.assertEqual(self.alert.original_severity, "Severe")

    def test_expiry_is_populated(self):
        self.assertIsNotNone(self.alert.expires_time)

    def test_official_instruction_is_carried_through(self):
        self.assertEqual(self.alert.instruction, "Move to higher ground immediately.")

    def test_english_area_desc_replaces_regional_headline_scraping(self):
        self.assertEqual(self.alert.affected_area, "Ghaghra, Turtipar, Ballia, Uttar Pradesh")
        self.assertIn("Uttar Pradesh", self.alert.affected_states)

    def test_title_takes_the_english_headline(self):
        """
        `title` comes from the RSS index, which SACHET publishes in the issuing state's
        language, and the UI renders it as the card heading. Measured at 27 of 56 live
        alerts in Telugu/Kannada/Marathi/Hindi, so an English reader saw regional script
        while the English CAP headline sat unused one field away.
        """
        self.assertEqual(self.alert.title, "River Ghaghra at Turtipar in Ballia district of Uttar Pradesh.")
        self.assertNotIn("घाघरा", self.alert.title)

    def test_regional_title_is_still_reachable_for_regional_readers(self):
        """Overwriting `title` must not lose the official regional text."""
        self.assertIn("घाघरा", self.alert.headline_local)

    def test_regional_language_text_is_preserved_verbatim(self):
        self.assertIn("घाघरा", self.alert.headline_local)
        self.assertEqual(self.alert.local_language, "hi")

    def test_expired_alert_is_marked_inactive(self):
        late = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        alert = provider.apply_cap_detail(_rss_alert(), provider.parse_cap_detail(CAP_DOC), late)
        self.assertFalse(alert.is_active, "an alert past its CAP expiry must not read as live")

    def test_unexpired_alert_stays_active(self):
        self.assertTrue(self.alert.is_active)

    def test_cancelled_status_overrides_expiry(self):
        doc = CAP_DOC.replace("<cap:status>Actual</cap:status>", "<cap:status>Cancelled</cap:status>")
        alert = provider.apply_cap_detail(_rss_alert(), provider.parse_cap_detail(doc), self.now)
        self.assertFalse(alert.is_active)


class TestCoordinateResolution(unittest.TestCase):
    def test_known_city_resolves_to_its_state(self):
        for lat, lon, expected in [
            (13.0878, 80.2785, "Tamil Nadu"), (25.5941, 85.1376, "Bihar"),
            (19.0760, 72.8777, "Maharashtra"), (26.8467, 80.9462, "Uttar Pradesh"),
            (22.5726, 88.3639, "West Bengal"), (20.2961, 85.8245, "Odisha"),
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, provider.states_for_point(lat, lon))

    def test_point_outside_india_resolves_to_nothing(self):
        for lat, lon in [(6.92, 79.86), (27.70, 85.30), (0.0, 0.0), (51.5, -0.12)]:
            with self.subTest(point=(lat, lon)):
                self.assertEqual(provider.states_for_point(lat, lon), [])


class TestCoordinateTargeting(unittest.IsolatedAsyncioTestCase):
    """Coordinates must narrow results correctly, and must never silently zero them."""

    def _alerts(self):
        base = dict(source=AlertSource.SACHET_NDMA, event_type="Flood",
                    issued_time=datetime.utcnow(), is_active=True)
        return [
            DisasterAlert(alert_id="bihar-1", title="Bihar flood", description="Bihar flood",
                          affected_area="Patna, Bihar", affected_states=["Bihar"],
                          scope=GeographicScope.STATE, **base),
            DisasterAlert(alert_id="tn-1", title="TN storm", description="TN storm",
                          affected_area="Chennai, Tamil Nadu", affected_states=["Tamil Nadu"],
                          scope=GeographicScope.STATE, **base),
        ]

    async def asyncSetUp(self):
        self._orig = provider.fetch_active_alerts
        alerts = self._alerts()

        async def fake(force_refresh=False):
            return alerts
        provider.fetch_active_alerts = fake

    async def asyncTearDown(self):
        provider.fetch_active_alerts = self._orig

    async def test_coordinates_select_the_right_state(self):
        res = await provider.get_alerts_for_location(lat=25.5941, lon=85.1376)  # Patna
        self.assertEqual([a.alert_id for a in res], ["bihar-1"])

    async def test_coordinates_exclude_unrelated_states(self):
        res = await provider.get_alerts_for_location(lat=19.0760, lon=72.8777)  # Mumbai
        self.assertEqual(res, [])

    async def test_unresolvable_coordinates_fail_open_not_closed(self):
        """
        Regression: coordinates outside the known boxes previously matched nothing,
        making a coordinates-only query strictly worse than no filter at all.
        """
        res = await provider.get_alerts_for_location(lat=6.92, lon=79.86)  # Colombo
        self.assertEqual(len(res), 2, "unresolvable coords must not narrow the result set")

    async def test_no_filter_returns_everything(self):
        self.assertEqual(len(await provider.get_alerts_for_location()), 2)


if __name__ == "__main__":
    unittest.main()
