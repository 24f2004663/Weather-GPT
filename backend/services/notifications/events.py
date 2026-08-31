import uuid
from datetime import datetime
from typing import List, Callable, Dict, Any
from backend.schemas.alerts import DisasterAlert
from backend.schemas.notifications import DisasterAlertTriggeredEvent, NotificationChannel
from backend.core.logging import logger

class AlertEventBus:
    """
    Decoupled Event Bus for Disaster Alert notifications.
    Allows multi-channel subscribers (Web, WhatsApp, SMS, IVR) to register handlers
    for high-severity alerts without coupling the ingestion engine to delivery adapters.
    """
    def __init__(self):
        self._subscribers: List[Callable[[DisasterAlertTriggeredEvent], Any]] = []

    def subscribe(self, handler: Callable[[DisasterAlertTriggeredEvent], Any]) -> None:
        self._subscribers.append(handler)

    async def emit_alert_triggered(self, alert: DisasterAlert) -> DisasterAlertTriggeredEvent:
        event = DisasterAlertTriggeredEvent(
            event_id=str(uuid.uuid4()),
            alert=alert,
            triggered_at=datetime.utcnow(),
            target_regions=alert.affected_states + alert.affected_districts,
            eligible_channels=[
                NotificationChannel.WEB_PUSH,
                NotificationChannel.WHATSAPP,
                NotificationChannel.SMS
            ]
        )
        logger.info(f"Disaster alert event emitted: {alert.alert_id} ({alert.title}) - {alert.severity}")

        for sub in self._subscribers:
            try:
                res = sub(event)
                if hasattr(res, "__await__"):
                    await res
            except Exception as e:
                logger.error(f"Error notifying alert subscriber: {str(e)}")

        return event

alert_event_bus = AlertEventBus()
