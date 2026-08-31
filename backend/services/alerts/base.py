from abc import ABC, abstractmethod
from typing import List, Optional
from backend.schemas.alerts import DisasterAlert

class BaseAlertProvider(ABC):
    """
    Abstract interface for official disaster and emergency alert feeds.
    Decouples specific government/CAP feeds (SACHET/NDMA, IMD, CWC) from the application core.
    """
    @abstractmethod
    async def fetch_active_alerts(self, force_refresh: bool = False) -> List[DisasterAlert]:
        """Fetches and normalizes all available disaster alerts from the source."""
        pass

    @abstractmethod
    async def get_alerts_for_location(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        state: Optional[str] = None,
        district: Optional[str] = None,
        active_only: bool = True
    ) -> List[DisasterAlert]:
        """Filters alerts relevant to a specific geographical region or coordinates."""
        pass
