import html
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.errors import (
    WeatherGPTError,
    LocationNotFoundError,
    UpstreamProviderError,
    UpstreamTimeoutError,
    InvalidCoordinatesError,
    GeminiConfigMissingError,
    InvalidToolCallError,
)
from backend.schemas.health import HealthResponse
from backend.schemas.config import ConfigStatusResponse
from backend.schemas.location import LocationSearchResponse
from backend.schemas.weather import NormalizedWeatherResponse
from backend.schemas.climate import NasaPowerClimateResponse
from backend.schemas.alerts import AlertListResponse, AlertSeverity, DisasterAlert, AlertUrgency, AlertCertainty, AlertStatus, GeographicScope
from backend.schemas.chat import ChatRequest, ChatResponse, ChatMessage
from backend.schemas.notifications import (
    SubscriptionRequest,
    NotificationSubscription,
    NotificationPreviewRequest,
    NotificationPreviewResponse,
    ProviderStatusResponse,
    VapidPublicKeyResponse,
    NotificationChannel,
)
from backend.services.weather.open_meteo import open_meteo_provider
from backend.services.weather.nasa_power import nasa_power_provider
from backend.services.alerts.sachet import sachet_alert_provider
from backend.services.ai.gemini import gemini_ai_service
from backend.services.audio.stt import groq_whisper_service, GroqConfigMissingError
from backend.services.notifications.events import alert_event_bus
from backend.services.notifications.orchestrator import notification_orchestrator

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="WeatherGPT: AI Weather Intelligence and Disaster Awareness Platform API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS configuration — supports local dev, configured ALLOWED_ORIGINS, and Vercel deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.PROJECT_NAME} API v{settings.PROJECT_VERSION} in [{settings.ENVIRONMENT}] mode")
    # Wire alert event bus to multi-channel notification orchestrator
    alert_event_bus.subscribe(notification_orchestrator.handle_alert_event)
    logger.info("Subscribed Notification Orchestrator to Disaster Alert Event Bus")

# Exception Handlers
@app.exception_handler(GeminiConfigMissingError)
async def gemini_config_missing_handler(request: Request, exc: GeminiConfigMissingError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error_type": "GeminiConfigMissing", "detail": str(exc.message)},
    )

@app.exception_handler(GroqConfigMissingError)
async def groq_config_missing_handler(request: Request, exc: GroqConfigMissingError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error_type": "GroqConfigMissing", "detail": str(exc.message)},
    )

@app.exception_handler(LocationNotFoundError)
async def location_not_found_handler(request: Request, exc: LocationNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error_type": "LocationNotFound", "detail": str(exc.message)},
    )

@app.exception_handler(InvalidCoordinatesError)
async def invalid_coords_handler(request: Request, exc: InvalidCoordinatesError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error_type": "InvalidCoordinates", "detail": str(exc.message)},
    )

@app.exception_handler(InvalidToolCallError)
async def invalid_tool_call_handler(request: Request, exc: InvalidToolCallError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error_type": "InvalidToolCall", "detail": str(exc.message)},
    )

@app.exception_handler(UpstreamTimeoutError)
async def upstream_timeout_handler(request: Request, exc: UpstreamTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"error_type": "UpstreamTimeout", "detail": str(exc.message), "provider": exc.provider},
    )

@app.exception_handler(UpstreamProviderError)
async def upstream_provider_handler(request: Request, exc: UpstreamProviderError):
    # 429 from upstream → surface as 503 Service Unavailable, NOT as 502
    if exc.status_code == 429:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_type": "WeatherProviderRateLimited",
                "detail": str(exc.message),
                "provider": exc.provider,
                "hint": "The weather data provider is temporarily rate-limiting requests. Please wait ~60 seconds and retry."
            },
        )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error_type": "UpstreamProviderError", "detail": str(exc.message), "provider": exc.provider},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error_type": "InternalServerError", "detail": "An internal server error occurred."},
    )

