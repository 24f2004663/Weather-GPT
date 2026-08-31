import asyncio
import os
import sys
import json
import httpx
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath("."))
from backend.core.config import settings
from backend.schemas.notifications import NotificationPayload, NotificationChannel, mask_phone_number
from backend.services.notifications.twilio_sms import TwilioSMSAdapter
from backend.services.notifications.twilio_voice import TwilioVoiceAdapter
from backend.services.notifications.twilio_whatsapp import TwilioWhatsAppAdapter

TEST_RECIPIENT = settings.TEST_NOTIFICATION_RECIPIENT or "+919042099020"
MASKED_RECIPIENT = mask_phone_number(TEST_RECIPIENT)
MASKED_SMS_FROM = mask_phone_number(settings.TWILIO_SMS_FROM) if settings.TWILIO_SMS_FROM else "NOT_CONFIGURED"
MASKED_VOICE_FROM = mask_phone_number(settings.TWILIO_VOICE_FROM) if settings.TWILIO_VOICE_FROM else "NOT_CONFIGURED"
MASKED_WA_FROM = mask_phone_number(settings.TWILIO_WHATSAPP_FROM.replace("whatsapp:", "")) if settings.TWILIO_WHATSAPP_FROM else "NOT_CONFIGURED"

print("==================================================")
print("TWILIO LIVE PROVIDER REAL VERIFICATION SESSION")
print("==================================================")
print(f"Target Recipient: {MASKED_RECIPIENT}")
print(f"SMS From:         {MASKED_SMS_FROM}")
print(f"Voice From:       {MASKED_VOICE_FROM}")
print(f"WhatsApp From:    {MASKED_WA_FROM}")
print("Dry run:          FALSE (REAL NETWORK DISPATCH)")
print("Live test gate:   ENABLED")
print("==================================================")

