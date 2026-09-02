import unittest
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from unittest.mock import patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient

from backend.main import app, notification_orchestrator
from backend.core.config import settings
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertUrgency, AlertCertainty, AlertStatus, GeographicScope
from backend.schemas.chat import ChatResponse, ChatMessage
from backend.schemas.notifications import (
    NotificationSubscription,
    SubscriptionRequest,
    NotificationChannel,
    NotificationStatus,
    NotificationPayload,
    DisasterAlertTriggeredEvent,
    normalize_phone_number,
    mask_phone_number,
)
from backend.services.notifications.whatsapp import WhatsAppNotificationAdapter
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.services.notifications.voice import ExotelVoiceAdapter
from backend.services.notifications.twilio_sms import TwilioSMSAdapter
from backend.services.notifications.twilio_voice import TwilioVoiceAdapter
from backend.services.notifications.twilio_whatsapp import TwilioWhatsAppAdapter
from backend.services.notifications.web_push import WebPushNotificationAdapter
from backend.services.notifications.orchestrator import NotificationOrchestrator
from backend.services.notifications.formatter import format_whatsapp_alert, format_sms_alert, format_voice_script

def create_sample_alert(severity=AlertSeverity.EXTREME, state="Tamil Nadu", district="Chennai"):
    return DisasterAlert(
        alert_id="ALERT-TEST-001",
        title="Cyclone Warning",
        event_type="Cyclone",
        severity=severity,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        headline="Severe Cyclone Warning",
        description="Very heavy rain expected.",
        instruction="Stay indoors in secure shelters.",
        affected_area=f"{state} ({district})",
        scope=GeographicScope.DISTRICT,
        affected_states=[state],
        affected_districts=[district],
        issued_time=datetime.utcnow(),
        is_active=True
    )

class MockSupabaseClient:
    def __init__(self):
        self._db: Dict[str, NotificationSubscription] = {}
        self.url = "https://mock.supabase.co"
        self.key = "mock_key"
        self.has_credentials = True

    def is_configured(self) -> bool:
        return True

    async def save_subscription(self, sub: NotificationSubscription) -> bool:
        self._db[sub.user_identifier] = sub
        return True

    async def get_subscription(self, user_identifier: str) -> Optional[NotificationSubscription]:
        return self._db.get(user_identifier)

    async def delete_subscription(self, user_identifier: str) -> bool:
        if user_identifier in self._db:
            del self._db[user_identifier]
            return True
        return False

    async def is_phone_subscribed(self, phone: str) -> bool:
        clean_target = "".join(c for c in phone if c.isdigit())
        if not clean_target:
            return False
        for sub in self._db.values():
            if not sub.is_opted_in:
                continue
            for cp in [sub.phone_number, sub.whatsapp_number, sub.user_identifier]:
                if not cp:
                    continue
                clean_cp = "".join(c for c in str(cp) if c.isdigit())
                if clean_cp == clean_target:
                    return True
                if len(clean_cp) >= 10 and len(clean_target) >= 10 and clean_cp[-10:] == clean_target[-10:]:
                    return True
        return False

    async def get_all_active_subscriptions(self) -> List[NotificationSubscription]:
        return [s for s in self._db.values() if s.is_opted_in]

