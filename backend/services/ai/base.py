from abc import ABC, abstractmethod
from backend.schemas.chat import ChatRequest, ChatResponse

class BaseAIService(ABC):
    """
    Abstract contract for WeatherGPT AI Orchestration.
    Decouples LLM providers from the rest of the application.
    """
    @abstractmethod
    async def generate_weather_response(self, request: ChatRequest) -> ChatResponse:
        pass
