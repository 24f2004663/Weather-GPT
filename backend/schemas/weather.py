from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.schemas.location import LocationResult

class LocationCoordinates(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

class WeatherQuery(BaseModel):
    location: Optional[str] = Field(None, description="City name or query text")
    coordinates: Optional[LocationCoordinates] = None
    days_forecast: int = Field(default=7, ge=1, le=16)
    include_hourly: bool = Field(default=True)
    include_historical: bool = Field(default=False)

class CurrentWeather(BaseModel):
    temperature_c: float
    apparent_temperature_c: Optional[float] = None
    humidity_percent: Optional[int] = None
    precipitation_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction_deg: Optional[int] = None
    wind_gusts_kmh: Optional[float] = None
    weather_code: int
    weather_condition: str
    icon_key: str
    is_day: Optional[int] = 1
    uv_index: Optional[float] = None
    cloud_cover_percent: Optional[int] = None
    pressure_hpa: Optional[float] = None
    air_quality_index: Optional[int] = None
    observed_time: datetime

class HourlyForecast(BaseModel):
    time: str
    temperature_c: float
    apparent_temperature_c: Optional[float] = None
    precipitation_probability: Optional[int] = None
    precipitation_mm: Optional[float] = None
    weather_code: int
    weather_condition: str
    icon_key: str
    wind_speed_kmh: Optional[float] = None
    humidity_percent: Optional[int] = None
    uv_index: Optional[float] = None

class DailyForecast(BaseModel):
    date: str
    temperature_max_c: float
    temperature_min_c: float
    apparent_temperature_max_c: Optional[float] = None
    apparent_temperature_min_c: Optional[float] = None
    precipitation_sum_mm: Optional[float] = None
    precipitation_probability_max: Optional[int] = None
    precipitation_hours: Optional[float] = None
    weather_code: int
    weather_condition: str
    icon_key: str
    wind_speed_max_kmh: Optional[float] = None
    wind_gusts_max_kmh: Optional[float] = None
    wind_direction_dominant_deg: Optional[int] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    uv_index_max: Optional[float] = None

class NormalizedWeatherResponse(BaseModel):
    provider: str = "Open-Meteo"
    location: LocationResult
    current: CurrentWeather
    hourly: List[HourlyForecast] = []
    daily: List[DailyForecast] = []
    timezone: str = "UTC"
    elevation_m: Optional[float] = None
    cached: bool = False
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
