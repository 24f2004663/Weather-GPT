import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from backend.services.alerts.engine import AlertIngestionEngine
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertStatus, AlertSource, AlertUrgency, AlertCertainty, GeographicScope


def create_sample_alert(alert_id="ENGINE-ALERT-1", severity=AlertSeverity.SEVERE, is_active=True, source=AlertSource.SACHET_NDMA):
    return DisasterAlert(
        alert_id=alert_id,
        source=source,
        title="Cyclone Alert",
        event_type="Cyclone",
        severity=severity,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        headline="Severe Cyclone Warning",
        description="Heavy rain expected.",
        affected_area="Coastal Tamil Nadu",
        scope=GeographicScope.DISTRICT,
        affected_states=["Tamil Nadu"],
        affected_districts=["Chennai"],
        issued_time=datetime.now(timezone.utc),
        is_active=is_active,
    )


class TestAlertIngestionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AlertIngestionEngine()
        # Patch supabase_client to use unconfigured (in-memory) mode for unit testing
        self.patcher = patch("backend.services.alerts.engine.supabase_client.is_configured", return_value=False)
        self.mock_is_conf = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @patch("backend.services.alerts.engine.sachet_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.gdacs_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.alert_event_bus.emit_alert_triggered", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.generate_alert_message", new_callable=AsyncMock)
    def test_poll_and_dispatch_new_alert(self, mock_gen_msg, mock_emit, mock_gdacs, mock_sachet):
        sample = create_sample_alert("NEW-001")
        mock_sachet.return_value = [sample]
        mock_gdacs.return_value = []
        mock_gen_msg.return_value = "Formatted Gemini Alert Message"

        res = asyncio.run(self.engine.poll_and_dispatch())

        self.assertEqual(res["total_ingested"], 1)
        self.assertEqual(res["dispatched"], 1)
        self.assertEqual(res["skipped_dedup"], 0)

        mock_emit.assert_called_once()
        emitted_alert = mock_emit.call_args[0][0]
        self.assertEqual(emitted_alert.alert_id, "NEW-001")
        self.assertEqual(emitted_alert.headline, "Formatted Gemini Alert Message")

    @patch("backend.services.alerts.engine.sachet_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.gdacs_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.alert_event_bus.emit_alert_triggered", new_callable=AsyncMock)
    def test_deduplication_skips_unchanged_alert(self, mock_emit, mock_gdacs, mock_sachet):
        sample = create_sample_alert("DEDUP-001")
        mock_sachet.return_value = [sample]
        mock_gdacs.return_value = []

        # First cycle: brand new -> dispatched
        res1 = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res1["dispatched"], 1)
        mock_emit.assert_called_once()

        mock_emit.reset_mock()

        # Second cycle: identical alert -> skipped
        res2 = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res2["dispatched"], 0)
        self.assertEqual(res2["skipped_dedup"], 1)
        mock_emit.assert_not_called()

    @patch("backend.services.alerts.engine.sachet_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.gdacs_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.alert_event_bus.emit_alert_triggered", new_callable=AsyncMock)
    def test_severity_escalation_triggers_redispatch(self, mock_emit, mock_gdacs, mock_sachet):
        alert_moderate = create_sample_alert("ESCALATE-001", severity=AlertSeverity.MODERATE)
        mock_sachet.return_value = [alert_moderate]
        mock_gdacs.return_value = []

        # First cycle: Moderate severity -> dispatched
        res1 = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res1["dispatched"], 1)

        mock_emit.reset_mock()

        # Second cycle: Severity escalated to Extreme -> re-dispatched
        alert_extreme = create_sample_alert("ESCALATE-001", severity=AlertSeverity.EXTREME)
        mock_sachet.return_value = [alert_extreme]

        res2 = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res2["dispatched"], 1)
        self.assertEqual(res2["skipped_dedup"], 0)
        mock_emit.assert_called_once()

    @patch("backend.services.alerts.engine.sachet_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.gdacs_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.alert_event_bus.emit_alert_triggered", new_callable=AsyncMock)
    def test_expired_or_cancelled_alert_skipped(self, mock_emit, mock_gdacs, mock_sachet):
        inactive_alert = create_sample_alert("INACTIVE-001", is_active=False)
        mock_sachet.return_value = [inactive_alert]
        mock_gdacs.return_value = []

        res = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res["dispatched"], 0)
        self.assertEqual(res["inactive_skipped"], 1)
        mock_emit.assert_not_called()

    @patch("backend.services.alerts.engine.sachet_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.gdacs_alert_provider.fetch_active_alerts", new_callable=AsyncMock)
    @patch("backend.services.alerts.engine.alert_event_bus.emit_alert_triggered", new_callable=AsyncMock)
    def test_provider_failure_isolation(self, mock_emit, mock_gdacs, mock_sachet):
        mock_sachet.side_effect = Exception("SACHET feed server down")
        gdacs_alert = create_sample_alert("GDACS-001", source=AlertSource.GDACS)
        mock_gdacs.return_value = [gdacs_alert]

        res = asyncio.run(self.engine.poll_and_dispatch())
        self.assertEqual(res["total_ingested"], 1)
        self.assertEqual(res["dispatched"], 1)
        mock_emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
