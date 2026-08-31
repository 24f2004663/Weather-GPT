from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AlertSeverity(str, Enum):
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"

class AlertUrgency(str, Enum):
    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"

class AlertCertainty(str, Enum):
    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"

class AlertStatus(str, Enum):
    ACTUAL = "Actual"
    EXERCISE = "Exercise"
    SYSTEM = "System"
    TEST = "Test"
    DRAFT = "Draft"
    CANCELLED = "Cancelled"

class AlertSource(str, Enum):
    SACHET_NDMA = "SACHET_NDMA"
    IMD = "IMD"
    CWC = "CWC"
    NDMA = "NDMA"
    OTHER = "OTHER"

class GeographicScope(str, Enum):
    DISTRICT = "District"
    STATE = "State"
    NATIONAL = "National"
    UNKNOWN = "Unknown"

class DisasterAlert(BaseModel):
    alert_id: str = Field(..., description="Unique stable identifier for the alert")
    source: AlertSource = AlertSource.SACHET_NDMA
    title: str = Field(..., description="Title / headline of the alert")
    event_type: str = Field(..., description="Hazard type: Flood, Cyclone, Heavy Rain, Heat Wave, Thunderstorm, etc.")
    severity: AlertSeverity = AlertSeverity.UNKNOWN
    original_severity: Optional[str] = None
    urgency: AlertUrgency = AlertUrgency.UNKNOWN
    certainty: AlertCertainty = AlertCertainty.UNKNOWN
    status: AlertStatus = AlertStatus.ACTUAL
    headline: Optional[str] = None
    description: str = Field(..., description="Full warning bulletin details")
    instruction: Optional[str] = Field(None, description="Official public safety and disaster response instructions")
    effective_time: Optional[datetime] = None
    expires_time: Optional[datetime] = None
    issued_time: datetime = Field(default_factory=datetime.utcnow)
    affected_area: str = Field(..., description="Human-readable affected region description")
    scope: GeographicScope = GeographicScope.UNKNOWN
    affected_states: List[str] = []
    affected_districts: List[str] = []
    polygon_coordinates: Optional[List[List[float]]] = None
    source_url: Optional[str] = None
    is_active: bool = True

class AlertListResponse(BaseModel):
    source: str = "SACHET/NDMA"
    query_location: Optional[str] = None
    total_count: int
    active_count: int
    highest_severity: Optional[AlertSeverity] = None
    alerts: List[DisasterAlert] = []
    cached: bool = False
    last_synced: datetime = Field(default_factory=datetime.utcnow)
