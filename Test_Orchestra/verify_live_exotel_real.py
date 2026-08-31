import asyncio
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath("."))
from backend.core.config import settings
from backend.schemas.notifications import NotificationPayload, NotificationChannel, mask_phone_number
from backend.services.notifications.exotel import ExotelSMSAdapter
from backend.services.notifications.voice import ExotelVoiceAdapter

TEST_RECIPIENT = "+919042099020"
MASKED_RECIPIENT = mask_phone_number(TEST_RECIPIENT)

async def test_exotel_sms_live():
    print("Executing Real Exotel SMS test to controlled recipient...")
    sms_dir = "proof/live_provider_final/02_exotel_sms"
    os.makedirs(sms_dir, exist_ok=True)

    # 1. Configuration Check
    with open(os.path.join(sms_dir, "01_configuration.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL SMS CONFIGURATION STATE\n")
        f.write("============================================================\n")
        f.write(f"Account SID Configured: {bool(settings.EXOTEL_ACCOUNT_SID)}\n")
        f.write(f"API Key Configured: {bool(settings.EXOTEL_API_KEY)}\n")
        f.write(f"API Token Configured: {bool(settings.EXOTEL_API_TOKEN)}\n")
        f.write(f"Sub Domain: {settings.EXOTEL_SUB_DOMAIN}\n")
        f.write(f"Caller ID Configured: {bool(settings.EXOTEL_CALLER_ID)}\n")
        f.write(f"Controlled Recipient: {MASKED_RECIPIENT}\n")

    # 2. Prepare payload
    sms_payload = NotificationPayload(
        alert_id="test-sms-live-001",
        channel=NotificationChannel.SMS,
        title="WeatherGPT Integration Test",
        message="WeatherGPT integration test — no action required.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    with open(os.path.join(sms_dir, "02_request.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL SMS LIVE REQUEST METADATA\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://{settings.EXOTEL_SUB_DOMAIN}.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Sms/send.json\n")
        f.write(f"Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Sender (From): {settings.EXOTEL_CALLER_ID or 'Default'}\n")
        f.write(f"Message: {sms_payload.message}\n")
        f.write(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")

    # 3. Execute live send with dry_run=False
    sms_adapter = ExotelSMSAdapter(dry_run=False)
    delivery_status = await sms_adapter.send_notification(sms_payload)
    print(f"Exotel SMS Result Status: {delivery_status.status} | Provider Ref: {delivery_status.provider_reference} | Error: {delivery_status.error_message}")

    with open(os.path.join(sms_dir, "03_provider_response.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL SMS PROVIDER RESPONSE METADATA\n")
        f.write("============================================================\n")
        f.write(f"Delivery Status: {delivery_status.status}\n")
        f.write(f"Provider Reference ID: {delivery_status.provider_reference}\n")
        f.write(f"Simulated Flag: {delivery_status.is_simulated}\n")
        f.write(f"Error Detail: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {delivery_status.timestamp.isoformat()}Z\n")

    with open(os.path.join(sms_dir, "04_delivery_confirmation.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL SMS PHYSICAL DELIVERY CONFIRMATION\n")
        f.write("============================================================\n")
        f.write(f"Target Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Provider Accepted: {delivery_status.status == 'SENT' or delivery_status.status == 'PENDING'}\n")
        f.write("Manual User Receipt Confirmation: PENDING CONFIRMATION\n")

    with open(os.path.join(sms_dir, "sms_verification.md"), "w", encoding="utf-8") as f:
        f.write("# Exotel SMS Live Verification\n\n")
        f.write(f"- **Provider Status**: `{delivery_status.status}`\n")
        f.write(f"- **Provider Reference**: `{delivery_status.provider_reference}`\n")
        f.write(f"- **Masked Recipient**: `{MASKED_RECIPIENT}`\n")
        f.write(f"- **Message Dispatched**: `{sms_payload.message}`\n")

    return delivery_status

async def test_exotel_voice_live():
    print("Executing Real Exotel Voice/IVR test to controlled recipient...")
    voice_dir = "proof/live_provider_final/03_exotel_voice"
    os.makedirs(voice_dir, exist_ok=True)

    with open(os.path.join(voice_dir, "01_configuration.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL VOICE / IVR CONFIGURATION STATE\n")
        f.write("============================================================\n")
        f.write(f"Account SID Configured: {bool(settings.EXOTEL_ACCOUNT_SID)}\n")
        f.write(f"API Key Configured: {bool(settings.EXOTEL_API_KEY)}\n")
        f.write(f"API Token Configured: {bool(settings.EXOTEL_API_TOKEN)}\n")
        f.write(f"Caller ID Configured: {bool(settings.EXOTEL_CALLER_ID)}\n")
        f.write(f"Controlled Recipient: {MASKED_RECIPIENT}\n")

    voice_payload = NotificationPayload(
        alert_id="test-voice-live-001",
        channel=NotificationChannel.VOICE_IVR,
        title="WeatherGPT Voice Test",
        message="This is a WeatherGPT integration test. No action is required.",
        priority="high",
        recipient_identifier=TEST_RECIPIENT
    )

    with open(os.path.join(voice_dir, "02_call_request.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL VOICE LIVE CALL REQUEST METADATA\n")
        f.write("============================================================\n")
        f.write(f"Endpoint: https://{settings.EXOTEL_SUB_DOMAIN}.exotel.com/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect.json\n")
        f.write(f"Caller ID: {mask_phone_number(settings.EXOTEL_CALLER_ID) if settings.EXOTEL_CALLER_ID else 'None'}\n")
        f.write(f"Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Spoken Script: {voice_payload.message}\n")
        f.write(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")

    voice_adapter = ExotelVoiceAdapter(dry_run=False)
    delivery_status = await voice_adapter.send_notification(voice_payload)
    print(f"Exotel Voice Result Status: {delivery_status.status} | Call Ref: {delivery_status.provider_reference} | Error: {delivery_status.error_message}")

    with open(os.path.join(voice_dir, "03_provider_response.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL VOICE PROVIDER RESPONSE METADATA\n")
        f.write("============================================================\n")
        f.write(f"Delivery Status: {delivery_status.status}\n")
        f.write(f"Call Reference ID: {delivery_status.provider_reference}\n")
        f.write(f"Simulated Flag: {delivery_status.is_simulated}\n")
        f.write(f"Error Detail: {delivery_status.error_message}\n")
        f.write(f"Timestamp: {delivery_status.timestamp.isoformat()}Z\n")

    with open(os.path.join(voice_dir, "04_delivery_confirmation.txt"), "w", encoding="utf-8") as f:
        f.write("EXOTEL VOICE PHYSICAL DELIVERY CONFIRMATION\n")
        f.write("============================================================\n")
        f.write(f"Target Recipient: {MASKED_RECIPIENT}\n")
        f.write(f"Provider Accepted: {delivery_status.status == 'SENT' or delivery_status.status == 'PENDING'}\n")
        f.write("Manual User Call Confirmation: PENDING CONFIRMATION\n")

    with open(os.path.join(voice_dir, "voice_verification.md"), "w", encoding="utf-8") as f:
        f.write("# Exotel Voice / IVR Live Verification\n\n")
        f.write(f"- **Provider Status**: `{delivery_status.status}`\n")
        f.write(f"- **Call Reference**: `{delivery_status.provider_reference}`\n")
        f.write(f"- **Masked Recipient**: `{MASKED_RECIPIENT}`\n")
        f.write(f"- **Spoken Message**: `{voice_payload.message}`\n")

    return delivery_status

async def main():
    await test_exotel_sms_live()
    await test_exotel_voice_live()

if __name__ == "__main__":
    asyncio.run(main())
