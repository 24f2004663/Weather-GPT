from abc import ABC, abstractmethod
from typing import List, Optional
from backend.schemas.location import LocationResult
from backend.schemas.weather import WeatherQuery, NormalizedWeatherResponse

class BaseWeatherProvider(ABC):
    """
    Abstract contract for external weather & geocoding providers.
    Ensures normalized data structures across Open-Meteo, NASA POWER, IMD, etc.
    """
    @abstractmethod
    async def resolve_location(self, query: str, count: int = 5) -> List[LocationResult]:
        """
        Geocodes a human query string into normalized LocationResult items.
        """
        pass

    @abstractmethod
    async def get_current_weather(self, lat: float, lon: float, location_meta: Optional[LocationResult] = None) -> NormalizedWeatherResponse:
        """
        Retrieves current conditions for coordinates.
        """
        pass

    @abstractmethod
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        days: int = 7,
        include_hourly: bool = True,
        location_meta: Optional[LocationResult] = None
    ) -> NormalizedWeatherResponse:
        """
        Retrieves daily and optional hourly forecasts for coordinates.
        """
        pass