async def test_live_sms():
    print("\n--- [1/3] EXECUTING REAL TWILIO SMS TEST ---")
    sms_dir = "proof/twilio_live/01_sms"
    os.makedirs(sms_dir, exist_ok=True)

    payload = NotificationPayload(
        alert_id="tw-sms-live-001",
        channel=NotificationChannel.SMS,
        title="WeatherGPT Alert",
        message="WeatherGPT Twilio integration test — Emergency SMS dispatch verified. No action required.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    adapter = TwilioSMSAdapter(dry_run=False)
    delivery_status = await adapter.send_notification(payload)

    print(f"Result Status:      {delivery_status.status}")
    print(f"Message SID:        {delivery_status.provider_reference}")
    print(f"Error Message:      {delivery_status.error_message}")

    provider_status = "unknown"
    error_code = None
    if delivery_status.provider_reference and delivery_status.provider_reference.startswith("SM"):
        try:
            await asyncio.sleep(2) # brief pause to allow Twilio carrier routing status update
            query_url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages/{delivery_status.provider_reference}.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(query_url, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
                if res.status_code == 200:
                    data = res.json()
                    provider_status = data.get("status")
                    error_code = data.get("error_code")
                    error_msg = data.get("error_message")
                    print(f"Twilio Carrier Progression: Status={provider_status}, ErrorCode={error_code}, ErrorMsg={error_msg}")
        except Exception as e:
            print(f"Status query error: {e}")

    with open(os.path.join(sms_dir, "01_sms_evidence.txt"), "w", encoding="utf-8") as f:
        f.write("TWILIO LIVE SMS VERIFICATION EVIDENCE\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://api.twilio.com/2010-04-01/Accounts/***/Messages.json\n")
        f.write(f"Sender (From): {MASKED_SMS_FROM}\n")
        f.write(f"Recipient (To): {MASKED_RECIPIENT}\n")
        f.write(f"Message: {payload.message}\n")
        f.write(f"Adapter Status: {delivery_status.status}\n")
        f.write(f"Twilio Message SID: {delivery_status.provider_reference}\n")
        f.write(f"Twilio Message Status: {provider_status}\n")
        f.write(f"Twilio Error Code: {error_code}\n")
        f.write(f"Error Detail: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    return delivery_status, provider_status

async def test_live_voice():
    print("\n--- [2/3] EXECUTING REAL TWILIO VOICE / IVR CALL TEST ---")
    voice_dir = "proof/twilio_live/02_voice"
    os.makedirs(voice_dir, exist_ok=True)

    payload = NotificationPayload(
        alert_id="tw-voice-live-001",
        channel=NotificationChannel.VOICE_IVR,
        title="WeatherGPT Voice Alert",
        message="This is an automated emergency notification test from WeatherGPT. All systems are operational.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    adapter = TwilioVoiceAdapter(dry_run=False)
    delivery_status = await adapter.send_notification(payload)

    print(f"Result Status:      {delivery_status.status}")
    print(f"Call SID:           {delivery_status.provider_reference}")
    print(f"Error Message:      {delivery_status.error_message}")

    call_status = "unknown"
    call_duration = None
    if delivery_status.provider_reference and delivery_status.provider_reference.startswith("CA"):
        try:
            await asyncio.sleep(2)
            query_url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls/{delivery_status.provider_reference}.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(query_url, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
                if res.status_code == 200:
                    data = res.json()
                    call_status = data.get("status")
                    call_duration = data.get("duration")
                    print(f"Twilio Call Progression: Status={call_status}, Duration={call_duration}")
        except Exception as e:
            print(f"Call status query error: {e}")

    with open(os.path.join(voice_dir, "01_voice_evidence.txt"), "w", encoding="utf-8") as f:
        f.write("TWILIO LIVE VOICE / IVR VERIFICATION EVIDENCE\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://api.twilio.com/2010-04-01/Accounts/***/Calls.json\n")
        f.write(f"Caller (From): {MASKED_VOICE_FROM}\n")
        f.write(f"Recipient (To): {MASKED_RECIPIENT}\n")
        f.write(f"Spoken Script: {payload.message}\n")
        f.write(f"Adapter Status: {delivery_status.status}\n")
        f.write(f"Twilio Call SID: {delivery_status.provider_reference}\n")
        f.write(f"Twilio Call Status: {call_status}\n")
        f.write(f"Error Detail: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    return delivery_status, call_status

async def test_live_whatsapp():
    print("\n--- [3/3] EXECUTING REAL TWILIO WHATSAPP TEST ---")
    wa_dir = "proof/twilio_live/03_whatsapp"
    os.makedirs(wa_dir, exist_ok=True)

    payload = NotificationPayload(
        alert_id="tw-wa-live-001",
        channel=NotificationChannel.WHATSAPP,
        title="WeatherGPT WhatsApp Test",
        message="*WeatherGPT Emergency Alert*: This is a live provider integration test via Twilio WhatsApp.",
        priority="high",
        recipient_identifier=settings.TWILIO_WHATSAPP_TO or f"whatsapp:{TEST_RECIPIENT}"
    )

    adapter = TwilioWhatsAppAdapter(dry_run=False)
    delivery_status = await adapter.send_notification(payload)

    print(f"Result Status:      {delivery_status.status}")
    print(f"Message SID:        {delivery_status.provider_reference}")
    print(f"Error Message:      {delivery_status.error_message}")

    with open(os.path.join(wa_dir, "01_whatsapp_evidence.txt"), "w", encoding="utf-8") as f:
        f.write("TWILIO LIVE WHATSAPP VERIFICATION EVIDENCE\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://api.twilio.com/2010-04-01/Accounts/***/Messages.json\n")
        f.write(f"Sender (From): {MASKED_WA_FROM}\n")
        f.write(f"Recipient (To): {MASKED_RECIPIENT}\n")
        f.write(f"Adapter Status: {delivery_status.status}\n")
        f.write(f"Twilio Message SID: {delivery_status.provider_reference}\n")
        f.write(f"Error Detail: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    return delivery_status

async def main():
    await test_live_sms()
    await test_live_voice()
    await test_live_whatsapp()

if __name__ == "__main__":
    asyncio.run(main())
