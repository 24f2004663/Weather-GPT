from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from backend.schemas.location import LocationResult

class MonthlyClimateMetric(BaseModel):
    month: str
    temperature_2m_c: Optional[float] = None
    precipitation_mm_day: Optional[float] = None
    solar_radiation_kwh_m2_day: Optional[float] = None
    relative_humidity_percent: Optional[float] = None
    wind_speed_10m_ms: Optional[float] = None

class NasaPowerClimateResponse(BaseModel):
    provider: str = "NASA POWER"
    location: LocationResult
    annual_averages: Dict[str, float]
    monthly_data: List[MonthlyClimateMetric]
    parameters_explained: Dict[str, str]
    cached: bool = False
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
