from typing import List, Optional, Dict, Any
from pydantic import Field
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseSettings
    SettingsConfigDict = None

class Settings(BaseSettings):
    """
    Application Settings validated through environment variables.
    Fails safely and explicitly when required parameters are malformed.
    """
    # Environment & Server
    PROJECT_NAME: str = "WeatherGPT"
    PROJECT_VERSION: str = "0.7.1"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    PORT: int = Field(default=8000, env="PORT")
    FRONTEND_PORT: int = Field(default=3000, env="FRONTEND_PORT")
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        env="ALLOWED_ORIGINS"
    )

    # HTTP Client Configuration & Timeouts
    HTTP_TIMEOUT_SECONDS: float = Field(default=30.0, env="HTTP_TIMEOUT_SECONDS")
    NASA_POWER_TIMEOUT_SECONDS: float = Field(default=45.0, env="NASA_POWER_TIMEOUT_SECONDS")

    # Cache TTLs (in seconds)
    WEATHER_CACHE_TTL_SECONDS: int = Field(default=900, env="WEATHER_CACHE_TTL_SECONDS")       # 15 mins (fresh)
    WEATHER_STALE_CACHE_TTL_SECONDS: int = Field(default=7200, env="WEATHER_STALE_CACHE_TTL_SECONDS") # 2 hours (stale fallback)
    GEOCODING_CACHE_TTL_SECONDS: int = Field(default=86400, env="GEOCODING_CACHE_TTL_SECONDS")   # 24 hours
    CLIMATE_CACHE_TTL_SECONDS: int = Field(default=604800, env="CLIMATE_CACHE_TTL_SECONDS")    # 7 days
    ALERT_CACHE_TTL_SECONDS: int = Field(default=300, env="ALERT_CACHE_TTL_SECONDS")          # 5 mins (fresh)
    ALERT_STALE_CACHE_TTL_SECONDS: int = Field(default=900, env="ALERT_STALE_CACHE_TTL_SECONDS") # 15 mins (stale fallback for emergencies)


    # Weather & Feed URLs
    OPEN_METEO_BASE_URL: str = Field(default="https://api.open-meteo.com/v1", env="OPEN_METEO_BASE_URL")
    OPEN_METEO_GEOCODING_URL: str = Field(default="https://geocoding-api.open-meteo.com/v1/search", env="OPEN_METEO_GEOCODING_URL")
    NASA_POWER_BASE_URL: str = Field(default="https://power.larc.nasa.gov/api/temporal/climatology/point", env="NASA_POWER_BASE_URL")
    SACHET_NDMA_ALERT_FEED_URL: str = Field(default="https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml", env="SACHET_NDMA_ALERT_FEED_URL")

    # Primary LLM Provider & Multi-Model Quota Router
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash-lite", env="GEMINI_MODEL")

    # Priority Model 1: Gemini 3.5 Flash Lite (Application-level protective limits)
    GEMINI_MODEL_1: str = Field(default="gemini-3.5-flash-lite", env="GEMINI_MODEL_1")
    GEMINI_FLASH_LITE_SAFE_RPM: int = Field(default=12, env="GEMINI_FLASH_LITE_SAFE_RPM")
    GEMINI_FLASH_LITE_SAFE_RPD: int = Field(default=1000, env="GEMINI_FLASH_LITE_SAFE_RPD")
    GEMINI_FLASH_LITE_SAFE_TPM: int = Field(default=250000, env="GEMINI_FLASH_LITE_SAFE_TPM")

    # Priority Model 2: Gemini 3.1 Flash Lite (Application-level protective limits)
    GEMINI_MODEL_2: str = Field(default="gemini-3.1-flash-lite", env="GEMINI_MODEL_2")
    GEMINI_FLASH_LITE_31B_SAFE_RPM: int = Field(default=12, env="GEMINI_FLASH_LITE_31B_SAFE_RPM")
    GEMINI_FLASH_LITE_31B_SAFE_RPD: int = Field(default=1000, env="GEMINI_FLASH_LITE_31B_SAFE_RPD")
    GEMINI_FLASH_LITE_31B_SAFE_TPM: int = Field(default=250000, env="GEMINI_FLASH_LITE_31B_SAFE_TPM")

    # Priority Model 3: Gemma 4 31B (Application-level protective limits)
    GEMINI_MODEL_3: str = Field(default="gemma-4-31b", env="GEMINI_MODEL_3")
    GEMMA_4_31B_SAFE_RPM: int = Field(default=25, env="GEMMA_4_31B_SAFE_RPM")
    GEMMA_4_31B_SAFE_RPD: int = Field(default=1000, env="GEMMA_4_31B_SAFE_RPD")
    GEMMA_4_31B_SAFE_TPM: int = Field(default=250000, env="GEMMA_4_31B_SAFE_TPM")

    # Priority Model 4: Gemma 4 26B (Application-level protective limits)
    GEMINI_MODEL_4: str = Field(default="gemma-4-26b", env="GEMINI_MODEL_4")
    GEMMA_4_26B_SAFE_RPM: int = Field(default=25, env="GEMMA_4_26B_SAFE_RPM")
    GEMMA_4_26B_SAFE_RPD: int = Field(default=1000, env="GEMMA_4_26B_SAFE_RPD")
    GEMMA_4_26B_SAFE_TPM: int = Field(default=250000, env="GEMMA_4_26B_SAFE_TPM")

    # Quota Suppression Duration on 429
    GEMINI_429_SUPPRESS_SECONDS: int = Field(default=60, env="GEMINI_429_SUPPRESS_SECONDS")



    # Supabase / Database
    SUPABASE_URL: Optional[str] = Field(default=None, env="SUPABASE_URL")
    SUPABASE_ANON_KEY: Optional[str] = Field(default=None, env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(default=None, env="SUPABASE_SERVICE_ROLE_KEY")
    DATABASE_URL: Optional[str] = Field(default=None, env="DATABASE_URL")

    # Speech to Text (Groq Whisper)
    GROQ_API_KEY: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    GROQ_WHISPER_MODEL: str = Field(default="whisper-large-v3", env="GROQ_WHISPER_MODEL")

    # Communication Providers & Emergency Delivery Controls
    NOTIFICATION_DRY_RUN: bool = Field(default=True, env="NOTIFICATION_DRY_RUN")
    ENABLE_LIVE_NOTIFICATION_TESTS: bool = Field(default=False, env="ENABLE_LIVE_NOTIFICATION_TESTS")
    TEST_NOTIFICATION_RECIPIENT: Optional[str] = Field(default=None, env="TEST_NOTIFICATION_RECIPIENT")
    DEVELOPER_PREVIEW_ENABLED: bool = Field(default=True, env="DEVELOPER_PREVIEW_ENABLED")
    MAX_NOTIFICATIONS_PER_RECIPIENT_PER_HOUR: int = Field(default=5, env="MAX_NOTIFICATIONS_PER_RECIPIENT_PER_HOUR")

    # Exotel Credentials
    EXOTEL_ACCOUNT_SID: Optional[str] = Field(default=None, env="EXOTEL_ACCOUNT_SID")
    EXOTEL_API_KEY: Optional[str] = Field(default=None, env="EXOTEL_API_KEY")
    EXOTEL_API_TOKEN: Optional[str] = Field(default=None, env="EXOTEL_API_TOKEN")
    EXOTEL_SUB_DOMAIN: str = Field(default="api", env="EXOTEL_SUB_DOMAIN")
    EXOTEL_CALLER_ID: Optional[str] = Field(default=None, env="EXOTEL_CALLER_ID")

    # Meta WhatsApp Cloud API Credentials
    WHATSAPP_API_TOKEN: Optional[str] = Field(default=None, env="WHATSAPP_API_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(default=None, env="WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: Optional[str] = Field(default=None, env="WHATSAPP_WEBHOOK_VERIFY_TOKEN")

    # Twilio Credentials & Settings (Primary Demo Provider)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    TWILIO_SMS_FROM: Optional[str] = Field(default=None, env="TWILIO_SMS_FROM")
    TWILIO_VOICE_FROM: Optional[str] = Field(default=None, env="TWILIO_VOICE_FROM")
    TWILIO_WHATSAPP_FROM: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_FROM")
    TWILIO_WHATSAPP_TO: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_TO")
    TWILIO_WHATSAPP_CONTENT_SID: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_CONTENT_SID")

    # Provider Selection Routing ("twilio" | "exotel" | "meta")
    SMS_PROVIDER: str = Field(default="twilio", env="SMS_PROVIDER")
    VOICE_PROVIDER: str = Field(default="twilio", env="VOICE_PROVIDER")
    WHATSAPP_PROVIDER: str = Field(default="twilio", env="WHATSAPP_PROVIDER")

    # Web Push VAPID Configuration
    VAPID_PUBLIC_KEY: Optional[str] = Field(default=None, env="VAPID_PUBLIC_KEY")
    VAPID_PRIVATE_KEY: Optional[str] = Field(default=None, env="VAPID_PRIVATE_KEY")
    VAPID_CLAIM_EMAIL: str = Field(default="admin@weathergpt.local", env="VAPID_CLAIM_EMAIL")

    class Config:
        env_file = ("backend/.env", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def get_service_readiness(self) -> Dict[str, Any]:
        """
        Returns boolean availability indicators for services without leaking credentials.
        """
        return {
            "gemini": bool(self.GEMINI_API_KEY),
            "supabase": bool(self.SUPABASE_URL and (self.SUPABASE_ANON_KEY or self.SUPABASE_SERVICE_ROLE_KEY)),
            "groq_whisper": bool(self.GROQ_API_KEY),
            "twilio_sms": bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN and self.TWILIO_SMS_FROM),
            "twilio_voice": bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN and self.TWILIO_VOICE_FROM),
            "twilio_whatsapp": bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN and self.TWILIO_WHATSAPP_FROM),
            "exotel_sms": bool(self.EXOTEL_ACCOUNT_SID and self.EXOTEL_API_KEY and self.EXOTEL_API_TOKEN),
            "exotel_voice": bool(self.EXOTEL_ACCOUNT_SID and self.EXOTEL_API_KEY and self.EXOTEL_API_TOKEN and self.EXOTEL_CALLER_ID),
            "whatsapp": bool(self.WHATSAPP_API_TOKEN and self.WHATSAPP_PHONE_NUMBER_ID) or bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN and self.TWILIO_WHATSAPP_FROM),
            "web_push": bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY),
            "notification_dry_run": self.NOTIFICATION_DRY_RUN,
            "open_meteo": bool(self.OPEN_METEO_BASE_URL),
            "open_meteo_geocoding": bool(self.OPEN_METEO_GEOCODING_URL),
            "nasa_power": bool(self.NASA_POWER_BASE_URL),
            "sachet_ndma": bool(self.SACHET_NDMA_ALERT_FEED_URL),
        }

settings = Settings()