# Endpoints
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint reporting overall system status and readiness of configured adapters.
    """
    services = settings.get_service_readiness()
    return HealthResponse(
        status="healthy",
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.utcnow(),
        services=services,
    )

@app.get("/api/config", response_model=ConfigStatusResponse, tags=["Configuration"])
async def get_config_status():
    """
    Returns public configuration metadata and configured service states without leaking secrets.
    """
    return ConfigStatusResponse(
        project_name=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        configured_services=settings.get_service_readiness(),
        allowed_origins=settings.cors_origins,
    )

@app.get("/api/location/search", response_model=LocationSearchResponse, tags=["Location"])
async def search_location(
    q: str = Query(..., min_length=1, max_length=100, description="City or place name to search for"),
    count: int = Query(default=5, ge=1, le=20, description="Maximum number of results to return")
):
    """
    Geocodes a place name into normalized geographic coordinates and administrative metadata.
    """
    results = await open_meteo_provider.resolve_location(query=q, count=count)
    return LocationSearchResponse(
        query=q,
        count=len(results),
        results=results,
    )

@app.get("/api/weather/current", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_current_weather(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
):
    """
    Returns normalized current weather conditions for given coordinates.
    """
    return await open_meteo_provider.get_current_weather(lat=lat, lon=lon)

@app.get("/api/weather/forecast", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_weather_forecast(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    days: int = Query(default=7, ge=1, le=16, description="Forecast days (1-16)"),
    hourly: bool = Query(default=True, description="Include hourly forecast data")
):
    """
    Returns normalized current weather and multi-day/hourly forecast for given coordinates.
    """
    return await open_meteo_provider.get_forecast(lat=lat, lon=lon, days=days, include_hourly=hourly)

@app.get("/api/weather/by-city", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_weather_by_city(
    city: str = Query(..., min_length=1, max_length=100, description="City name to lookup and fetch weather for"),
    days: int = Query(default=7, ge=1, le=16, description="Forecast days (1-16)"),
    hourly: bool = Query(default=True, description="Include hourly forecast data")
):
    """
    Resolves city name into coordinates and returns normalized weather forecast in one step.
    """
    locations = await open_meteo_provider.resolve_location(query=city, count=1)
    if not locations:
        raise LocationNotFoundError(f"Could not resolve city location '{city}'")
    
    target_loc = locations[0]
    return await open_meteo_provider.get_forecast(
        lat=target_loc.latitude,
        lon=target_loc.longitude,
        days=days,
        include_hourly=hourly,
        location_meta=target_loc
    )

@app.get("/api/climate/historical", response_model=NasaPowerClimateResponse, tags=["Climate"])
async def get_historical_climate(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
):
    """
    Returns 30-year NASA POWER climatology baseline averages for agro-meteorological research.
    """
    return await nasa_power_provider.get_climatology(lat=lat, lon=lon)

@app.get("/api/alerts", response_model=AlertListResponse, tags=["Disaster Alerts"])
async def get_disaster_alerts(
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitude for proximity filtering"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitude for proximity filtering"),
    state: Optional[str] = Query(None, min_length=1, max_length=100, description="Indian state name"),
    district: Optional[str] = Query(None, min_length=1, max_length=100, description="District or city name"),
    active_only: bool = Query(default=True, description="Filter for active alerts only")
):
    """
    Returns normalized official disaster alerts from SACHET/NDMA CAP feed.
    """
    alerts = await sachet_alert_provider.get_alerts_for_location(
        lat=lat,
        lon=lon,
        state=state,
        district=district,
        active_only=active_only
    )

    # Determine highest severity
    severity_order = [
        AlertSeverity.EXTREME,
        AlertSeverity.SEVERE,
        AlertSeverity.MODERATE,
        AlertSeverity.MINOR,
        AlertSeverity.UNKNOWN
    ]
    highest_sev = None
    if alerts:
        present_sevs = {a.severity for a in alerts}
        for sev in severity_order:
            if sev in present_sevs:
                highest_sev = sev
                break

    query_label = district or state or (f"({lat:.2f}, {lon:.2f})" if lat is not None and lon is not None else "India (All)")

    return AlertListResponse(
        source="SACHET/NDMA",
        query_location=query_label,
        total_count=len(alerts),
        active_count=len([a for a in alerts if a.is_active]),
        highest_severity=highest_sev,
        alerts=alerts,
        cached=False,
        last_synced=datetime.utcnow()
    )

@app.post("/api/chat", response_model=ChatResponse, tags=["AI WeatherGPT"])
async def chat_endpoint(request: ChatRequest):
    """
    Processes conversational weather intelligence queries using Google Gemini AI
    with controlled server-side tool calling and session state.
    """
    return await gemini_ai_service.generate_weather_response(request)

@app.post("/api/audio/transcribe", tags=["Accessibility & Voice"])
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default="en")
):
    """
    Transcribes voice audio using Groq Whisper (whisper-large-v3).
    """
    audio_bytes = await file.read()
    return await groq_whisper_service.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=file.filename or "audio.webm",
        content_type=file.content_type or "audio/webm",
        language=language
    )

# =====================================================================
# Phase 7 — Multi-Channel Emergency Notification Endpoints
# =====================================================================
@app.get("/api/notifications/preferences", response_model=Optional[NotificationSubscription], tags=["Notifications"])
async def get_notification_preferences(
    user_id: str = Query(..., min_length=3, max_length=64, regex="^[a-zA-Z0-9_\\-\\.\\@]+$", description="User or client identifier")
):
    """
    Retrieves emergency alert subscription preferences for a given user.
    """
    return await notification_orchestrator.get_subscription(user_identifier=user_id)

@app.post("/api/notifications/preferences", response_model=NotificationSubscription, tags=["Notifications"])
async def update_notification_preferences(request: SubscriptionRequest):
    """
    Saves or updates explicit opt-in preferences for multi-channel emergency disaster alerts.
    """
    return await notification_orchestrator.save_subscription(request)

@app.delete("/api/notifications/preferences", tags=["Notifications"])
async def unsubscribe_notifications(
    user_id: str = Query(..., min_length=3, max_length=64, regex="^[a-zA-Z0-9_\\-\\.\\@]+$", description="User or client identifier")
):
    """
    Unsubscribes a user from all proactive emergency communication channels.
    """
    success = await notification_orchestrator.delete_subscription(user_identifier=user_id)
    return {"status": "unsubscribed" if success else "not_found", "user_identifier": user_id}

@app.get("/api/notifications/providers/status", response_model=ProviderStatusResponse, tags=["Notifications"])
async def get_notification_providers_status():
    """
    Returns public availability and dry-run state for notification delivery channels without leaking credentials.
    """
    readiness = settings.get_service_readiness()
    dry_run = settings.NOTIFICATION_DRY_RUN

    channels = {}
    channels["WHATSAPP"] = "DRY_RUN" if dry_run else ("CONFIGURED" if readiness["whatsapp"] else "NOT_CONFIGURED")
    channels["SMS"] = "DRY_RUN" if dry_run else ("CONFIGURED" if readiness["exotel_sms"] else "NOT_CONFIGURED")
    channels["VOICE_IVR"] = "DRY_RUN" if dry_run else ("CONFIGURED" if readiness["exotel_voice"] else "NOT_CONFIGURED")
    channels["WEB_PUSH"] = "DRY_RUN" if dry_run else ("CONFIGURED" if readiness["web_push"] else "NOT_CONFIGURED")

    return ProviderStatusResponse(
        channels=channels,
        dry_run_enabled=dry_run,
        live_tests_enabled=settings.ENABLE_LIVE_NOTIFICATION_TESTS,
        subscription_store_mode="in_memory_prototype",
        idempotency_store_mode="in_memory_prototype_24h",
        restart_persistence=False
    )

@app.get("/api/notifications/vapid-public-key", response_model=VapidPublicKeyResponse, tags=["Notifications"])
async def get_vapid_public_key():
    """
    Returns the public VAPID key for browser Web Push subscription registration.
    The private VAPID key is strictly preserved server-side and never returned.
    """
    is_configured = bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)
    return VapidPublicKeyResponse(
        public_key=settings.VAPID_PUBLIC_KEY if is_configured else None,
        status="CONFIGURED" if is_configured else "NOT_CONFIGURED",
        claim_email=settings.VAPID_CLAIM_EMAIL
    )

@app.post("/api/notifications/preview", response_model=NotificationPreviewResponse, tags=["Notifications"])
async def preview_notification_message(request: NotificationPreviewRequest):
    """
    Developer/Admin safe preview endpoint to simulate rendered disaster alert formatting across channels and languages.
    Strictly simulated; cannot trigger live dispatch. Disabled in production when DEVELOPER_PREVIEW_ENABLED=False.
    """
    if not settings.DEBUG and not settings.DEVELOPER_PREVIEW_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Notification preview endpoint is disabled in production."
        )

    # Representative disaster alert model
    sample_alert = DisasterAlert(
        alert_id=request.alert_id or "SAMPLE-ALERT-101",
        title="Cyclone Warning for Coastal Tamil Nadu",
        event_type="Cyclone",
        severity=AlertSeverity.EXTREME,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        headline="Severe Cyclonic Storm Advancing Towards Coast",
        description="Heavy to very heavy rainfall expected across coastal districts.",
        instruction="Fishermen are advised not to venture into sea. Stay indoors in secure shelters.",
        affected_area="Coastal Tamil Nadu (Chennai, Tiruvallur)",
        scope=GeographicScope.DISTRICT,
        affected_states=["Tamil Nadu"],
        affected_districts=["Chennai", "Tiruvallur"],
        issued_time=datetime.utcnow(),
        is_active=True
    )

    return notification_orchestrator.preview_message(
        alert=sample_alert,
        channel=request.channel,
        language=request.language,
        recipient=request.recipient or "+919876543210"
    )

@app.post("/api/notifications/webhook/twilio-whatsapp", tags=["Notifications"])
async def twilio_whatsapp_inbound_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    ProfileName: Optional[str] = Form(default=None)
):
    """
    Inbound Webhook Endpoint for Twilio WhatsApp Messages.
    Processes user incoming questions via WeatherGPT conversational AI engine and returns TwiML reply.
    """
    clean_sender = From.replace("whatsapp:", "")
    logger.info(f"Inbound Twilio WhatsApp message from {clean_sender[:6]}***: {Body}")

    try:
        chat_req = ChatRequest(
            messages=[ChatMessage(role="user", content=Body.strip())]
        )
        ai_resp = await gemini_ai_service.generate_weather_response(chat_req)
        reply_text = ai_resp.response_message.content
    except Exception as e:
        logger.error(f"Error generating AI reply for WhatsApp inbound message: {e}")
        reply_text = "WeatherGPT Alert: Unable to retrieve weather intelligence right now. Please try again shortly."

    safe_reply = html.escape(reply_text)
    twiml_content = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_reply}</Message></Response>'
    return Response(content=twiml_content, media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
