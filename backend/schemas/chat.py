from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., max_length=10000)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_attribution: Optional[List[str]] = Field(default=None, description="Data sources utilized for this response")

class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_items=1, max_items=50)
    user_location: Optional[str] = Field(default=None, description="Optional current user place name hint")
    coordinates: Optional[Dict[str, float]] = Field(default=None, description="Optional current lat/lon coordinates")
    language_preference: str = Field(default="en", description="Preferred output language")
    session_id: Optional[str] = Field(default=None, description="Conversation session token")

class ToolCallLog(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    status: str
    execution_time_ms: float

class ChatResponse(BaseModel):
    response_message: ChatMessage
    session_id: str
    referenced_weather_data: Optional[Dict[str, Any]] = None
    referenced_alerts: Optional[List[Dict[str, Any]]] = None
    tools_used: List[str] = []
    tool_execution_logs: List[ToolCallLog] = []
