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

class ExotelSMSAdapter(BaseNotificationAdapter):
    """
    Exotel Emergency SMS Notification Adapter.
    Supports official Exotel transactional SMS dispatch with dry-run safety.
    """
    def __init__(
        self,
        account_sid: Any = _DEFAULT,
        api_key: Any = _DEFAULT,
        api_token: Any = _DEFAULT,
        sub_domain: Any = _DEFAULT,
        caller_id: Any = _DEFAULT,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.account_sid = settings.EXOTEL_ACCOUNT_SID if account_sid is _DEFAULT else account_sid
        self.api_key = settings.EXOTEL_API_KEY if api_key is _DEFAULT else api_key
        self.api_token = settings.EXOTEL_API_TOKEN if api_token is _DEFAULT else api_token
        self.sub_domain = settings.EXOTEL_SUB_DOMAIN if sub_domain is _DEFAULT else (sub_domain or "api")
        self.caller_id = settings.EXOTEL_CALLER_ID if caller_id is _DEFAULT else caller_id
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        domain = self.sub_domain or "api"
        if not domain.endswith(".exotel.com"):
            domain = f"{domain}.exotel.com"
        self.base_url = f"https://{domain}/v1/Accounts/{self.account_sid}/Sms/send.json" if self.account_sid else None

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = payload.recipient_identifier.strip().replace(" ", "").replace("-", "")

        # 1. Dry Run / Simulation Mode
        if self.dry_run:
            logger.info(f"[SIMULATION: EXOTEL SMS] To: {clean_recipient} | Text: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_sms_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                is_simulated=True
            )

        # 2. Configuration Guard
        if not self.account_sid or not self.api_key or not self.api_token:
            logger.warning("Exotel SMS credentials not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message="Exotel SMS credentials not configured.",
                timestamp=datetime.utcnow()
            )

        data = {
            "From": self.caller_id or "WTHRGPT",
            "To": clean_recipient,
            "Body": payload.message,
            "Priority": "high"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    auth=(self.api_key, self.api_token),
                    data=data
                )
        except httpx.TimeoutException:
            logger.error(f"Exotel SMS timed out to {clean_recipient}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.RETRYING,
                error_message="Exotel SMS connection timed out.",
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Network error calling Exotel SMS: {str(e)}")
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
            sms_data = resp_data.get("SMSMessage", {})
            sid = sms_data.get("Sid", "exotel_sms_sent")
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
                error_message="Exotel rate limit reached (HTTP 429)",
                timestamp=datetime.utcnow()
            )
        else:
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.SMS,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Exotel SMS returned HTTP {response.status_code}: {response.text[:100]}",
                timestamp=datetime.utcnow()
            )

exotel_sms_adapter = ExotelSMSAdapter()
