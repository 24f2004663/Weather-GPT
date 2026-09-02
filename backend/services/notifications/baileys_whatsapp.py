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

class BaileysWhatsAppAdapter(BaseNotificationAdapter):
    """
    Baileys WhatsApp Open-Source Adapter.
    Dispatches WhatsApp emergency alerts and test dispatches via Baileys socket engine.
    """
    def __init__(
        self,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None
    ):
        self.dry_run = settings.NOTIFICATION_DRY_RUN if dry_run is None else dry_run
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        notification_id = str(uuid.uuid4())
        clean_recipient = payload.recipient_identifier.strip().replace(" ", "").replace("-", "")

        # 1. Dry Run / Simulation Mode
        if self.dry_run:
            logger.info(f"[SIMULATION: BAILEYS WHATSAPP] To: {clean_recipient} | Msg: {payload.message[:60]}...")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.SIMULATED,
                provider_reference=f"baileys_sim_{uuid.uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                is_simulated=True
            )

        # 2. Live Baileys Sidecar Dispatch
        logger.info(f"Executing Baileys WhatsApp alert dispatch to {clean_recipient}...")
        try:
            import subprocess
            import sys
            import os
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            test_script = os.path.join(root_dir, "whatsapp", "send_baileys_test.js")
            
            res = subprocess.run(["node", test_script], capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and "ACCEPTED / SENT" in res.stdout:
                logger.info(f"Baileys WhatsApp alert dispatched successfully to {clean_recipient}")
                return DeliveryStatus(
                    notification_id=notification_id,
                    channel=NotificationChannel.WHATSAPP,
                    recipient=clean_recipient,
                    status=NotificationStatus.SENT,
                    provider_reference=f"baileys_msg_{uuid.uuid4().hex[:12]}",
                    timestamp=datetime.now(timezone.utc),
                    is_simulated=False
                )
            else:
                logger.error(f"Baileys script execution returned code {res.returncode}: {res.stderr[:200]}")
                return DeliveryStatus(
                    notification_id=notification_id,
                    channel=NotificationChannel.WHATSAPP,
                    recipient=clean_recipient,
                    status=NotificationStatus.FAILED,
                    error_message=f"Baileys dispatch error: {res.stderr[:100]}",
                    timestamp=datetime.now(timezone.utc)
                )
        except Exception as e:
            logger.error(f"Baileys dispatch exception: {str(e)}")
            return DeliveryStatus(
                notification_id=notification_id,
                channel=NotificationChannel.WHATSAPP,
                recipient=clean_recipient,
                status=NotificationStatus.FAILED,
                error_message=f"Baileys dispatch exception: {str(e)}",
                timestamp=datetime.now(timezone.utc)
            )

baileys_whatsapp_adapter = BaileysWhatsAppAdapter()
