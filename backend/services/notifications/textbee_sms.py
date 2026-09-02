import uuid
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from backend.core.config import settings
from backend.core.logging import logger
from backend.services.notifications.base import BaseNotificationAdapter
from backend.schemas.notifications import (
    NotificationPayload,
    DeliveryStatus,
    NotificationChannel,
    NotificationStatus,
)

_DEFAULT = object()


class TextBeeSMSAdapter(BaseNotificationAdapter):
    """
    TextBee Emergency SMS Notification Adapter.
    Dispatches emergency SMS alerts via TextBee Gateway REST API (Android phone + SIM).
    """

    def __init__(
        self,
        api_key: Any = _DEFAULT,
        device_id: Any = _DEFAULT,
        base_url: Any = _DEFAULT,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = settings.TEXTBEE_API_KEY if api_key is _DEFAULT else api_key
        self.device_id = settings.TEXTBEE_DEVICE_ID if device_id is _DEFAULT else device_id
        b_url = settings.TEXTBEE_BASE_URL if base_url is _DEFAULT else base_url
        self.base_url = (b_url or "https://api.textbee.dev/api/v1").rstrip("/")
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = payload.recipient_identifier.strip().replace(" ", "").replace("-", "")

        # Normalize phone number to E.164
        if not clean_recipient.startswith("+") and clean_recipient.isdigit():
            if len(clean_recipient) == 10:
                clean_recipient = f"+91{clean_recipient}"
            else:
                clean_recipient = f"+{clean_recipient}"

        # 1. Dry Run / Simulation Guard
        if self.dry_run:
            logger.info(f"[SIMULATION: TEXTBEE SMS] To: {clean_recipient} | Text: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_tb_sms_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                is_simulated=True,
            )

        # 2. Configuration Guard
        if not self.api_key or not self.device_id:
            logger.warning("TextBee SMS credentials (TEXTBEE_API_KEY or TEXTBEE_DEVICE_ID) not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message="TextBee SMS credentials (TEXTBEE_API_KEY / TEXTBEE_DEVICE_ID) not configured.",
                timestamp=datetime.now(timezone.utc),
            )

        endpoint = f"{self.base_url}/gateway/send-sms"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        data = {
            "recipients": [clean_recipient],
            "message": payload.message,
            "deviceId": self.device_id,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, headers=headers, json=data)
        except httpx.TimeoutException:
            logger.error(f"TextBee SMS connection timed out to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="TextBee SMS gateway connection timed out.",
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.error(f"Network error calling TextBee SMS: {str(e)}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Network error: {str(e)}",
                timestamp=datetime.now(timezone.utc),
            )

        if response.status_code in [200, 201]:
            try:
                resp_data = response.json()
            except Exception:
                resp_data = {}

            message_id = (
                resp_data.get("id")
                or resp_data.get("messageId")
                or (resp_data.get("data", {}) if isinstance(resp_data.get("data"), dict) else {}).get("id")
                or f"tb_sms_{uuid.uuid4().hex[:12]}"
            )
            logger.info(f"TextBee SMS accepted for delivery. ID: {message_id} to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.SENT,
                provider_reference=str(message_id),
                timestamp=datetime.now(timezone.utc),
            )
        elif response.status_code == 429:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="TextBee rate limit reached (HTTP 429).",
                timestamp=datetime.now(timezone.utc),
            )
        else:
            try:
                err_json = response.json()
                err_msg = err_json.get("message") or err_json.get("error") or response.text[:100]
                detail = f"TextBee SMS API error HTTP {response.status_code}: {err_msg}"
            except Exception:
                detail = f"TextBee SMS API returned HTTP {response.status_code}: {response.text[:100]}"

            logger.error(f"TextBee SMS failure to {clean_recipient}: {detail}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=detail,
                timestamp=datetime.now(timezone.utc),
            )


textbee_sms_adapter = TextBeeSMSAdapter()
