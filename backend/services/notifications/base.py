from abc import ABC, abstractmethod
from backend.schemas.notifications import NotificationPayload, DeliveryStatus

class BaseNotificationAdapter(ABC):
    """
    Abstract contract for dispatching proactive and disaster alerts.
    """
    @abstractmethod
    async def send_notification(self, payload: NotificationPayload) -> DeliveryStatus:
        pass
