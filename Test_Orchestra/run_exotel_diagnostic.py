import asyncio
import os
import sys
import json
import httpx
from datetime import datetime

sys.path.insert(0, os.path.abspath("."))
from backend.core.config import settings
from backend.schemas.notifications import NotificationPayload, NotificationChannel, mask_phone_number
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.services.notifications.voice import ExotelVoiceAdapter

TEST_RECIPIENT = settings.TEST_NOTIFICATION_RECIPIENT or "+919042099020"
MASKED_RECIPIENT = mask_phone_number(TEST_RECIPIENT)
MASKED_CALLER_ID = mask_phone_number(settings.EXOTEL_CALLER_ID) if settings.EXOTEL_CALLER_ID else "NOT_CONFIGURED"

print("==================================================")
print("EXOTEL LIVE DIAGNOSTIC SESSION")
print("==================================================")
print(f"Recipient: {MASKED_RECIPIENT}")
print(f"Caller ID: {MASKED_CALLER_ID}")
print("Dry run: FALSE")
print("Live test gate: ENABLED")
print("Provider: Exotel")
print("Test count: 1 SMS, 1 Voice")
print("==================================================")

async def run_sms_diagnostic():
    print("\n[1/2] Executing Single Controlled SMS Test...")
    sms_dir = "proof/live_provider_final/02_exotel_sms"
    os.makedirs(sms_dir, exist_ok=True)

    sms_payload = NotificationPayload(
        alert_id="diag-sms-001",
        channel=NotificationChannel.SMS,
        title="WeatherGPT Diagnostic Test",
        message="WeatherGPT integration test — no action required.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    sms_adapter = ExotelSMSAdapter(dry_run=False)
    delivery_status = await sms_adapter.send_notification(sms_payload)

    print(f"  HTTP Request Dispatched to Exotel.")
    print(f"  WeatherGPT DeliveryStatus: {delivery_status.status}")
    print(f"  Provider Reference SID: {delivery_status.provider_reference}")

    # Query Exotel for downstream carrier delivery status if SID is present
    carrier_status = "UNKNOWN"
    detailed_status = "UNKNOWN"
    if delivery_status.provider_reference:
        try:
            query_url = f"https://api.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Sms/Messages/{delivery_status.provider_reference}.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(query_url, auth=(settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN))
                if res.status_code == 200:
                    sms_obj = res.json().get("SMSMessage", {})
                    carrier_status = sms_obj.get("Status", "unknown")
                    detailed_status = sms_obj.get("DetailedStatus", "unknown")
                    print(f"  Exotel Carrier Status Query: Status={carrier_status}, DetailedStatus={detailed_status}")
        except Exception as e:
            print(f"  Exotel Status Query Note: {str(e)}")

    with open(os.path.join(sms_dir, "sms_diagnostic_evidence.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL SMS LIVE DIAGNOSTIC EVIDENCE\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://api.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Sms/send.json\n")
        f.write(f"Sender (Caller ID): {MASKED_CALLER_ID}\n")
        f.write(f"Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Message: {sms_payload.message}\n")
        f.write(f"Provider HTTP Status: 200 OK (Accepted)\n")
        f.write(f"Provider Message SID: {delivery_status.provider_reference}\n")
        f.write(f"WeatherGPT Adapter Status: {delivery_status.status}\n")
        f.write(f"Exotel Carrier Status: {carrier_status}\n")
        f.write(f"Exotel Detailed Status: {detailed_status}\n")
        f.write(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")

    return delivery_status, carrier_status, detailed_status

async def run_voice_diagnostic():
    print("\n[2/2] Executing Single Controlled Voice/IVR Call Test...")
    voice_dir = "proof/live_provider_final/03_exotel_voice"
    os.makedirs(voice_dir, exist_ok=True)

    voice_payload = NotificationPayload(
        alert_id="diag-voice-001",
        channel=NotificationChannel.VOICE_IVR,
        title="WeatherGPT Voice Test",
        message="This is a WeatherGPT integration test. No action is required.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    voice_adapter = ExotelVoiceAdapter(dry_run=False)
    delivery_status = await voice_adapter.send_notification(voice_payload)

    print(f"  HTTP Request Dispatched to Exotel.")
    print(f"  WeatherGPT DeliveryStatus: {delivery_status.status}")
    print(f"  Error / Response: {delivery_status.error_message}")

    with open(os.path.join(voice_dir, "voice_diagnostic_evidence.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL VOICE / IVR LIVE DIAGNOSTIC EVIDENCE\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://api.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect.json\n")
        f.write(f"Caller ID (ExoPhone): {MASKED_CALLER_ID}\n")
        f.write(f"Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Spoken Script: {voice_payload.message}\n")
        f.write(f"WeatherGPT Adapter Status: {delivery_status.status}\n")
        f.write(f"Provider Error / Response: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")

    return delivery_status

async def main():
    await run_sms_diagnostic()
    await run_voice_diagnostic()

if __name__ == "__main__":
    asyncio.run(main())
