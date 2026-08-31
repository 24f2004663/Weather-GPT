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

class WhatsAppNotificationAdapter(BaseNotificationAdapter):
    """
    Meta WhatsApp Cloud API Notification Adapter.
    Supports official Cloud API v19.0 message dispatch with built-in dry-run safety.
    """
    def __init__(
        self,
        api_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.api_token = api_token or settings.WHATSAPP_API_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.base_url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages" if self.phone_number_id else None

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = payload.recipient_identifier.strip().replace(" ", "").replace("-", "")

        # 1. Dry Run / Simulation Mode
        if self.dry_run:
            logger.info(f"[SIMULATION: WHATSAPP] To: {clean_recipient} | Msg: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_wa_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                is_simulated=True
            )

        # 2. Configuration Guard
        if not self.api_token or not self.phone_number_id:
            logger.warning("WhatsApp API Token or Phone Number ID not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message="Meta WhatsApp Cloud API credentials not configured.",
                timestamp=datetime.utcnow()
            )

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        # Standard Meta text message payload
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": payload.message
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, headers=headers, json=body)
        except httpx.TimeoutException:
            logger.error(f"WhatsApp Cloud API timed out to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Request to Meta WhatsApp API timed out.",
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Network error calling WhatsApp API: {str(e)}")
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
            messages = resp_data.get("messages", [])
            msg_id = messages[0].get("id") if messages else "wa_sent"
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.SENT,
                provider_reference=msg_id,
                timestamp=datetime.utcnow()
            )
        elif response.status_code == 429:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message=f"Meta WhatsApp rate limit reached (HTTP 429)",
                timestamp=datetime.utcnow()
            )
        else:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Meta WhatsApp API returned HTTP {response.status_code}: {response.text[:100]}",
                timestamp=datetime.utcnow()
            )

whatsapp_notification_adapter = WhatsAppNotificationAdapter()
