import asyncio
import html
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, HTTPException, status, UploadFile, File, Form, Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.core.config import settings
from backend.core.logging import logger
from backend.core.cache import cache
from backend.core.http_client import http_client_manager
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
from backend.services.ai.session import session_store
from backend.services.audio.stt import groq_whisper_service, GroqConfigMissingError
from backend.services.notifications.events import alert_event_bus
from backend.services.notifications.orchestrator import notification_orchestrator

# ---------------------------------------------------------------------------
# Background Periodic Cache & Session Eviction Loop
# ---------------------------------------------------------------------------
async def _periodic_cleanup_loop(interval_seconds: float = 1800.0):
    """
    Periodically purges expired in-memory cache entries, conversation sessions,
    and rate-limiting tracking records to maintain predictable memory footprint.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            purged_cache = await cache.cleanup_expired()
            purged_sessions = await session_store.cleanup_expired()
            purged_rates = await notification_orchestrator.cleanup_expired_tracking()
            logger.info(
                f"[Background Cleanup] Purged {purged_cache} cache keys, "
                f"{purged_sessions} sessions, {purged_rates} rate-trackers"
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in background cleanup loop: {e}")

# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} API v{settings.PROJECT_VERSION} in [{settings.ENVIRONMENT}] mode (debug={settings.DEBUG})")
    
    # Wire alert event bus to multi-channel notification orchestrator
    alert_event_bus.subscribe(notification_orchestrator.handle_alert_event)
    logger.info("Subscribed Notification Orchestrator to Disaster Alert Event Bus")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(_periodic_cleanup_loop(interval_seconds=1800.0))

    try:
        yield
    finally:
        # Shutdown sequence
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await http_client_manager.close()
        logger.info("Gracefully stopped background tasks and closed HTTP connection pools")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="WeatherGPT: AI Weather Intelligence and Disaster Awareness Platform API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
@app.exception_handler(GeminiConfigMissingError)
async def gemini_config_missing_handler(request: Request, exc: GeminiConfigMissingError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error_type": "GeminiConfigMissing", "detail": str(exc.message)},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(GroqConfigMissingError)
async def groq_config_missing_handler(request: Request, exc: GroqConfigMissingError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error_type": "GroqConfigMissing", "detail": str(exc.message)},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(LocationNotFoundError)
async def location_not_found_handler(request: Request, exc: LocationNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error_type": "LocationNotFound", "detail": str(exc.message)},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(InvalidCoordinatesError)
async def invalid_coords_handler(request: Request, exc: InvalidCoordinatesError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error_type": "InvalidCoordinates", "detail": str(exc.message)},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(InvalidToolCallError)
async def invalid_tool_call_handler(request: Request, exc: InvalidToolCallError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error_type": "InvalidToolCall", "detail": str(exc.message)},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(UpstreamTimeoutError)
async def upstream_timeout_handler(request: Request, exc: UpstreamTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"error_type": "UpstreamTimeout", "detail": str(exc.message), "provider": exc.provider},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(UpstreamProviderError)
async def upstream_provider_handler(request: Request, exc: UpstreamProviderError):
    if exc.status_code == 429:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_type": "WeatherProviderRateLimited",
                "detail": str(exc.message),
                "provider": exc.provider,
                "hint": "The weather data provider is temporarily rate-limiting requests. Please wait ~60 seconds and retry."
            },
            headers={"Cache-Control": "no-store, private"}
        )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error_type": "UpstreamProviderError", "detail": str(exc.message), "provider": exc.provider},
        headers={"Cache-Control": "no-store, private"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error_type": "InternalServerError", "detail": "An internal server error occurred."},
        headers={"Cache-Control": "no-store, private"}
    )

# ---------------------------------------------------------------------------
# Public Health & Configuration Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check(response: FastAPIResponse):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    services = settings.get_service_readiness()
    return HealthResponse(
        status="healthy",
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.utcnow(),
        services=services,
    )

@app.get("/api/config", response_model=ConfigStatusResponse, tags=["Configuration"])
async def get_config_status(response: FastAPIResponse):
    response.headers["Cache-Control"] = "public, max-age=3600"
    return ConfigStatusResponse(
        project_name=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        configured_services=settings.get_service_readiness(),
        allowed_origins=settings.cors_origins,
    )

# ---------------------------------------------------------------------------
# Geocoding, Weather, Climate & Alert Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/location/search", response_model=LocationSearchResponse, tags=["Location"])
async def search_location(
    response: FastAPIResponse,
    q: str = Query(..., min_length=1, max_length=100, description="City or place name to search for"),
    count: int = Query(default=5, ge=1, le=20, description="Maximum number of results to return")
):
    response.headers["Cache-Control"] = "public, max-age=86400"
    results = await open_meteo_provider.resolve_location(query=q, count=count)
    return LocationSearchResponse(
        query=q,
        count=len(results),
        results=results,
    )

@app.get("/api/weather/current", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_current_weather(
    response: FastAPIResponse,
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
):
    response.headers["Cache-Control"] = "public, max-age=900, stale-while-revalidate=7200"
    return await open_meteo_provider.get_current_weather(lat=lat, lon=lon)

@app.get("/api/weather/forecast", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_weather_forecast(
    response: FastAPIResponse,
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    days: int = Query(default=7, ge=1, le=16, description="Forecast days (1-16)"),
    hourly: bool = Query(default=True, description="Include hourly forecast data")
):
    response.headers["Cache-Control"] = "public, max-age=900, stale-while-revalidate=7200"
    return await open_meteo_provider.get_forecast(lat=lat, lon=lon, days=days, include_hourly=hourly)

@app.get("/api/weather/by-city", response_model=NormalizedWeatherResponse, tags=["Weather"])
async def get_weather_by_city(
    response: FastAPIResponse,
    city: str = Query(..., min_length=1, max_length=100, description="City name to lookup and fetch weather for"),
    days: int = Query(default=7, ge=1, le=16, description="Forecast days (1-16)"),
    hourly: bool = Query(default=True, description="Include hourly forecast data")
):
    response.headers["Cache-Control"] = "public, max-age=900, stale-while-revalidate=7200"
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
    response: FastAPIResponse,
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
):
    response.headers["Cache-Control"] = "public, max-age=604800"
    return await nasa_power_provider.get_climatology(lat=lat, lon=lon)

@app.get("/api/alerts", response_model=AlertListResponse, tags=["Disaster Alerts"])
async def get_disaster_alerts(
    response: FastAPIResponse,
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Latitude for proximity filtering"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Longitude for proximity filtering"),
    state: Optional[str] = Query(None, min_length=1, max_length=100, description="Indian state name"),
    district: Optional[str] = Query(None, min_length=1, max_length=100, description="District or city name"),
    active_only: bool = Query(default=True, description="Filter for active alerts only")
):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=900"
    alerts = await sachet_alert_provider.get_alerts_for_location(
        lat=lat,
        lon=lon,
        state=state,
        district=district,
        active_only=active_only
    )

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

# ---------------------------------------------------------------------------
# Conversational AI & Audio STT Endpoints (Strictly private / no-store)
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse, tags=["AI WeatherGPT"])
async def chat_endpoint(request: ChatRequest, response: FastAPIResponse):
    response.headers["Cache-Control"] = "no-store, private"
    return await gemini_ai_service.generate_weather_response(request)

@app.post("/api/audio/transcribe", tags=["Accessibility & Voice"])
async def transcribe_audio_endpoint(
    response: FastAPIResponse,
    file: UploadFile = File(...),
    language: Optional[str] = Form(default="en")
):
    response.headers["Cache-Control"] = "no-store, private"
    audio_bytes = await file.read()
    return await groq_whisper_service.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=file.filename or "audio.webm",
        content_type=file.content_type or "audio/webm",
        language=language
    )

# ---------------------------------------------------------------------------
# Multi-Channel Emergency Notification Endpoints (Strictly private / no-store)
# ---------------------------------------------------------------------------
@app.get("/api/notifications/preferences", response_model=Optional[NotificationSubscription], tags=["Notifications"])
async def get_notification_preferences(
    response: FastAPIResponse,
    user_id: str = Query(..., min_length=3, max_length=64, regex="^[a-zA-Z0-9_\\-\\.\\@]+$", description="User or client identifier")
):
    response.headers["Cache-Control"] = "no-store, private"
    return await notification_orchestrator.get_subscription(user_identifier=user_id)

@app.post("/api/notifications/preferences", response_model=NotificationSubscription, tags=["Notifications"])
async def update_notification_preferences(request: SubscriptionRequest, response: FastAPIResponse):
    response.headers["Cache-Control"] = "no-store, private"
    return await notification_orchestrator.save_subscription(request)

@app.delete("/api/notifications/preferences", tags=["Notifications"])
async def unsubscribe_notifications(
    response: FastAPIResponse,
    user_id: str = Query(..., min_length=3, max_length=64, regex="^[a-zA-Z0-9_\\-\\.\\@]+$", description="User or client identifier")
):
    response.headers["Cache-Control"] = "no-store, private"
    success = await notification_orchestrator.delete_subscription(user_identifier=user_id)
    return {"status": "unsubscribed" if success else "not_found", "user_identifier": user_id}

@app.get("/api/notifications/subscriber/verify", tags=["Notifications"])
async def verify_subscriber_phone(
    response: FastAPIResponse,
    phone: str = Query(..., min_length=7, max_length=30, description="Phone number to check subscription status for")
):
    response.headers["Cache-Control"] = "no-store, private"
    is_active = await notification_orchestrator.is_phone_subscribed(phone)
    return {"phone": phone, "is_subscribed": is_active}

@app.get("/api/notifications/providers/status", response_model=ProviderStatusResponse, tags=["Notifications"])
async def get_notification_providers_status(response: FastAPIResponse):
    response.headers["Cache-Control"] = "public, max-age=60"
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
        subscription_store_mode="supabase_authoritative_persistent",
        idempotency_store_mode="in_memory_prototype_24h",
        restart_persistence=True
    )

@app.get("/api/notifications/vapid-public-key", response_model=VapidPublicKeyResponse, tags=["Notifications"])
async def get_vapid_public_key(response: FastAPIResponse):
    response.headers["Cache-Control"] = "public, max-age=86400"
    is_configured = bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)
    return VapidPublicKeyResponse(
        public_key=settings.VAPID_PUBLIC_KEY if is_configured else None,
        status="CONFIGURED" if is_configured else "NOT_CONFIGURED",
        claim_email=settings.VAPID_CLAIM_EMAIL
    )

@app.post("/api/notifications/preview", response_model=NotificationPreviewResponse, tags=["Notifications"])
async def preview_notification_message(request: NotificationPreviewRequest, response: FastAPIResponse):
    response.headers["Cache-Control"] = "no-store, private"
    if not settings.DEBUG and not settings.DEVELOPER_PREVIEW_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Notification preview endpoint is disabled in production."
        )

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
