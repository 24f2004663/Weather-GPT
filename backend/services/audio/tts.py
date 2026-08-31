from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseTTSService(ABC):
    """
    Abstract contract for Text-to-Speech synthesis.
    Prepared for external provider integration in Phase 7 while supporting
    browser client speech synthesis as the default zero-cost fallback.
    """
    @abstractmethod
    async def get_synthesis_metadata(self, text: str, language: str = "en") -> Dict[str, Any]:
        pass

class BrowserSpeechSynthesisService(BaseTTSService):
    """
    Client-side speech synthesis provider configuration.
    """
    async def get_synthesis_metadata(self, text: str, language: str = "en") -> Dict[str, Any]:
        return {
            "mode": "browser_native",
            "language": language,
            "char_count": len(text),
            "suggested_rate": 1.0,
            "suggested_pitch": 1.0
        }

browser_tts_service = BrowserSpeechSynthesisService()