class TestNotificationServices(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_supabase = MockSupabaseClient()
        self.patcher = patch("backend.services.notifications.orchestrator.supabase_client", self.mock_supabase)
        self.patcher.start()
        self.orchestrator = NotificationOrchestrator()

    def tearDown(self):
        self.patcher.stop()

    # 1. WhatsApp Dry Run & Live Mocks
    def test_whatsapp_dry_run(self):
        adapter = WhatsAppNotificationAdapter(dry_run=True)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.WHATSAPP,
            title="Alert",
            message="Test Cyclone Alert"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.is_simulated)
        self.assertTrue(res.provider_reference.startswith("sim_wa_"))

    @patch("httpx.AsyncClient.post")
    def test_whatsapp_mocked_http_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "wamid.12345"}]}
        mock_post.return_value = mock_resp

        adapter = WhatsAppNotificationAdapter(api_token="mock_token", phone_number_id="123456", dry_run=False)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.WHATSAPP,
            title="Alert",
            message="Test Alert"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SENT)
        self.assertEqual(res.provider_reference, "wamid.12345")

    @patch("httpx.AsyncClient.post")
    def test_whatsapp_mocked_429_rate_limit(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"
        mock_post.return_value = mock_resp

        adapter = WhatsAppNotificationAdapter(api_token="mock_token", phone_number_id="123456", dry_run=False)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.WHATSAPP,
            title="Alert",
            message="Test Alert"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.RETRYING)

    # 2. Exotel SMS Dry Run & Mocked
    def test_exotel_sms_dry_run(self):
        adapter = ExotelSMSAdapter(dry_run=True)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Alert",
            message="SMS Warning"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.provider_reference.startswith("sim_sms_"))

    @patch("httpx.AsyncClient.post")
    def test_exotel_sms_mocked_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"SMSMessage": {"Sid": "exo_sms_789"}}
        mock_post.return_value = mock_resp

        adapter = ExotelSMSAdapter(account_sid="acc_1", api_key="k_1", api_token="t_1", dry_run=False)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Alert",
            message="SMS Warning"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SENT)
        self.assertEqual(res.provider_reference, "exo_sms_789")

    # 3. Exotel Voice / IVR Dry Run & Mocked
    def test_exotel_voice_dry_run(self):
        adapter = ExotelVoiceAdapter(dry_run=True)
        payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.VOICE_IVR,
            title="Alert",
            message="Spoken Alert"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.provider_reference.startswith("sim_call_"))

    # 4. Web Push Adapter Dry Run & Live Key Guard
    def test_web_push_dry_run(self):
        adapter = WebPushNotificationAdapter(dry_run=True)
        payload = NotificationPayload(
            recipient_identifier="user_web_token_123",
            channel=NotificationChannel.WEB_PUSH,
            title="Cyclone Warning",
            message="Extreme Cyclone Warning issued for Chennai.",
            alert_id="ALERT-001"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.is_simulated)
        self.assertTrue(res.provider_reference.startswith("sim_push_"))

    def test_web_push_missing_keys_guard(self):
        adapter = WebPushNotificationAdapter(public_key=None, private_key=None, dry_run=False)
        payload = NotificationPayload(
            recipient_identifier="user_web_token_123",
            channel=NotificationChannel.WEB_PUSH,
            title="Cyclone Warning",
            message="Alert message",
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.FAILED)
        self.assertIn("VAPID keys not configured", res.error_message)

    # 5. Phone Number Normalization & Masking
    def test_phone_normalization_and_masking(self):
        self.assertEqual(normalize_phone_number("+91 98765 43210"), "+919876543210")
        self.assertEqual(normalize_phone_number("9876543210"), "9876543210")
        with self.assertRaises(ValueError):
            normalize_phone_number("123") # Too short

        masked = mask_phone_number("+919876543210")
        self.assertEqual(masked, "+91 9876 ****10")

    # 6. Orchestrator Subscription Management & Validation
    def test_subscription_lifecycle(self):
        req = SubscriptionRequest(
            user_identifier="user_123",
            phone_number="+919876543210",
            preferred_language="ta",
            enabled_channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
            min_severity_threshold=AlertSeverity.SEVERE,
            target_states=["Tamil Nadu"],
            target_districts=["Chennai"]
        )
        sub = asyncio.run(self.orchestrator.save_subscription(req))
        self.assertEqual(sub.user_identifier, "user_123")
        self.assertEqual(len(sub.enabled_channels), 2)

        fetched = asyncio.run(self.orchestrator.get_subscription("user_123"))
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.preferred_language, "ta")

        deleted = asyncio.run(self.orchestrator.delete_subscription("user_123"))
        self.assertTrue(deleted)
        self.assertIsNone(asyncio.run(self.orchestrator.get_subscription("user_123")))

    # 7. Orchestrator Severity & Geographic Filtering
    def test_orchestrator_severity_and_geo_filter(self):
        asyncio.run(self.orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="user_chennai",
            phone_number="+919876543210",
            whatsapp_number="+919876543210",
            enabled_channels=[NotificationChannel.WHATSAPP],
            min_severity_threshold=AlertSeverity.SEVERE,
            target_states=["Tamil Nadu"],
            target_districts=["Chennai"]
        )))

        asyncio.run(self.orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="user_mumbai",
            phone_number="+919999999999",
            whatsapp_number="+919999999999",
            enabled_channels=[NotificationChannel.WHATSAPP],
            min_severity_threshold=AlertSeverity.MODERATE,
            target_states=["Maharashtra"],
            target_districts=["Mumbai"]
        )))

        # Event A: Extreme Cyclone in Chennai
        alert_chennai = create_sample_alert(severity=AlertSeverity.EXTREME, state="Tamil Nadu", district="Chennai")
        records_a = asyncio.run(self.orchestrator.handle_alert_event(DisasterAlertTriggeredEvent(
            event_id="evt_1",
            alert=alert_chennai
        )))

        # Should match Chennai user only
        self.assertEqual(len(records_a), 1)

        # Event B: Minor Heat Wave in Chennai (below threshold)
        alert_minor = create_sample_alert(severity=AlertSeverity.MINOR, state="Tamil Nadu", district="Chennai")
        alert_minor.alert_id = "ALERT-MINOR-002"
        records_b = asyncio.run(self.orchestrator.handle_alert_event(DisasterAlertTriggeredEvent(
            event_id="evt_2",
            alert=alert_minor
        )))
        self.assertEqual(len(records_b), 0)

    # 8. Orchestrator Idempotency (Duplicate Suppression & Concurrency)
    def test_orchestrator_idempotency(self):
        asyncio.run(self.orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="user_dup",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.WHATSAPP],
            min_severity_threshold=AlertSeverity.SEVERE,
            target_states=["Tamil Nadu"]
        )))

        alert = create_sample_alert()
        # First trigger
        rec_1 = asyncio.run(self.orchestrator.handle_alert_event(DisasterAlertTriggeredEvent(
            event_id="evt_101",
            alert=alert
        )))
        self.assertEqual(len(rec_1), 1)

        # Immediate second trigger with same alert_id
        rec_2 = asyncio.run(self.orchestrator.handle_alert_event(DisasterAlertTriggeredEvent(
            event_id="evt_102",
            alert=alert
        )))
        self.assertEqual(len(rec_2), 0) # Suppressed

    # 9. Multilingual Message Formatting
    def test_multilingual_formatting(self):
        alert = create_sample_alert()
        msg_en = format_whatsapp_alert(alert, language="en")
        self.assertIn("WEATHERGPT OFFICIAL DISASTER ALERT", msg_en)

        msg_hi = format_whatsapp_alert(alert, language="hi")
        self.assertIn("आधिकारिक आपदा चेतावनी", msg_hi)

        msg_ta = format_whatsapp_alert(alert, language="ta")
        self.assertIn("அதிகாரப்பூர்வ பேரிடர் எச்சரிக்கை", msg_ta)

        sms_hi = format_sms_alert(alert, language="hi")
        self.assertIn("आपदा अलर्ट", sms_hi)

        voice_en = format_voice_script(alert, language="en")
        self.assertIn("official WeatherGPT emergency", voice_en)

    # 10. Preferences REST API Endpoints & VAPID Key API
    def test_preferences_api_endpoints(self):
        payload = {
            "user_identifier": "test_api_user",
            "phone_number": "+919876543210",
            "preferred_language": "hi",
            "enabled_channels": ["WHATSAPP", "SMS"],
            "min_severity_threshold": "Severe",
            "target_states": ["Tamil Nadu"],
            "is_opted_in": True
        }
        res_post = self.client.post("/api/notifications/preferences", json=payload)
        self.assertEqual(res_post.status_code, 200)
        data = res_post.json()
        self.assertEqual(data["user_identifier"], "test_api_user")

        res_get = self.client.get("/api/notifications/preferences?user_id=test_api_user")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["preferred_language"], "hi")

        # Provider status endpoint
        res_prov = self.client.get("/api/notifications/providers/status")
        self.assertEqual(res_prov.status_code, 200)
        self.assertIn("channels", res_prov.json())
        self.assertIn("WEB_PUSH", res_prov.json()["channels"])
        self.assertIn("restart_persistence", res_prov.json())

        # VAPID public key endpoint
        res_vapid = self.client.get("/api/notifications/vapid-public-key")
        self.assertEqual(res_vapid.status_code, 200)
        self.assertIn("status", res_vapid.json())
        self.assertIn("claim_email", res_vapid.json())

        # Preview endpoint
        res_prev = self.client.post("/api/notifications/preview", json={
            "channel": "WHATSAPP",
            "language": "hi",
            "recipient": "+919876543210"
        })
        self.assertEqual(res_prev.status_code, 200)
        self.assertIn("आधिकारिक", res_prev.json()["formatted_message"])

        # Unsubscribe
        res_del = self.client.delete("/api/notifications/preferences?user_id=test_api_user")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["status"], "unsubscribed")

    # 11. Preview Endpoint Safety
    def test_preview_endpoint_strictly_simulated(self):
        res = self.client.post("/api/notifications/preview", json={
            "channel": "SMS",
            "language": "en",
            "recipient": "+919876543210"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["dry_run"])

    # 12. Cross User Isolation
    def test_cross_user_isolation(self):
        asyncio.run(self.orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="user_alpha",
            phone_number="+919876543210",
            preferred_language="en",
            enabled_channels=[NotificationChannel.SMS]
        )))

        asyncio.run(self.orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="user_beta",
            phone_number="+919123456789",
            preferred_language="hi",
            enabled_channels=[NotificationChannel.WHATSAPP]
        )))

        sub_a = asyncio.run(self.orchestrator.get_subscription("user_alpha"))
        sub_b = asyncio.run(self.orchestrator.get_subscription("user_beta"))
        self.assertNotEqual(sub_a.phone_number, sub_b.phone_number)
        self.assertNotEqual(sub_a.preferred_language, sub_b.preferred_language)

    # 13. Twilio SMS Adapter Tests
    def test_twilio_sms_dry_run(self):
        adapter = TwilioSMSAdapter(dry_run=True)
        payload = NotificationPayload(
            alert_id="TEST-TW-SMS",
            channel=NotificationChannel.SMS,
            title="Flood Warning",
            message="Flood alert for zone A",
            priority="high",
            recipient_identifier="+919876543210"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.is_simulated)

    def test_twilio_sms_missing_config_fails_gracefully(self):
        adapter = TwilioSMSAdapter(account_sid=None, auth_token=None, from_number=None, dry_run=False)
        payload = NotificationPayload(
            alert_id="TEST-TW-SMS",
            channel=NotificationChannel.SMS,
            title="Flood Warning",
            message="Flood alert for zone A",
            priority="high",
            recipient_identifier="+919876543210"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.FAILED)
        self.assertIn("not configured", res.error_message)

    # 14. Twilio Voice Adapter Tests
    def test_twilio_voice_dry_run(self):
        adapter = TwilioVoiceAdapter(dry_run=True)
        payload = NotificationPayload(
            alert_id="TEST-TW-VOICE",
            channel=NotificationChannel.VOICE_IVR,
            title="Cyclone Warning",
            message="Cyclone alert. Seek shelter immediately.",
            priority="high",
            recipient_identifier="+919876543210"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.is_simulated)

    def test_twilio_voice_twiml_generation(self):
        adapter = TwilioVoiceAdapter(dry_run=True)
        twiml = adapter._build_twiml("Severe storm alert.")
        self.assertIn("<Response>", twiml)
        self.assertIn("<Say", twiml)
        self.assertIn("Severe storm alert.", twiml)

    # 15. Twilio WhatsApp Adapter Tests
    def test_twilio_whatsapp_dry_run(self):
        adapter = TwilioWhatsAppAdapter(dry_run=True)
        payload = NotificationPayload(
            alert_id="TEST-TW-WA",
            channel=NotificationChannel.WHATSAPP,
            title="Heatwave Alert",
            message="Heatwave warning in effect.",
            priority="high",
            recipient_identifier="+919876543210"
        )
        res = asyncio.run(adapter.send_notification(payload))
        self.assertEqual(res.status, NotificationStatus.SIMULATED)
        self.assertTrue(res.is_simulated)

    # 16. Twilio WhatsApp Inbound Webhook Test
    def test_twilio_whatsapp_inbound_webhook_returns_twiml(self):
        with patch("backend.services.ai.gemini.gemini_ai_service.generate_weather_response") as mock_gemini:
            mock_gemini.return_value = ChatResponse(
                response_message=ChatMessage(role="model", content="It will not rain in Chennai today."),
                session_id="test_wa_session",
                tools_used=[]
            )
            res = self.client.post("/api/notifications/webhook/twilio-whatsapp", data={
                "From": "whatsapp:+919876543210",
                "Body": "Will it rain today in Chennai?",
                "ProfileName": "Manoj"
            })
            self.assertEqual(res.status_code, 200)
            self.assertIn("application/xml", res.headers["content-type"])
            self.assertIn("<Response><Message>", res.text)
            self.assertIn("It will not rain in Chennai today.", res.text)

    # 17. Subscriber Verification Tests
    def test_subscriber_verification_endpoint(self):
        # Register a test subscriber
        asyncio.run(notification_orchestrator.save_subscription(SubscriptionRequest(
            user_identifier="sub_test_user",
            phone_number="+919940148758",
            whatsapp_number="+919940148758",
            enabled_channels=[NotificationChannel.WHATSAPP],
            is_opted_in=True
        )))

        # Verify exact number
        res = self.client.get("/api/notifications/subscriber/verify?phone=%2B919940148758")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_subscribed"])

        # Verify national format digits (without +)
        res2 = self.client.get("/api/notifications/subscriber/verify?phone=919940148758")
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["is_subscribed"])

        # Verify 10-digit format
        res3 = self.client.get("/api/notifications/subscriber/verify?phone=9940148758")
        self.assertEqual(res3.status_code, 200)
        self.assertTrue(res3.json()["is_subscribed"])

        # Verify unregistered number returns False
        res4 = self.client.get("/api/notifications/subscriber/verify?phone=911111111111")
        self.assertEqual(res4.status_code, 200)
        self.assertFalse(res4.json()["is_subscribed"])

    # 18. Unsubscribe Revokes Access Immediately
    def test_unsubscribe_immediately_revokes_whatsapp_authorization(self):
        user_id = "temp_whatsapp_user"
        phone = "+919876543210"

        # 1. Subscribe
        asyncio.run(notification_orchestrator.save_subscription(SubscriptionRequest(
            user_identifier=user_id,
            phone_number=phone,
            whatsapp_number=phone,
            enabled_channels=[NotificationChannel.WHATSAPP],
            is_opted_in=True
        )))

        # Verify active
        res1 = self.client.get(f"/api/notifications/subscriber/verify?phone={phone}")
        self.assertTrue(res1.json()["is_subscribed"])

        # 2. Unsubscribe via DELETE
        del_res = self.client.delete(f"/api/notifications/preferences?user_id={user_id}")
        self.assertEqual(del_res.status_code, 200)

        # 3. Immediately verify unauthorized (no process restart needed)
        res2 = self.client.get(f"/api/notifications/subscriber/verify?phone={phone}")
        self.assertFalse(res2.json()["is_subscribed"])

    # 19. Supabase REST Client Unit Tests (Mocked PostgREST)
    @patch("httpx.AsyncClient.post")
    def test_supabase_save_subscription_mock(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp

        from backend.db.supabase import SupabaseClient
        client = SupabaseClient()
        client.url = "https://mock.supabase.co"
        client.key = "mock_key"
        client.has_credentials = True

        sub = NotificationSubscription(
            subscription_id="test-uuid",
            user_identifier="mock_user",
            phone_number="+919042099020",
            whatsapp_number="+919042099020",
            enabled_channels=[NotificationChannel.WHATSAPP],
            is_opted_in=True
        )

        res = asyncio.run(client.save_subscription(sub))
        self.assertTrue(res)
        mock_post.assert_called_once()

    @patch("httpx.AsyncClient.get")
    def test_supabase_is_phone_subscribed_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"user_identifier": "mock_u", "phone_number": "+919042099020", "whatsapp_number": "+919042099020", "is_opted_in": True}
        ]
        mock_get.return_value = mock_resp

        from backend.db.supabase import SupabaseClient
        client = SupabaseClient()
        client.url = "https://mock.supabase.co"
        client.key = "mock_key"
        client.has_credentials = True

        # Authorized phone
        res = asyncio.run(client.is_phone_subscribed("+919042099020"))
        self.assertTrue(res)

        # Unauthorized phone
        mock_resp.json.return_value = []
        res2 = asyncio.run(client.is_phone_subscribed("+911234567890"))
        self.assertFalse(res2)

    # 20. Supabase Failure Fails Closed with 503 (No Silent In-Memory Fallback)
    def test_save_subscription_fails_503_when_supabase_unconfigured(self):
        from backend.db.supabase import SupabaseClient
        unconf_client = SupabaseClient()
        unconf_client.has_credentials = False

        with patch("backend.services.notifications.orchestrator.supabase_client", unconf_client):
            res = self.client.post("/api/notifications/preferences", json={
                "user_identifier": "unconf_user",
                "phone_number": "+919876543210",
                "is_opted_in": True
            })
            self.assertEqual(res.status_code, 503)
            self.assertIn("Database persistence error", res.json()["detail"])

    # 21. Phase 1 Test Notification Isolation & Channel Guard
    def test_phase1_test_notification_whatsapp_success(self):
        # Save active user subscription with WHATSAPP
        sub = NotificationSubscription(
            subscription_id="sub-test-1",
            user_identifier="phase1_user",
            phone_number="+919876543210",
            whatsapp_number="+919876543210",
            enabled_channels=[NotificationChannel.WHATSAPP, NotificationChannel.WEB_PUSH],
            is_opted_in=True
        )
        asyncio.run(self.mock_supabase.save_subscription(sub))

        # Trigger POST /api/notifications/test for WHATSAPP
        res = self.client.post("/api/notifications/test", json={
            "user_id": "phase1_user",
            "channel": "WHATSAPP"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["channel"], "WHATSAPP")
        self.assertEqual(data["alert_id"], "TEST-NOTIFICATION")
        self.assertEqual(data["status"], "SIMULATED")  # Dry-run safe mode

    def test_phase1_test_notification_web_push_success(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-2",
            user_identifier="phase1_push_user",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.WEB_PUSH],
            is_opted_in=True
        )
        asyncio.run(self.mock_supabase.save_subscription(sub))

        res = self.client.post("/api/notifications/test", json={
            "user_id": "phase1_push_user",
            "channel": "WEB_PUSH"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["channel"], "WEB_PUSH")
        self.assertEqual(data["alert_id"], "TEST-NOTIFICATION")

    def test_phase1_test_notification_sms_disabled_400(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-3",
            user_identifier="phase1_sms_user",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.SMS],
            is_opted_in=True
        )
        asyncio.run(self.mock_supabase.save_subscription(sub))

        # Triggering SMS in Phase 1 MUST return 400 Bad Request
        res = self.client.post("/api/notifications/test", json={
            "user_id": "phase1_sms_user",
            "channel": "SMS"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("not active in Phase 1", res.json()["detail"])

    def test_phase1_test_notification_voice_disabled_400(self):
        sub = NotificationSubscription(
            subscription_id="sub-test-4",
            user_identifier="phase1_voice_user",
            phone_number="+919876543210",
            enabled_channels=[NotificationChannel.VOICE_IVR],
            is_opted_in=True
        )
        asyncio.run(self.mock_supabase.save_subscription(sub))

        # Triggering Voice/IVR in Phase 1 MUST return 400 Bad Request
        res = self.client.post("/api/notifications/test", json={
            "user_id": "phase1_voice_user",
            "channel": "VOICE_IVR"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("not active in Phase 1", res.json()["detail"])

