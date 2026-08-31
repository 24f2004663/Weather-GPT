import json
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

class TwilioWhatsAppAdapter(BaseNotificationAdapter):
    """
    Twilio WhatsApp Notification Adapter.
    Dispatches WhatsApp notifications via Twilio Messaging API (Sandbox or Production Sender).
    Supports pre-approved Sandbox Content Templates (ContentSid + ContentVariables) as well as direct text.
    """
    def __init__(
        self,
        account_sid: Any = _DEFAULT,
        auth_token: Any = _DEFAULT,
        from_whatsapp: Any = _DEFAULT,
        content_sid: Any = _DEFAULT,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.account_sid = settings.TWILIO_ACCOUNT_SID if account_sid is _DEFAULT else account_sid
        self.auth_token = settings.TWILIO_AUTH_TOKEN if auth_token is _DEFAULT else auth_token
        self.from_whatsapp = settings.TWILIO_WHATSAPP_FROM if from_whatsapp is _DEFAULT else from_whatsapp
        self.content_sid = settings.TWILIO_WHATSAPP_CONTENT_SID if content_sid is _DEFAULT else content_sid
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.base_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            if self.account_sid
            else None
        )

    def _format_whatsapp_number(self, num: str) -> str:
        clean = num.strip().replace(" ", "").replace("-", "")
        if not clean.startswith("whatsapp:"):
            clean = f"whatsapp:{clean}"
        return clean

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = self._format_whatsapp_number(payload.recipient_identifier)
        clean_from = self._format_whatsapp_number(self.from_whatsapp) if self.from_whatsapp else None

        # 1. Dry Run / Simulation Guard
        if self.dry_run:
            logger.info(f"[SIMULATION: TWILIO WHATSAPP] To: {clean_recipient} | Text: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_tw_wa_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                is_simulated=True
            )

        # 2. Configuration Guard
        if not self.account_sid or not self.auth_token or not self.from_whatsapp:
            logger.warning("Twilio WhatsApp credentials or from_whatsapp not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message="Twilio WhatsApp credentials not configured in environment.",
                timestamp=datetime.utcnow()
            )

        if self.content_sid:
            data = {
                "From": clean_from,
                "To": clean_recipient,
                "ContentSid": self.content_sid,
                "ContentVariables": json.dumps({
                    "1": payload.title or "Weather Alert",
                    "2": payload.message[:60]
                })
            }
        else:
            data = {
                "From": clean_from,
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
            logger.error(f"Twilio WhatsApp connection timed out to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Twilio WhatsApp connection timed out.",
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Network error calling Twilio WhatsApp: {str(e)}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Network error: {str(e)}",
                timestamp=datetime.utcnow()
            )

        if response.status_code in [200, 201]:
            resp_data = response.json()
            sid = resp_data.get("sid", "twilio_wa_sent")
            status_str = resp_data.get("status", "queued")
            logger.info(f"Twilio WhatsApp message accepted. SID: {sid}, Status: {status_str}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.SENT,
                provider_reference=sid,
                timestamp=datetime.utcnow()
            )
        elif response.status_code == 429:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Twilio WhatsApp rate limit reached.",
                timestamp=datetime.utcnow()
            )
        else:
            try:
                err_json = response.json()
                err_code = err_json.get("code", response.status_code)
                err_msg = err_json.get("message", response.text)
                detail = f"Twilio WhatsApp API error {err_code}: {err_msg}"
            except Exception:
                detail = f"Twilio WhatsApp API returned HTTP {response.status_code}: {response.text}"

            logger.error(f"Twilio WhatsApp failure to {clean_recipient}: {detail}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=detail,
                timestamp=datetime.utcnow()
            )

twilio_whatsapp_adapter = TwilioWhatsAppAdapter()
