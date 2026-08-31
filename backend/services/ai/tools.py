from typing import Dict, Any, Tuple, Optional, List
from pydantic import BaseModel, Field, ValidationError

from backend.core.errors import (
    InvalidToolCallError,
    UpstreamTimeoutError,
    UpstreamProviderError,
    LocationNotFoundError,
    InvalidCoordinatesError,
)
from backend.services.weather.open_meteo import open_meteo_provider
from backend.services.weather.nasa_power import nasa_power_provider
from backend.services.alerts.sachet import sachet_alert_provider

# =====================================================================
# Strict Pydantic Argument Validation Schemas
# =====================================================================
class ResolveLocationArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=100, description="City, district, or place name to search")
    count: int = Field(default=5, ge=1, le=10, description="Number of candidate matches")

class GetCurrentWeatherArgs(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")

class GetWeatherForecastArgs(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    days: int = Field(default=7, ge=1, le=16, description="Forecast horizon in days (1-16)")
    include_hourly: bool = Field(default=True, description="Whether to include hourly temperature/precipitation breakdown")

class GetHistoricalClimateArgs(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")

class GetActiveAlertsArgs(BaseModel):
    state: Optional[str] = Field(None, max_length=100, description="Indian state name (e.g. 'Tamil Nadu', 'Kerala')")
    district: Optional[str] = Field(None, max_length=100, description="District or city name (e.g. 'Chennai', 'Mumbai')")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    active_only: bool = Field(default=True, description="Whether to return only currently active alerts")

# =====================================================================
# Official Gemini Function Declarations Specification
# =====================================================================
GEMINI_WEATHER_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "resolve_location",
                "description": "Geocodes or searches for a city or place name to retrieve its geographic coordinates (latitude, longitude) and administrative details.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "City, district, or place name (e.g. 'Chennai', 'Mumbai', 'London')"
                        },
                        "count": {
                            "type": "INTEGER",
                            "description": "Maximum number of candidate locations to retrieve (1 to 10, default: 5)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_current_weather",
                "description": "Retrieves current real-time weather conditions (temperature, humidity, wind speed, precipitation, weather condition) for given latitude and longitude coordinates.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "latitude": {
                            "type": "NUMBER",
                            "description": "Latitude in decimal degrees (-90.0 to 90.0)"
                        },
                        "longitude": {
                            "type": "NUMBER",
                            "description": "Longitude in decimal degrees (-180.0 to 180.0)"
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            },
            {
                "name": "get_weather_forecast",
                "description": "Retrieves multi-day and hourly weather forecasts for given latitude and longitude coordinates.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "latitude": {
                            "type": "NUMBER",
                            "description": "Latitude in decimal degrees (-90.0 to 90.0)"
                        },
                        "longitude": {
                            "type": "NUMBER",
                            "description": "Longitude in decimal degrees (-180.0 to 180.0)"
                        },
                        "days": {
                            "type": "INTEGER",
                            "description": "Number of forecast days (1 to 16, default: 7)"
                        },
                        "include_hourly": {
                            "type": "BOOLEAN",
                            "description": "Include hourly temperature and precipitation breakdown (default: true)"
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            },
            {
                "name": "get_historical_climate",
                "description": "Retrieves 30-year NASA POWER climatology baseline averages for agro-meteorological research and historical comparisons. ONLY use when the user explicitly asks for historical climate or monthly/annual baseline averages.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "latitude": {
                            "type": "NUMBER",
                            "description": "Latitude in decimal degrees (-90.0 to 90.0)"
                        },
                        "longitude": {
                            "type": "NUMBER",
                            "description": "Longitude in decimal degrees (-180.0 to 180.0)"
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            },
            {
                "name": "get_active_alerts",
                "description": "Retrieves official active government disaster alerts, emergency cyclone warnings, flood bulletins, and heavy rainfall advisories from SACHET / NDMA for a given state, district, or coordinates.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "state": {
                            "type": "STRING",
                            "description": "Indian state name (e.g. 'Tamil Nadu', 'Maharashtra', 'Odisha', 'Kerala')"
                        },
                        "district": {
                            "type": "STRING",
                            "description": "District or city name (e.g. 'Chennai', 'Mumbai')"
                        },
                        "latitude": {
                            "type": "NUMBER",
                            "description": "Latitude in decimal degrees (-90.0 to 90.0)"
                        },
                        "longitude": {
                            "type": "NUMBER",
                            "description": "Longitude in decimal degrees (-180.0 to 180.0)"
                        },
                        "active_only": {
                            "type": "BOOLEAN",
                            "description": "Whether to return only active alerts (default: true)"
                        }
                    }
                }
            }
        ]
    }
]

