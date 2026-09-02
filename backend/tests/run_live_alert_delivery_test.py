import asyncio
import json
import logging
import sys
import uuid
import httpx
from datetime import datetime, timezone

from backend.core.config import settings
from backend.db.supabase import supabase_client
from backend.services.notifications.orchestrator import notification_orchestrator
from backend.schemas.notifications import DisasterAlertTriggeredEvent
from backend.schemas.alerts import (
    DisasterAlert,
    AlertSeverity,
    AlertUrgency,
    AlertCertainty,
    AlertStatus,
    AlertSource,
    GeographicScope,
)
from backend.schemas.notifications import NotificationChannel, NotificationStatus, DeliveryStatus

# Reconfigure stdout for UTF-8 compatibility
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live_alert_delivery_test")


def mask_phone(p: str) -> str:
    if not p:
        return "NONE"
    clean = "".join(filter(str.isdigit, str(p)))
    if len(clean) >= 10:
        return f"+{clean[:2]}******{clean[-4:]}"
    return "***REDACTED***"


async def main():
    print("=" * 80)
    print("FULL LIVE ALERT DELIVERY TEST — WHATSAPP + SMS + WEB PUSH")
    print("=" * 80)

    # PRE-FLIGHT CONFIGURATION REPORT
    print("\n--- PRE-FLIGHT CONFIGURATION AUDIT ---")
    print(f"NOTIFICATION_DRY_RUN: {settings.NOTIFICATION_DRY_RUN}")
    print(f"ENABLE_LIVE_NOTIFICATION_TESTS: {settings.ENABLE_LIVE_NOTIFICATION_TESTS}")
    print(f"TEST_NOTIFICATION_RECIPIENT: {mask_phone(settings.TEST_NOTIFICATION_RECIPIENT)}")
    print(f"SMS_PROVIDER: {settings.SMS_PROVIDER}")
    print(f"TEXTBEE_BASE_URL: {settings.TEXTBEE_BASE_URL}")
    print(f"TEXTBEE_DEVICE_ID: {'CONFIGURED' if settings.TEXTBEE_DEVICE_ID else 'MISSING'}")
    print(f"TEXTBEE_API_KEY: {'CONFIGURED' if settings.TEXTBEE_API_KEY else 'MISSING'}")
    print(f"WHATSAPP_PROVIDER: {settings.WHATSAPP_PROVIDER}")
    print(f"TWILIO_ACCOUNT_SID: {'CONFIGURED' if settings.TWILIO_ACCOUNT_SID else 'MISSING'}")
    print(f"TWILIO_AUTH_TOKEN: {'CONFIGURED' if settings.TWILIO_AUTH_TOKEN else 'MISSING'}")
    print(f"TWILIO_WHATSAPP_FROM: {mask_phone(settings.TWILIO_WHATSAPP_FROM)}")
    print(f"WEB_PUSH_VAPID_PUBLIC_KEY: {'CONFIGURED' if settings.VAPID_PUBLIC_KEY else 'MISSING'}")
    print(f"WEB_PUSH_VAPID_PRIVATE_KEY: {'CONFIGURED' if settings.VAPID_PRIVATE_KEY else 'MISSING'}")

    # CONSTRUCT ISOLATED TEST ALERT
    test_alert = DisasterAlert(
        alert_id="TEST-ALERT-LIVE-557",
        source=AlertSource.SACHET_NDMA,
        title="[TEST ALERT] WeatherGPT Emergency Safety Alert Delivery Test",
        event_type="Severe Weather",
        severity=AlertSeverity.SEVERE,
        original_severity="Severe",
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.TEST,
        headline="[TEST ALERT] Emergency Meteorological Safety Test Notice",
        description="This is an official automated test notification triggered by WeatherGPT system verification. Please disregard if received.",
        instruction="No action required. System test in progress.",
        affected_area="Chennai, Tamil Nadu",
        scope=GeographicScope.DISTRICT,
        affected_states=["Tamil Nadu"],
        affected_districts=["Chennai"],
        issued_time=datetime.now(timezone.utc),
        is_active=True,
    )

    print(f"\n--- TEST ALERT DETAILS ---")
    print(f"Alert ID: {test_alert.alert_id}")
    print(f"Title: {test_alert.title}")
    print(f"Severity: {test_alert.severity.value}")
    print(f"Target State/District: {test_alert.affected_states} / {test_alert.affected_districts}")

    # VERIFY SUBSCRIBER MATCHING
    print(f"\n--- SUBSCRIBER LOOKUP & MATCHING ---")
    subs = await supabase_client.get_all_active_subscriptions()
    print(f"Total Supabase Subscribers: {len(subs)}")
    matched_subs = []
    for sub in subs:
        if not sub.is_opted_in:
            continue
        sev_match = notification_orchestrator._check_severity_threshold(test_alert.severity, sub.min_severity_threshold)
        geo_match = notification_orchestrator._check_geographic_match(test_alert, sub)
        if sev_match and geo_match:
            matched_subs.append(sub)
            print(f"  Matched Subscriber: ID={sub.subscription_id}, Phone={mask_phone(sub.phone_number)}, PushSubPresent={bool(sub.push_subscription)}")

    if not matched_subs:
        print("ERROR: No matching subscribers found in database for test alert!")
        return

    # EXECUTE NOTIFICATION ROUTING
    print(f"\n--- EXECUTING NOTIFICATION ORCHESTRATOR ---")
    notification_orchestrator._sent_idempotency_keys.clear()
    notification_orchestrator._recipient_hourly_counts.clear()

    event = DisasterAlertTriggeredEvent(
        event_id=str(uuid.uuid4()),
        alert=test_alert,
        triggered_at=datetime.utcnow(),
        target_regions=["Tamil Nadu", "Chennai"],
        eligible_channels=[NotificationChannel.WEB_PUSH, NotificationChannel.WHATSAPP, NotificationChannel.SMS]
    )
    dispatch_records = await notification_orchestrator.handle_alert_event(event)

    print(f"\nTotal Channel Dispatches Initiated: {len(dispatch_records)}")
    
    results = {}
    for rec in dispatch_records:
        ch = rec.channel.value
        results[ch] = {
            "notification_id": rec.notification_id,
            "channel": ch,
            "provider": rec.provider,
            "recipient": mask_phone(rec.recipient),
            "status": rec.status.value,
            "provider_message_id": rec.provider_message_id,
            "error_message": rec.error_message,
            "dry_run": rec.dry_run,
        }
        print(f"\n[{ch}] Result:")
        print(f"  - Provider: {rec.provider}")
        print(f"  - Recipient: {mask_phone(rec.recipient)}")
        print(f"  - Status: {rec.status.value}")
        print(f"  - Job/Message ID: {rec.provider_message_id}")
        print(f"  - Dry Run: {rec.dry_run}")
        if rec.error_message:
            print(f"  - Error: {rec.error_message}")

    print("\n" + "=" * 80)
    print("LIVE ALERT DELIVERY TEST SUMMARY")
    print("=" * 80)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
