import uuid
import httpx
from datetime import datetime
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

class TwilioSMSAdapter(BaseNotificationAdapter):
    """
    Twilio Emergency SMS Notification Adapter.
    Dispatches transactional and emergency SMS alerts via Twilio REST API.
    """
    def __init__(
        self,
        account_sid: Any = _DEFAULT,
        auth_token: Any = _DEFAULT,
        from_number: Any = _DEFAULT,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.account_sid = settings.TWILIO_ACCOUNT_SID if account_sid is _DEFAULT else account_sid
        self.auth_token = settings.TWILIO_AUTH_TOKEN if auth_token is _DEFAULT else auth_token
        self.from_number = settings.TWILIO_SMS_FROM if from_number is _DEFAULT else from_number
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.base_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            if self.account_sid
            else None
        )

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = payload.recipient_identifier.strip().replace(" ", "").replace("-", "")

        # 1. Dry Run / Simulation Guard
        if self.dry_run:
            logger.info(f"[SIMULATION: TWILIO SMS] To: {clean_recipient} | Text: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_tw_sms_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                is_simulated=True
            )

        # 2. Configuration Guard
        if not self.account_sid or not self.auth_token or not self.from_number:
            logger.warning("Twilio SMS credentials or from_number not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message="Twilio SMS credentials not configured in environment.",
                timestamp=datetime.utcnow()
            )

        data = {
            "From": self.from_number,
            "To": clean_recipient,
            "Body": payload.message
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    auth=(self.account_sid, self.auth_token),
                    data=data
                )
        except httpx.TimeoutException:
            logger.error(f"Twilio SMS connection timed out to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Twilio SMS connection timed out.",
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Network error calling Twilio SMS: {str(e)}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Network error: {str(e)}",
                timestamp=datetime.utcnow()
            )

        if response.status_code in [200, 201]:
            resp_data = response.json()
            sid = resp_data.get("sid", "twilio_sms_sent")
            status_str = resp_data.get("status", "queued")
            logger.info(f"Twilio SMS accepted for delivery. SID: {sid}, Status: {status_str}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.SENT,
                provider_reference=sid,
                timestamp=datetime.utcnow()
            )
        elif response.status_code == 429:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Twilio SMS rate limit reached.",
                timestamp=datetime.utcnow()
            )
        else:
            try:
                err_json = response.json()
                err_code = err_json.get("code", response.status_code)
                err_msg = err_json.get("message", response.text)
                detail = f"Twilio SMS API error {err_code}: {err_msg}"
            except Exception:
                detail = f"Twilio SMS API returned HTTP {response.status_code}: {response.text}"

            logger.error(f"Twilio SMS failure to {clean_recipient}: {detail}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=detail,
                timestamp=datetime.utcnow()
            )

twilio_sms_adapter = TwilioSMSAdapter()
