from typing import Optional, Dict, Any

class WeatherGPTError(Exception):
    """Base exception for WeatherGPT errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class LocationNotFoundError(WeatherGPTError):
    """Raised when geocoding or location lookup returns no matches."""
    pass

class UpstreamProviderError(WeatherGPTError):
    """Raised when an external API (Open-Meteo, NASA POWER, Gemini) returns an error or invalid response."""
    def __init__(self, provider: str, status_code: Optional[int], message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Upstream provider [{provider}] error: {message}", details)
        self.provider = provider
        self.status_code = status_code

class UpstreamTimeoutError(WeatherGPTError):
    """Raised when an external API request times out."""
    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(f"Request to upstream provider [{provider}] timed out after {timeout_seconds}s")
        self.provider = provider
        self.timeout_seconds = timeout_seconds

class InvalidCoordinatesError(WeatherGPTError):
    """Raised when latitude/longitude coordinates are out of valid geographic ranges."""
    pass

class GeminiConfigMissingError(WeatherGPTError):
    """Raised when Gemini API key is required but missing."""
    def __init__(self, message: str = "Gemini API key is not configured. Set GEMINI_API_KEY in environment variables."):
        super().__init__(message)

class InvalidToolCallError(WeatherGPTError):
    """Raised when the AI attempts to call an unauthorized or malformed tool."""
    pass
