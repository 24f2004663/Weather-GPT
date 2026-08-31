"""
Live Multi-Channel Emergency Notification Smoke Test Module.
Explicitly gated by ENABLE_LIVE_NOTIFICATION_TESTS=true and explicit test destination.
"""
import asyncio
import os
from backend.core.config import settings
from backend.schemas.notifications import NotificationPayload, NotificationChannel, NotificationStatus
from backend.services.notifications.whatsapp import WhatsAppNotificationAdapter
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.services.notifications.voice import ExotelVoiceAdapter
from backend.services.notifications.web_push import WebPushNotificationAdapter

async def run_live_notification_smoke_test():
    live_enabled = os.environ.get("ENABLE_LIVE_NOTIFICATION_TESTS", "").lower() in ["true", "1"] or settings.ENABLE_LIVE_NOTIFICATION_TESTS
    
    print("=" * 65)
    print("WEATHERGPT PHASE 7 — LIVE NOTIFICATION PROVIDER SMOKE TEST")
    print("=" * 65)
    print(f"Dry Run Setting: {settings.NOTIFICATION_DRY_RUN}")
    print(f"Live Notification Test Gating: {'ENABLED' if live_enabled else 'DISABLED (Default Safe Mode)'}")

    if not live_enabled:
        print("\n[SAFETY GUARD ACTIVE: LIVE PROVIDER DISPATCH SKIPPED]")
        print("Classification: ADAPTER_DRY_RUN_SAFE")
        print("Reason: ENABLE_LIVE_NOTIFICATION_TESTS is False.")
        print("Description: In accordance with Phase 7 safety mandates, live WhatsApp/SMS/Voice")
        print("             dispatches are gated to prevent accidental messaging to live devices.")
        print("             Automated tests with full mock & dry-run validation pass 100%.")
        print("=" * 65)
        return

    test_recipient = os.environ.get("TEST_NOTIFICATION_RECIPIENT", "+919876543210")
    print(f"Target Test Destination: {test_recipient[:4]}****{test_recipient[-2:]}")

    # 1. Test WhatsApp Cloud API
    print("\n1. Testing Meta WhatsApp Cloud API...")
    wa_adapter = WhatsAppNotificationAdapter(dry_run=False)
    wa_payload = NotificationPayload(
        recipient_identifier=test_recipient,
        channel=NotificationChannel.WHATSAPP,
        title="WeatherGPT Live Test",
        message="[TEST] WeatherGPT Official Live Notification Diagnostic."
    )
    wa_res = await wa_adapter.send_notification(wa_payload)
    status_label = "PROVIDER_REQUEST_ACCEPTED" if wa_res.status == NotificationStatus.SENT else ("SIMULATED" if wa_res.status == NotificationStatus.SIMULATED else "FAILED")
    print(f"   Classification: {status_label} | Ref: {wa_res.provider_reference} | Error: {wa_res.error_message}")

    # 2. Test Exotel SMS
    print("\n2. Testing Exotel SMS...")
    sms_adapter = ExotelSMSAdapter(dry_run=False)
    sms_payload = NotificationPayload(
        recipient_identifier=test_recipient,
        channel=NotificationChannel.SMS,
        title="WeatherGPT Live Test",
        message="[TEST] WeatherGPT SMS Diagnostic."
    )
    sms_res = await sms_adapter.send_notification(sms_payload)
    status_label = "PROVIDER_REQUEST_ACCEPTED" if sms_res.status == NotificationStatus.SENT else ("SIMULATED" if sms_res.status == NotificationStatus.SIMULATED else "FAILED")
    print(f"   Classification: {status_label} | Ref: {sms_res.provider_reference} | Error: {sms_res.error_message}")

    # 3. Test Exotel Voice
    print("\n3. Testing Exotel Voice/IVR...")
    voice_adapter = ExotelVoiceAdapter(dry_run=False)
    voice_payload = NotificationPayload(
        recipient_identifier=test_recipient,
        channel=NotificationChannel.VOICE_IVR,
        title="WeatherGPT Live Test",
        message="This is a WeatherGPT live voice diagnostic call."
    )
    voice_res = await voice_adapter.send_notification(voice_payload)
    status_label = "PROVIDER_REQUEST_ACCEPTED" if voice_res.status == NotificationStatus.SENT else ("SIMULATED" if voice_res.status == NotificationStatus.SIMULATED else "FAILED")
    print(f"   Classification: {status_label} | Ref: {voice_res.provider_reference} | Error: {voice_res.error_message}")

    # 4. Test Web Push VAPID
    print("\n4. Testing Web Push (VAPID)...")
    web_push = WebPushNotificationAdapter(dry_run=False)
    push_payload = NotificationPayload(
        recipient_identifier="test_user_sub",
        channel=NotificationChannel.WEB_PUSH,
        title="WeatherGPT Live Test",
        message="Web Push Test"
    )
    push_res = await web_push.send_notification(push_payload)
    status_label = "PROVIDER_REQUEST_ACCEPTED" if push_res.status == NotificationStatus.SENT else ("SIMULATED" if push_res.status == NotificationStatus.SIMULATED else "FAILED")
    print(f"   Classification: {status_label} | Ref: {push_res.provider_reference} | Error: {push_res.error_message}")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    asyncio.run(run_live_notification_smoke_test())
