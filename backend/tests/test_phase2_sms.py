import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.notifications.orchestrator import notification_orchestrator
from backend.services.notifications.twilio_sms import TwilioSMSAdapter
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.schemas.notifications import (
    NotificationSubscription,
    NotificationChannel,
    SubscriptionRequest,
    AlertSeverity,
    NotificationPayload,
    NotificationStatus,
)
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertSource, GeographicScope


class TestPhase2SMSEmergencyAlerts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # A. SMS adapter success using mocked provider boundary
    def test_twilio_sms_adapter_success_mocked(self):
        adapter = TwilioSMSAdapter(
            account_sid="ACmock123",
            auth_token="auth_mock",
            from_number="+15005550006",
            dry_run=False
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS"
        )
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"sid": "SM_mock_123", "status": "queued"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(adapter.send_notification(payload))
            self.assertEqual(status.status, NotificationStatus.SENT)
            self.assertEqual(status.provider_reference, "SM_mock_123")

    # B. SMS adapter provider failure
    def test_twilio_sms_adapter_failure(self):
        adapter = TwilioSMSAdapter(
            account_sid="ACmock123",
            auth_token="auth_mock",
            from_number="+15005550006",
            dry_run=False
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS"
        )
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"code": 21211, "message": "Invalid To Phone Number"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(adapter.send_notification(payload))
            self.assertEqual(status.status, NotificationStatus.FAILED)
            self.assertIn("Invalid To Phone Number", status.error_message)

    # C. SMS missing configuration
    def test_sms_missing_configuration_fails_safely(self):
        adapter = TwilioSMSAdapter(
            account_sid="",
            auth_token="",
            from_number="",
            dry_run=False
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS"
        )
        status = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(status.status, NotificationStatus.FAILED)
        self.assertIn("not configured", status.error_message)

    # D. SMS routing when subscriber has SMS enabled
    def test_sms_routing_when_subscriber_enabled(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-1",
            user_identifier="user_sms_enabled",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True
        )
        alert = DisasterAlert(
            alert_id="alert-sms-1",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL
        )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            event = MagicMock(alert=alert)
            records = asyncio.run(notification_orchestrator.handle_alert_event(event))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].channel, NotificationChannel.SMS)

    # E. SMS not routed when SMS is disabled
    def test_sms_not_routed_when_sms_disabled(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-2",
            user_identifier="user_sms_disabled",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.WHATSAPP],  # SMS not in channels
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True
        )
        alert = DisasterAlert(
            alert_id="alert-sms-2",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL
        )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            event = MagicMock(alert=alert)
            records = asyncio.run(notification_orchestrator.handle_alert_event(event))
            channels_sent = [r.channel for r in records]
            self.assertNotIn(NotificationChannel.SMS, channels_sent)

    # F. SMS not routed when user is not opted in
    def test_sms_not_routed_when_user_not_opted_in(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-3",
            user_identifier="user_opted_out",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=False  # Opted out
        )
        alert = DisasterAlert(
            alert_id="alert-sms-3",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL
        )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            event = MagicMock(alert=alert)
            records = asyncio.run(notification_orchestrator.handle_alert_event(event))
            self.assertEqual(len(records), 0)

    # G. SMS not routed when severity is below threshold
    def test_sms_not_routed_when_severity_below_threshold(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-4",
            user_identifier="user_high_threshold",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            min_severity_threshold=AlertSeverity.EXTREME,  # User wants Extreme only
            is_opted_in=True
        )
        alert_mod = DisasterAlert(
            alert_id="alert-sms-4",
            source=AlertSource.SACHET_NDMA,
            title="Moderate Rain Warning",
            event_type="Rain",
            severity=AlertSeverity.MODERATE,  # Moderate severity
            description="Moderate rainfall",
            affected_area="India",
            scope=GeographicScope.NATIONAL
        )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            event = MagicMock(alert=alert_mod)
            records = asyncio.run(notification_orchestrator.handle_alert_event(event))
            self.assertEqual(len(records), 0)

    # H. SMS geographic mismatch
    def test_sms_geographic_mismatch(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-5",
            user_identifier="user_mumbai",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            target_states=["Maharashtra"],
            target_districts=["Mumbai"],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True
        )
        alert_chennai = DisasterAlert(
            alert_id="alert-sms-5",
            source=AlertSource.SACHET_NDMA,
            title="Chennai Flood Warning",
            event_type="Flood",
            severity=AlertSeverity.SEVERE,
            description="Heavy rain in Chennai",
            affected_area="Chennai, Tamil Nadu",
            scope=GeographicScope.DISTRICT,
            affected_states=["Tamil Nadu"],
            affected_districts=["Chennai"]
        )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            event = MagicMock(alert=alert_chennai)
            records = asyncio.run(notification_orchestrator.handle_alert_event(event))
            self.assertEqual(len(records), 0)

    # I. SMS channel failure does not block WhatsApp or Web Push
    def test_sms_failure_does_not_block_whatsapp_or_webpush(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-6",
            user_identifier="user_multi_channel",
            phone_number="+919876543210",
            whatsapp_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS, NotificationChannel.WHATSAPP, NotificationChannel.WEB_PUSH],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True
        )
        alert = DisasterAlert(
            alert_id="alert-sms-6",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL
        )

        # Mock SMS dispatch to throw an exception
        async def mock_dispatch(channel, payload):
            if channel == NotificationChannel.SMS:
                raise Exception("SMS Provider Network Failure")
            from backend.schemas.notifications import DeliveryStatus
            return DeliveryStatus(
                notification_id="norm-1",
                channel=channel,
                recipient=payload.recipient_identifier,
                status=NotificationStatus.SENT
            )

        with patch("backend.db.supabase.supabase_client.get_all_active_subscriptions", AsyncMock(return_value=[sub])):
            with patch.object(notification_orchestrator, "_dispatch_to_adapter", side_effect=mock_dispatch):
                event = MagicMock(alert=alert)
                records = asyncio.run(notification_orchestrator.handle_alert_event(event))
                sent_channels = [r.channel for r in records if r.status == NotificationStatus.SENT]
                self.assertIn(NotificationChannel.WHATSAPP, sent_channels)
                self.assertIn(NotificationChannel.WEB_PUSH, sent_channels)

    # K. Normal website chat does not trigger SMS
    def test_normal_chat_endpoint_does_not_trigger_sms(self):
        with patch.object(notification_orchestrator, "handle_alert_event") as mock_handle:
            response = self.client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "What is the weather in Chennai?"}]
            })
            self.assertEqual(response.status_code, 200)
            mock_handle.assert_not_called()

    # M. SMS test endpoint uses the exact fixed test message
    def test_sms_test_endpoint_uses_fixed_message(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-sms",
            user_identifier="sms_test_user",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            is_opted_in=True
        )

        with patch.object(notification_orchestrator, "get_subscription", AsyncMock(return_value=sub)):
            res = self.client.post("/api/notifications/test", json={
                "user_id": "sms_test_user",
                "channel": "SMS"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["channel"], "SMS")
            self.assertEqual(data["alert_id"], "TEST-NOTIFICATION")

    # N. SMS test endpoint cannot target arbitrary recipients
    def test_sms_test_endpoint_cannot_target_arbitrary_recipients(self):
        # Non-existent user
        with patch.object(notification_orchestrator, "get_subscription", AsyncMock(return_value=None)):
            res = self.client.post("/api/notifications/test", json={
                "user_id": "unknown_attacker_user",
                "channel": "SMS"
            })
            self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