ALLOWED_TOOL_NAMES = {
    "resolve_location",
    "get_current_weather",
    "get_weather_forecast",
    "get_historical_climate",
    "get_active_alerts",
}

# =====================================================================
# Safe Tool Execution & Structured Error Dispatcher
# =====================================================================
async def execute_weather_tool(tool_name: str, raw_args: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Validates arguments and executes the requested server-side tool safely.
    Returns (result_dict, provider_name).
    Differentiates invalid tools, argument errors, provider timeouts, and upstream failures.
    """
    if tool_name not in ALLOWED_TOOL_NAMES:
        return {
            "status": "error",
            "error_type": "UNAUTHORIZED_TOOL",
            "message": f"Tool '{tool_name}' is unauthorized or does not exist. Allowed tools: {sorted(list(ALLOWED_TOOL_NAMES))}",
            "tool_name": tool_name
        }, "Security Guard"

    try:
        if tool_name == "resolve_location":
            validated = ResolveLocationArgs(**raw_args)
            results = await open_meteo_provider.resolve_location(query=validated.query, count=validated.count)
            return {
                "status": "success",
                "tool_name": tool_name,
                "provider": "Open-Meteo Geocoding",
                "query": validated.query,
                "count": len(results),
                "locations": [loc.dict() for loc in results]
            }, "Open-Meteo"

        elif tool_name == "get_current_weather":
            validated = GetCurrentWeatherArgs(**raw_args)
            res = await open_meteo_provider.get_current_weather(lat=validated.latitude, lon=validated.longitude)
            return {
                "status": "success",
                "tool_name": tool_name,
                "provider": "Open-Meteo",
                "data": res.dict()
            }, "Open-Meteo"

        elif tool_name == "get_weather_forecast":
            validated = GetWeatherForecastArgs(**raw_args)
            res = await open_meteo_provider.get_forecast(
                lat=validated.latitude,
                lon=validated.longitude,
                days=validated.days,
                include_hourly=validated.include_hourly
            )
            return {
                "status": "success",
                "tool_name": tool_name,
                "provider": "Open-Meteo",
                "data": res.dict()
            }, "Open-Meteo"

        elif tool_name == "get_historical_climate":
            validated = GetHistoricalClimateArgs(**raw_args)
            res = await nasa_power_provider.get_climatology(lat=validated.latitude, lon=validated.longitude)
            return {
                "status": "success",
                "tool_name": tool_name,
                "provider": "NASA POWER",
                "data": res.dict()
            }, "NASA POWER"

        elif tool_name == "get_active_alerts":
            validated = GetActiveAlertsArgs(**raw_args)
            alerts = await sachet_alert_provider.get_alerts_for_location(
                lat=validated.latitude,
                lon=validated.longitude,
                state=validated.state,
                district=validated.district,
                active_only=validated.active_only
            )
            return {
                "status": "success",
                "tool_name": tool_name,
                "provider": "SACHET/NDMA",
                "count": len(alerts),
                "alerts": [a.dict() for a in alerts]
            }, "SACHET/NDMA"

    except ValidationError as ve:
        error_msgs = [f"{e['loc'][0]}: {e['msg']}" for e in ve.errors() if 'loc' in e and len(e['loc']) > 0]
        return {
            "status": "error",
            "error_type": "INVALID_ARGUMENTS",
            "message": f"Validation failed for tool '{tool_name}': {', '.join(error_msgs)}",
            "tool_name": tool_name
        }, "Validation Guard"

    except InvalidCoordinatesError as ice:
        return {
            "status": "error",
            "error_type": "INVALID_COORDINATES",
            "message": str(ice.message),
            "tool_name": tool_name
        }, "Validation Guard"

    except UpstreamTimeoutError as ute:
        return {
            "status": "error",
            "error_type": "PROVIDER_TIMEOUT",
            "message": f"Upstream service '{ute.provider}' timed out after {ute.timeout_seconds}s",
            "tool_name": tool_name
        }, "Network Layer"

    except UpstreamProviderError as upe:
        return {
            "status": "error",
            "error_type": "PROVIDER_ERROR",
            "message": f"Upstream service '{upe.provider}' returned an error (status {upe.status_code})",
            "tool_name": tool_name
        }, "Network Layer"

    except Exception as ex:
        return {
            "status": "error",
            "error_type": "INTERNAL_TOOL_ERROR",
            "message": "An internal error occurred while executing the tool.",
            "tool_name": tool_name
        }, "Internal Engine"
