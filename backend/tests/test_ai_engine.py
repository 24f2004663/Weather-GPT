import unittest
import asyncio
from unittest.mock import patch, MagicMock
import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai.gemini import GeminiAIService
from backend.services.ai.session import SessionStore, session_store
from backend.services.ai.tools import (
    execute_weather_tool,
    ResolveLocationArgs,
    GetCurrentWeatherArgs,
    GetWeatherForecastArgs,
    GetHistoricalClimateArgs,
    ALLOWED_TOOL_NAMES,
)
from backend.schemas.chat import ChatRequest, ChatMessage, ChatResponse
from backend.schemas.location import LocationResult
from backend.schemas.weather import NormalizedWeatherResponse, CurrentWeather, DailyForecast, HourlyForecast
from backend.schemas.climate import NasaPowerClimateResponse, MonthlyClimateMetric
from backend.core.errors import (
    GeminiConfigMissingError,
    UpstreamTimeoutError,
    UpstreamProviderError,
    InvalidToolCallError,
)
from datetime import datetime

class TestAIEngine(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.ai_service = GeminiAIService(api_key="mock_test_key", model="gemini-1.5-pro", timeout=2.0)
        asyncio.run(session_store.clear_session("test_session"))

    # 1. Missing Gemini configuration -> 503
    def test_missing_gemini_config_error(self):
        service = GeminiAIService(api_key=None)
        req = ChatRequest(messages=[ChatMessage(role="user", content="What is the weather?")])
        with self.assertRaises(GeminiConfigMissingError):
            asyncio.run(service.generate_weather_response(req))

    @patch("httpx.AsyncClient.post")
    def test_chat_endpoint_missing_config_503(self, mock_post):
        with patch("backend.services.ai.gemini.gemini_ai_service.api_key", None):
            response = self.client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "What is the weather?"}]
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error_type"], "GeminiConfigMissing")

    # 2. Simple conversational response without tool use
    @patch("httpx.AsyncClient.post")
    def test_question_without_tool_use(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Hello! I am WeatherGPT, your weather intelligence assistant."}],
                        "role": "model"
                    },
                    "finishReason": "STOP"
                }
            ]
        }
        mock_post.return_value = mock_response

        req = ChatRequest(messages=[ChatMessage(role="user", content="Hello!")])
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertEqual(res.response_message.role, "assistant")
        self.assertIn("WeatherGPT", res.response_message.content)
        self.assertEqual(res.response_message.source_attribution, ["Gemini AI"])
        self.assertEqual(len(res.tools_used), 0)
        self.assertIsNone(res.referenced_weather_data)

    # 3. Current weather tool use
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_current_weather")
    @patch("httpx.AsyncClient.post")
    def test_current_weather_tool_use(self, mock_post, mock_weather):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_current_weather",
                                    "args": {"latitude": 13.08, "longitude": 80.27}
                                }
                            }
                        ],
                        "role": "model"
                    },
                    "finishReason": "FUNCTION_CALL"
                }
            ]
        }

        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "The current temperature in Chennai is 31.5°C with mainly clear skies."}],
                        "role": "model"
                    },
                    "finishReason": "STOP"
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2]

        mock_weather.return_value = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=LocationResult(name="Chennai", latitude=13.08, longitude=80.27),
            current=CurrentWeather(
                temperature_c=31.5,
                apparent_temperature_c=36.0,
                humidity_percent=75,
                precipitation_mm=0.0,
                wind_speed_kmh=12.0,
                wind_direction_deg=100,
                weather_code=1,
                weather_condition="Mainly Clear",
                icon_key="mainly-clear",
                observed_time=datetime.utcnow()
            )
        )

        req = ChatRequest(
            messages=[ChatMessage(role="user", content="What is the weather in Chennai right now?")],
            coordinates={"latitude": 13.08, "longitude": 80.27}
        )
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertEqual(res.tools_used, ["get_current_weather"])
        self.assertIn("Open-Meteo", res.response_message.source_attribution)
        self.assertIsNotNone(res.referenced_weather_data)
        self.assertIn("31.5°C", res.response_message.content)

    # 4. Multi-step location resolution -> forecast
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.resolve_location")
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_forecast")
    @patch("httpx.AsyncClient.post")
    def test_location_resolution_then_forecast(self, mock_post, mock_forecast, mock_resolve):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "resolve_location",
                                    "args": {"query": "Tokyo", "count": 1}
                                }
                            }
                        ],
                        "role": "model"
                    }
                }
            ]
        }

        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather_forecast",
                                    "args": {"latitude": 35.68, "longitude": 139.76, "days": 3}
                                }
                            }
                        ],
                        "role": "model"
                    }
                }
            ]
        }

        resp_3 = MagicMock()
        resp_3.status_code = 200
        resp_3.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Tokyo will experience mild temperatures around 22°C over the next 3 days."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2, resp_3]

        mock_resolve.return_value = [
            LocationResult(name="Tokyo", latitude=35.68, longitude=139.76, country="Japan")
        ]
        mock_forecast.return_value = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=LocationResult(name="Tokyo", latitude=35.68, longitude=139.76),
            current=CurrentWeather(
                temperature_c=22.0,
                weather_code=1,
                weather_condition="Mainly Clear",
                icon_key="mainly-clear",
                observed_time=datetime.utcnow()
            ),
            daily=[
                DailyForecast(
                    date="2026-08-30",
                    temperature_max_c=24.0,
                    temperature_min_c=19.0,
                    precipitation_sum_mm=0.0,
                    weather_code=1,
                    weather_condition="Mainly Clear",
                    icon_key="mainly-clear",
                    wind_speed_max_kmh=10.0
                )
            ]
        )

        req = ChatRequest(messages=[ChatMessage(role="user", content="Will it rain in Tokyo in the next 3 days?")])
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertIn("resolve_location", res.tools_used)
        self.assertIn("get_weather_forecast", res.tools_used)
        self.assertIn("Open-Meteo", res.response_message.source_attribution)
        self.assertIn("Tokyo", res.response_message.content)

    # 5. Historical climate tool call
    @patch("backend.services.weather.nasa_power.NasaPowerProvider.get_climatology")
    @patch("httpx.AsyncClient.post")
    def test_historical_climate_tool_use(self, mock_post, mock_climate):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_historical_climate",
                                    "args": {"latitude": 30.04, "longitude": 31.23}
                                }
                            }
                        ],
                        "role": "model"
                    }
                }
            ]
        }

        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Cairo's 30-year annual average temperature is 22.4°C."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2]

        mock_climate.return_value = NasaPowerClimateResponse(
            provider="NASA POWER",
            location=LocationResult(name="Cairo", latitude=30.04, longitude=31.23, country="Egypt"),
            annual_averages={"T2M": 22.4, "PRECTOTCORR": 0.2},
            monthly_data=[MonthlyClimateMetric(month="JAN", temperature_2m_c=14.1)],
            parameters_explained={"T2M": "Temp"}
        )

        req = ChatRequest(
            messages=[ChatMessage(role="user", content="What is the historical climate in Cairo?") if hasattr(ChatMessage, 'role') else ChatMessage(role="user", content="Historical climate in Cairo")],
            coordinates={"latitude": 30.04, "longitude": 31.23}
        )
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertIn("get_historical_climate", res.tools_used)
        self.assertIn("NASA POWER", res.response_message.source_attribution)

    # 6. Multiple tool calls in one turn
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_current_weather")
    @patch("backend.services.weather.open_meteo.OpenMeteoProvider.get_forecast")
    @patch("httpx.AsyncClient.post")
    def test_multiple_parallel_tool_calls(self, mock_post, mock_forecast, mock_current):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "get_current_weather", "args": {"latitude": 13.08, "longitude": 80.27}}},
                            {"functionCall": {"name": "get_weather_forecast", "args": {"latitude": 13.08, "longitude": 80.27, "days": 5}}}
                        ],
                        "role": "model"
                    }
                }
            ]
        }
        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Current temperature is 31°C and the 5-day forecast remains warm."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2]

        mock_current.return_value = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=LocationResult(name="Chennai", latitude=13.08, longitude=80.27),
            current=CurrentWeather(temperature_c=31.0, weather_code=0, weather_condition="Clear", icon_key="clear-day", observed_time=datetime.utcnow())
        )
        mock_forecast.return_value = NormalizedWeatherResponse(
            provider="Open-Meteo",
            location=LocationResult(name="Chennai", latitude=13.08, longitude=80.27),
            current=CurrentWeather(temperature_c=31.0, weather_code=0, weather_condition="Clear", icon_key="clear-day", observed_time=datetime.utcnow()),
            daily=[DailyForecast(date="2026-08-30", temperature_max_c=34.0, temperature_min_c=26.0, weather_code=0, weather_condition="Clear", icon_key="clear-day")]
        )

        req = ChatRequest(messages=[ChatMessage(role="user", content="Give me current and 5-day weather for Chennai")], coordinates={"latitude": 13.08, "longitude": 80.27})
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertEqual(len(res.tools_used), 2)
        self.assertIn("get_current_weather", res.tools_used)
        self.assertIn("get_weather_forecast", res.tools_used)

    # 7. Unknown / unauthorized tool call handling
    @patch("httpx.AsyncClient.post")
    def test_unknown_tool_call_handled_gracefully(self, mock_post):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "unauthorized_shell_command",
                                    "args": {"cmd": "rm -rf /"}
                                }
                            }
                        ],
                        "role": "model"
                    }
                }
            ]
        }
        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "I can only access authorized meteorological services."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2]

        req = ChatRequest(messages=[ChatMessage(role="user", content="Execute shell command")])
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertEqual(res.tool_execution_logs[0].status, "error")
        self.assertIn("meteorological services", res.response_message.content)

    # 8. Invalid tool arguments
    @patch("httpx.AsyncClient.post")
    def test_invalid_tool_arguments_recovery(self, mock_post):
        resp_1 = MagicMock()
        resp_1.status_code = 200
        resp_1.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_current_weather",
                                    "args": {"latitude": 999.0, "longitude": 80.0} # Invalid lat
                                }
                            }
                        ],
                        "role": "model"
                    }
                }
            ]
        }
        resp_2 = MagicMock()
        resp_2.status_code = 200
        resp_2.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "The provided coordinates are out of valid range."}],
                        "role": "model"
                    }
                }
            ]
        }
        mock_post.side_effect = [resp_1, resp_2]

        req = ChatRequest(messages=[ChatMessage(role="user", content="Weather at invalid lat")])
        res = asyncio.run(self.ai_service.generate_weather_response(req))

        self.assertEqual(res.tool_execution_logs[0].status, "error")
        self.assertIn("out of valid range", res.response_message.content)

    # 9. Gemini timeout
    @patch("httpx.AsyncClient.post")
    def test_gemini_timeout_handling(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("Gemini timeout")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Current weather")])
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(self.ai_service.generate_weather_response(req))

    # 10. Gemini HTTP 500 error
    @patch("httpx.AsyncClient.post")
    def test_gemini_upstream_500(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        mock_post.return_value = mock_resp

        req = ChatRequest(messages=[ChatMessage(role="user", content="Current weather")])
        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.ai_service.generate_weather_response(req))

    # 11. Empty candidate response
    @patch("httpx.AsyncClient.post")
    def test_empty_candidates_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": []}
        mock_post.return_value = mock_resp

        req = ChatRequest(messages=[ChatMessage(role="user", content="Current weather")])
        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.ai_service.generate_weather_response(req))

    # 12. Safety finishReason response
    @patch("httpx.AsyncClient.post")
    def test_safety_finish_reason(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": [], "role": "model"},
                    "finishReason": "SAFETY"
                }
            ]
        }
        mock_post.return_value = mock_resp

        req = ChatRequest(messages=[ChatMessage(role="user", content="Unsafe request")])
        res = asyncio.run(self.ai_service.generate_weather_response(req))
        self.assertIn("safety policies", res.response_message.content)

    # 13. Session store bounded limits & TTL
    def test_session_store_bounds_and_ttl(self):
        store = SessionStore(max_messages_per_session=3, session_ttl_seconds=1)
        sid, _ = asyncio.run(store.get_or_create_session())

        msgs = [ChatMessage(role="user", content=f"msg {i}") for i in range(5)]
        asyncio.run(store.append_messages(sid, msgs))

        _, history = asyncio.run(store.get_or_create_session(sid))
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].content, "msg 2")
        self.assertEqual(history[-1].content, "msg 4")

    # 14. Frontend/backend contract compatibility
    def test_chat_response_schema_fields(self):
        res = ChatResponse(
            response_message=ChatMessage(role="assistant", content="Test reply", source_attribution=["Open-Meteo"]),
            session_id="sess_123",
            referenced_weather_data={"temp": 30.0},
            tools_used=["get_current_weather"],
            tool_execution_logs=[]
        )
        data = res.dict()
        self.assertIn("response_message", data)
        self.assertIn("session_id", data)
        self.assertIn("referenced_weather_data", data)
        self.assertIn("tools_used", data)


if __name__ == "__main__":
    unittest.main()
