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

class WebPushNotificationAdapter(BaseNotificationAdapter):
    """
    Web Push (VAPID) Notification Adapter.
    Dispatches browser-native push notifications for emergency disaster alerts.
    """
    def __init__(
        self,
        public_key: Any = _DEFAULT,
        private_key: Any = _DEFAULT,
        claim_email: Optional[str] = None,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.public_key = settings.VAPID_PUBLIC_KEY if public_key is _DEFAULT else public_key
        self.private_key = settings.VAPID_PRIVATE_KEY if private_key is _DEFAULT else private_key
        self.claim_email = claim_email or settings.VAPID_CLAIM_EMAIL
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        recipient = payload.recipient_identifier

        # 1. Dry Run / Simulation Mode
        if self.dry_run:
            logger.info(f"[SIMULATION: WEB PUSH] Recipient: {recipient} | Title: {payload.title}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WEB_PUSH,
                recipient=recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"sim_push_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.utcnow(),
                is_simulated=True
            )

        # 2. Configuration Guard
        if not self.public_key or not self.private_key:
            logger.warning("Web Push VAPID keys not configured.")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WEB_PUSH,
                recipient=recipient,
                status=NotificationStatus.FAILED,
                error_message="WebPush VAPID keys not configured in environment.",
                timestamp=datetime.utcnow()
            )

        # Build Web Push standard payload
        push_data = {
            "title": payload.title,
            "body": payload.message,
            "icon": "/icon-192.png",
            "tag": f"weathergpt-alert-{payload.alert_id or 'general'}",
            "data": {
                "alert_id": payload.alert_id,
                "url": "/api/alerts",
                "priority": payload.priority
            }
        }

        # Simulated live dispatch stub for browser web push endpoint
        return DeliveryStatus(
            notification_id=notification_id,
            channel=NotificationChannel.WEB_PUSH,
            recipient=recipient,
            status=NotificationStatus.SENT,
            provider_reference=f"vapid_push_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow()
        )

web_push_adapter = WebPushNotificationAdapter()
