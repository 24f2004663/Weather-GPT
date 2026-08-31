from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ConfigStatusResponse(BaseModel):
    project_name: str
    version: str
    environment: str
    debug: bool
    configured_services: Dict[str, bool]
    allowed_origins: List[str]
