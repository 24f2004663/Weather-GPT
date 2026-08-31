from typing import List, Optional
from pydantic import BaseModel, Field

class LocationResult(BaseModel):
    """
    Normalized geographic identity model.
    """
    id: Optional[int] = None
    name: str = Field(..., description="City or place name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    country: Optional[str] = None
    country_code: Optional[str] = None
    admin1: Optional[str] = Field(None, description="State, province, or primary administrative subdivision")
    admin2: Optional[str] = Field(None, description="District or secondary administrative subdivision")
    timezone: Optional[str] = None
    elevation: Optional[float] = None
    population: Optional[int] = None

class LocationSearchResponse(BaseModel):
    query: str
    count: int
    results: List[LocationResult]
