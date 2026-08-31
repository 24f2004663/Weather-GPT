import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.errors import (
    WeatherGPTError,
    UpstreamProviderError,
    UpstreamTimeoutError,
)

class GroqConfigMissingError(WeatherGPTError):
    """Raised when Groq API key is required for transcription but not configured."""
    def __init__(self, message: str = "Groq API key is not configured. Set GROQ_API_KEY in environment variables."):
        super().__init__(message)

class BaseSTTService(ABC):
    @abstractmethod
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

_DEFAULT = object()

class GroqWhisperService(BaseSTTService):
    """
    High-Speed Speech-to-Text using Groq Whisper API (whisper-large-v3).
    Supports multilingual voice transcription with strict error boundaries.
    """
    def __init__(
        self,
        api_key: Any = _DEFAULT,
        model: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.api_key = settings.GROQ_API_KEY if api_key is _DEFAULT else api_key
        self.model = model or settings.GROQ_WHISPER_MODEL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.api_key or not self.api_key.strip():
            logger.error("Attempted to call Groq STT without configured GROQ_API_KEY")
            raise GroqConfigMissingError()

        if not audio_bytes or len(audio_bytes) == 0:
            raise WeatherGPTError("Audio buffer is empty or corrupted.")

        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        # Build multipart form data
        data = {
            "model": self.model,
            "response_format": "json"
        }
        if language and language != "auto":
            data["language"] = language

        files = {
            "file": (filename, audio_bytes, content_type)
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    data=data,
                    files=files
                )
        except httpx.TimeoutException:
            logger.error(f"Groq Whisper transcription timed out after {self.timeout}s")
            raise UpstreamTimeoutError(provider="Groq Whisper", timeout_seconds=self.timeout)
        except Exception as e:
            logger.error(f"Network error calling Groq Whisper: {str(e)}")
            raise UpstreamProviderError(provider="Groq Whisper", status_code=None, message=str(e))

        if response.status_code != 200:
            logger.error(f"Groq Whisper HTTP {response.status_code}: {response.text}")
            raise UpstreamProviderError(
                provider="Groq Whisper",
                status_code=response.status_code,
                message=f"Groq Whisper returned HTTP {response.status_code}"
            )

        try:
            result = response.json()
        except Exception as e:
            raise UpstreamProviderError(provider="Groq Whisper", status_code=200, message="Malformed JSON response from Groq API")

        transcription_text = result.get("text", "").strip()
        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "transcription": transcription_text,
            "language": language or "auto",
            "model": self.model,
            "execution_time_ms": elapsed_ms
        }

groq_whisper_service = GroqWhisperService()
