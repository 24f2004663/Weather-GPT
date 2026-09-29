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

    # SACHET CAP detail enrichment.
    # The RSS index carries only title/link/pubDate; severity, urgency, expiry,
    # official instructions and structured areaDesc live in the per-alert CAP XML
    # behind each item's <link>. A CAP document is immutable for a given
    # identifier, so it is cached far longer than the index itself.
    SACHET_CAP_ENRICH_ENABLED: bool = Field(default=True, env="SACHET_CAP_ENRICH_ENABLED")
    SACHET_CAP_MAX_CONCURRENCY: int = Field(default=8, env="SACHET_CAP_MAX_CONCURRENCY")
    SACHET_CAP_TIMEOUT_SECONDS: float = Field(default=10.0, env="SACHET_CAP_TIMEOUT_SECONDS")
    SACHET_CAP_DETAIL_TTL_SECONDS: int = Field(default=21600, env="SACHET_CAP_DETAIL_TTL_SECONDS")  # 6 hours

    # Weather & Feed URLs
    OPEN_METEO_BASE_URL: str = Field(default="https://api.open-meteo.com/v1", env="OPEN_METEO_BASE_URL")
    OPEN_METEO_GEOCODING_URL: str = Field(default="https://geocoding-api.open-meteo.com/v1/search", env="OPEN_METEO_GEOCODING_URL")
    NASA_POWER_BASE_URL: str = Field(default="https://power.larc.nasa.gov/api/temporal/climatology/point", env="NASA_POWER_BASE_URL")
    SACHET_NDMA_ALERT_FEED_URL: str = Field(default="https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml", env="SACHET_NDMA_ALERT_FEED_URL")

    # Reverse geocoding (coordinates -> place name). Open-Meteo's geocoding API is
    # forward-only, so this uses Nominatim, whose usage policy requires a descriptive
    # User-Agent and roughly one request per second — hence the long cache TTL.
    NOMINATIM_REVERSE_URL: str = Field(default="https://nominatim.openstreetmap.org/reverse", env="NOMINATIM_REVERSE_URL")
    REVERSE_GEOCODE_USER_AGENT: str = Field(
        default="WeatherGPT/0.7 (SIH26068 disaster alert prototype)",
        env="REVERSE_GEOCODE_USER_AGENT",
    )
    REVERSE_GEOCODE_TIMEOUT_SECONDS: float = Field(default=8.0, env="REVERSE_GEOCODE_TIMEOUT_SECONDS")
    REVERSE_GEOCODE_CACHE_TTL_SECONDS: int = Field(default=604800, env="REVERSE_GEOCODE_CACHE_TTL_SECONDS")  # 7 days

    # Numerical Weather Prediction model selection. Open-Meteo blends several NWP
    # sources under "best_match"; naming a model pins the forecast to that single
    # global model so a forecast can be attributed to the system that produced it.
    OPEN_METEO_DEFAULT_MODEL: str = Field(default="best_match", env="OPEN_METEO_DEFAULT_MODEL")

    # Primary LLM Provider & Multi-Model Quota Router
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash-lite", env="GEMINI_MODEL")

    # Priority Model 1: Gemini 3.5 Flash-Lite (Primary)
    GEMINI_MODEL_1: str = Field(default="gemini-3.5-flash-lite", env="GEMINI_MODEL_1")
    GEMINI_3_5_FLASH_LITE_SAFE_RPM: int = Field(default=12, env="GEMINI_3_5_FLASH_LITE_SAFE_RPM")
    GEMINI_3_5_FLASH_LITE_SAFE_RPD: int = Field(default=500, env="GEMINI_3_5_FLASH_LITE_SAFE_RPD")
    GEMINI_3_5_FLASH_LITE_SAFE_TPM: int = Field(default=250000, env="GEMINI_3_5_FLASH_LITE_SAFE_TPM")

    # Priority Model 2: Gemma 4 31B-IT (First Fallback)
    GEMINI_MODEL_2: str = Field(default="gemma-4-31b-it", env="GEMINI_MODEL_2")
    GEMMA_4_31B_SAFE_RPM: int = Field(default=25, env="GEMMA_4_31B_SAFE_RPM")
    GEMMA_4_31B_SAFE_RPD: int = Field(default=1000, env="GEMMA_4_31B_SAFE_RPD")
    GEMMA_4_31B_SAFE_TPM: int = Field(default=250000, env="GEMMA_4_31B_SAFE_TPM")

    # Priority Model 3: Gemma 4 26B-A4B-IT (Second Fallback)
    GEMINI_MODEL_3: str = Field(default="gemma-4-26b-a4b-it", env="GEMINI_MODEL_3")
    GEMMA_4_26B_SAFE_RPM: int = Field(default=25, env="GEMMA_4_26B_SAFE_RPM")
    GEMMA_4_26B_SAFE_RPD: int = Field(default=1000, env="GEMMA_4_26B_SAFE_RPD")
    GEMMA_4_26B_SAFE_TPM: int = Field(default=250000, env="GEMMA_4_26B_SAFE_TPM")

    # Priority Model 4: Gemini 3.1 Flash Lite (Final Fallback)
    GEMINI_MODEL_4: Optional[str] = Field(default="gemini-3.1-flash-lite", env="GEMINI_MODEL_4")
    GEMINI_FLASH_LITE_SAFE_RPM: int = Field(default=12, env="GEMINI_FLASH_LITE_SAFE_RPM")
    GEMINI_FLASH_LITE_SAFE_RPD: int = Field(default=1000, env="GEMINI_FLASH_LITE_SAFE_RPD")
    GEMINI_FLASH_LITE_SAFE_TPM: int = Field(default=250000, env="GEMINI_FLASH_LITE_SAFE_TPM")

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

    # Twilio Credentials & Settings (Legacy / Secondary)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    TWILIO_SMS_FROM: Optional[str] = Field(default=None, env="TWILIO_SMS_FROM")
    TWILIO_VOICE_FROM: Optional[str] = Field(default=None, env="TWILIO_VOICE_FROM")
    TWILIO_WHATSAPP_FROM: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_FROM")
    TWILIO_WHATSAPP_TO: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_TO")
    TWILIO_WHATSAPP_CONTENT_SID: Optional[str] = Field(default=None, env="TWILIO_WHATSAPP_CONTENT_SID")

    # TextBee SMS Service (Android Phone + SIM Gateway)
    TEXTBEE_API_KEY: Optional[str] = Field(default=None, env="TEXTBEE_API_KEY")
    TEXTBEE_DEVICE_ID: Optional[str] = Field(default=None, env="TEXTBEE_DEVICE_ID")
    TEXTBEE_BASE_URL: str = Field(default="https://api.textbee.dev/api/v1", env="TEXTBEE_BASE_URL")

    # Provider Selection Routing ("textbee" | "exotel" | "twilio")
    SMS_PROVIDER: str = Field(default="textbee", env="SMS_PROVIDER")
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
            "textbee_sms": bool(self.TEXTBEE_API_KEY and self.TEXTBEE_DEVICE_ID),
            "twilio_sms": False,  # Twilio removed from active SMS execution path
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

    def __init__(self, **values: Any):
        super().__init__(**values)
        if self.GEMINI_API_KEY:
            object.__setattr__(self, "GEMINI_API_KEY", self.GEMINI_API_KEY.strip())
        if self.GEMINI_MODEL:
            object.__setattr__(self, "GEMINI_MODEL", self.GEMINI_MODEL.strip())
        if self.GEMINI_MODEL_1:
            object.__setattr__(self, "GEMINI_MODEL_1", self.GEMINI_MODEL_1.strip())
        if self.GEMINI_MODEL_2:
            object.__setattr__(self, "GEMINI_MODEL_2", self.GEMINI_MODEL_2.strip())
        if self.GEMINI_MODEL_3:
            object.__setattr__(self, "GEMINI_MODEL_3", self.GEMINI_MODEL_3.strip())
        if self.GEMINI_MODEL_4:
            object.__setattr__(self, "GEMINI_MODEL_4", self.GEMINI_MODEL_4.strip())

        # Prohibited models protection: automatically remap deprecated models if present in env
        PROHIBITED_MODELS = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.8-flash", "gemma-4-31b", "gemma-4-26b"}
        if self.GEMINI_MODEL in PROHIBITED_MODELS:
            object.__setattr__(self, "GEMINI_MODEL", "gemini-3.5-flash-lite")
        if self.GEMINI_MODEL_1 in PROHIBITED_MODELS:
            object.__setattr__(self, "GEMINI_MODEL_1", "gemini-3.5-flash-lite")
        if self.GEMINI_MODEL_2 in PROHIBITED_MODELS:
            object.__setattr__(self, "GEMINI_MODEL_2", "gemma-4-31b-it")
        if self.GEMINI_MODEL_3 in PROHIBITED_MODELS:
            object.__setattr__(self, "GEMINI_MODEL_3", "gemma-4-26b-a4b-it")
        if self.GEMINI_MODEL_4 in PROHIBITED_MODELS:
            object.__setattr__(self, "GEMINI_MODEL_4", "gemini-3.1-flash-lite")

        # Automatic upgrade of legacy 3-model cascade if present in environment
        if self.GEMINI_MODEL_1 == "gemma-4-31b-it" and self.GEMINI_MODEL_2 == "gemma-4-26b-a4b-it":
            object.__setattr__(self, "GEMINI_MODEL", "gemini-3.5-flash-lite")
            object.__setattr__(self, "GEMINI_MODEL_1", "gemini-3.5-flash-lite")
            object.__setattr__(self, "GEMINI_MODEL_2", "gemma-4-31b-it")
            object.__setattr__(self, "GEMINI_MODEL_3", "gemma-4-26b-a4b-it")
            object.__setattr__(self, "GEMINI_MODEL_4", "gemini-3.1-flash-lite")


settings = Settings()
