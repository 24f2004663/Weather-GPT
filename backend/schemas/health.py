from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = Field(..., description="Application health status: 'healthy', 'degraded', or 'unhealthy'")
    version: str = Field(..., description="API Version")
    environment: str = Field(..., description="Execution environment")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of the health check")
    services: Dict[str, bool] = Field(..., description="Availability status of configured adapters and components")
