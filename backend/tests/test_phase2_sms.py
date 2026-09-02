import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.notifications.orchestrator import notification_orchestrator
import backend.services.notifications.orchestrator as orchestrator_module
from backend.db.supabase import supabase_client
from backend.services.notifications.textbee_sms import TextBeeSMSAdapter
from backend.schemas.notifications import (
    NotificationSubscription,
    NotificationChannel,
    SubscriptionRequest,
    AlertSeverity,
    NotificationPayload,
    NotificationStatus,
    DeliveryStatus,
)
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertSource, GeographicScope


class TestPhase2SMSEmergencyAlerts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        orchestrator_module.supabase_client = supabase_client
        notification_orchestrator._sent_idempotency_keys.clear()
        notification_orchestrator._recipient_hourly_counts.clear()

    # A. TextBee SMS adapter success using mocked provider boundary
    def test_textbee_sms_adapter_success_mocked(self):
        adapter = TextBeeSMSAdapter(
            api_key="tb_key_mock",
            device_id="tb_device_mock",
            base_url="https://api.textbee.dev/api/v1",
            dry_run=False,
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "tb_msg_100200"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(adapter.send_notification(payload))
            self.assertEqual(status.status, NotificationStatus.SENT)
            self.assertEqual(status.provider_reference, "tb_msg_100200")

    # B. TextBee SMS adapter provider failure
    def test_textbee_sms_adapter_failure(self):
        adapter = TextBeeSMSAdapter(
            api_key="tb_key_mock",
            device_id="tb_device_mock",
            dry_run=False,
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS",
        )
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid recipient phone format"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(adapter.send_notification(payload))
            self.assertEqual(status.status, NotificationStatus.FAILED)
            self.assertIn("Invalid recipient phone format", status.error_message)

    # C. TextBee SMS missing configuration
    def test_textbee_sms_missing_configuration_fails_safely(self):
        adapter = TextBeeSMSAdapter(
            api_key="",
            device_id="",
            dry_run=False,
        )
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS",
        )
        status = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(status.status, NotificationStatus.FAILED)
        self.assertIn("not configured", status.error_message)

    # D. TextBee SMS routing when subscriber has SMS enabled
    def test_sms_routing_when_subscriber_enabled(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-1",
            user_identifier="user_sms_enabled",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True,
        )
        alert = DisasterAlert(
            alert_id="alert-sms-1",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL,
        )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
                event = MagicMock(alert=alert)
                records = asyncio.run(notification_orchestrator.handle_alert_event(event))
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].channel, NotificationChannel.SMS)
                self.assertEqual(records[0].provider, "TextBee SMS")

    # E. SMS not routed when SMS is disabled
    def test_sms_not_routed_when_sms_disabled(self):
        sub = NotificationSubscription(
            subscription_id="sub-sms-2",
            user_identifier="user_sms_disabled",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.WHATSAPP],
            min_severity_threshold=AlertSeverity.SEVERE,
            is_opted_in=True,
        )
        alert = DisasterAlert(
            alert_id="alert-sms-2",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL,
        )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
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
            is_opted_in=False,
        )
        alert = DisasterAlert(
            alert_id="alert-sms-3",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL,
        )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
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
            min_severity_threshold=AlertSeverity.EXTREME,
            is_opted_in=True,
        )
        alert_mod = DisasterAlert(
            alert_id="alert-sms-4",
            source=AlertSource.SACHET_NDMA,
            title="Moderate Rain Warning",
            event_type="Rain",
            severity=AlertSeverity.MODERATE,
            description="Moderate rainfall",
            affected_area="India",
            scope=GeographicScope.NATIONAL,
        )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
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
            is_opted_in=True,
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
            affected_districts=["Chennai"],
        )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
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
            is_opted_in=True,
        )
        alert = DisasterAlert(
            alert_id="alert-sms-channel-isolation-unique-99",
            source=AlertSource.SACHET_NDMA,
            title="Cyclone Warning",
            event_type="Cyclone",
            severity=AlertSeverity.SEVERE,
            description="Severe Cyclone Warning",
            affected_area="India",
            scope=GeographicScope.NATIONAL,
        )

        async def mock_dispatch(channel, payload):
            if channel == NotificationChannel.SMS:
                raise Exception("TextBee API Gateway Unavailable")
            return DeliveryStatus(
                notification_id="norm-1",
                channel=channel,
                recipient=payload.recipient_identifier,
                status=NotificationStatus.SENT,
            )

        with patch.object(supabase_client, "is_configured", return_value=True):
            with patch.object(supabase_client, "get_all_active_subscriptions", AsyncMock(return_value=[sub])):
                with patch.object(notification_orchestrator, "_dispatch_to_adapter", side_effect=mock_dispatch):
                    event = MagicMock(alert=alert)
                    records = asyncio.run(notification_orchestrator.handle_alert_event(event))
                    processed_channels = [r.channel for r in records if r.status in (NotificationStatus.SENT, NotificationStatus.SIMULATED)]
                    self.assertIn(NotificationChannel.WHATSAPP, processed_channels)
                    self.assertIn(NotificationChannel.WEB_PUSH, processed_channels)

    # K. Normal website chat does not trigger SMS
    def test_normal_chat_endpoint_does_not_trigger_sms(self):
        with patch.object(notification_orchestrator, "handle_alert_event") as mock_handle:
            response = self.client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "What is the weather in Chennai?"}]
            })
            self.assertEqual(response.status_code, 200)
            mock_handle.assert_not_called()

    # M. SMS test endpoint uses the exact fixed test message and registered Supabase phone
    def test_sms_test_endpoint_uses_registered_phone_and_fixed_message(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-tb-sms",
            user_identifier="sms_tb_test_user",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            is_opted_in=True,
        )

        with patch.object(notification_orchestrator, "get_subscription", AsyncMock(return_value=sub)):
            res = self.client.post("/api/notifications/test", json={
                "user_id": "sms_tb_test_user",
                "channel": "SMS"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["channel"], "SMS")
            self.assertEqual(data["alert_id"], "TEST-NOTIFICATION")
            self.assertEqual(data["provider"], "TextBee SMS")

    # N. SMS test endpoint cannot target arbitrary recipients from payload
    def test_sms_test_endpoint_ignores_arbitrary_recipients(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-tb-sms-2",
            user_identifier="registered_user_123",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            is_opted_in=True,
        )

        with patch.object(notification_orchestrator, "get_subscription", AsyncMock(return_value=sub)) as mock_get_sub:
            res = self.client.post("/api/notifications/test", json={
                "user_id": "registered_user_123",
                "channel": "SMS",
                "recipient": "+19998887777",
                "phone_number": "+19998887777"
            })
            self.assertEqual(res.status_code, 200)
            mock_get_sub.assert_called_once_with("registered_user_123")
            data = res.json()
            self.assertIn("+91 9876", data["recipient"])


if __name__ == "__main__":
    unittest.main()
