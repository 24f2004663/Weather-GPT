import unittest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock

from backend.services.ai.router import gemini_model_router, GeminiModelRouter, GeminiModelConfig
from backend.services.ai.gemini import GeminiAIService
from backend.services.ai.session import session_store
from backend.schemas.chat import ChatRequest, ChatMessage, ChatResponse

class TestGeminiMultiModelRouter(unittest.TestCase):

    def setUp(self):
        asyncio.run(gemini_model_router.reset_state())
        asyncio.run(session_store.clear_session("test_session_router"))

    def tearDown(self):
        asyncio.run(gemini_model_router.reset_state())

    # 1. First request selects Gemini 3.5 Flash Lite
    def test_first_request_selects_primary(self):
        res = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res)
        model, reason = res
        self.assertEqual(model.name, "gemini-3.5-flash-lite")
        self.assertEqual(model.priority, 1)
        self.assertEqual(reason, "primary_available")

    # 2. 11 requests in rolling window: primary remains eligible
    def test_under_threshold_keeps_primary(self):
        for i in range(11):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            self.assertIsNotNone(res)
            model, _ = res
            self.assertEqual(model.name, "gemini-3.5-flash-lite")

    # 3. 12 requests fills primary, 13th request selects Gemini 3.1 Flash Lite
    def test_primary_exhaustion_cascades_to_secondary(self):
        # 12 requests fill primary (safe_rpm = 12)
        for i in range(12):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            model, _ = res
            self.assertEqual(model.name, "gemini-3.5-flash-lite")

        # 13th request should immediately route to Model 2 (Gemini 3.1 Flash Lite)
        res_13 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_13)
        model_13, reason_13 = res_13
        self.assertEqual(model_13.name, "gemini-3.1-flash-lite")
        self.assertEqual(model_13.priority, 2)
        self.assertEqual(reason_13, "primary_rpm_threshold")

    # 4. Secondary reaches threshold -> selects Gemma 4 31B
    def test_secondary_exhaustion_cascades_to_tertiary(self):
        # Fill Model 1 (12 reqs)
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Fill Model 2 (12 reqs)
        for _ in range(12):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            model, _ = res
            self.assertEqual(model.name, "gemini-3.1-flash-lite")

        # Next request routes to Model 3 (Gemma 4 31B)
        res_tertiary = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_tertiary)
        model_tertiary, reason_tertiary = res_tertiary
        self.assertEqual(model_tertiary.name, "gemma-4-31b")
        self.assertEqual(model_tertiary.priority, 3)

    # 5. Gemma 31B reaches threshold -> selects Gemma 4 26B
    def test_tertiary_exhaustion_cascades_to_quaternary(self):
        # Fill Model 1 (12 reqs)
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())
        # Fill Model 2 (12 reqs)
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())
        # Fill Model 3 (25 reqs)
        for _ in range(25):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            model, _ = res
            self.assertEqual(model.name, "gemma-4-31b")

        # Next request routes to Model 4 (Gemma 4 26B)
        res_quat = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_quat)
        model_quat, _ = res_quat
        self.assertEqual(model_quat.name, "gemma-4-26b")
        self.assertEqual(model_quat.priority, 4)

    # 6. Sliding window test: after 60 seconds (simulated), primary is eligible again
    def test_rolling_window_expiration_restores_primary(self):
        # Fill Model 1 (12 reqs at t=0)
        t0 = time.time()
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # At t=0, Model 1 is exhausted -> routes to Model 2
        res_next = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_next[0].name, "gemini-3.1-flash-lite")

        # Simulate 65 seconds passing by backdating timestamps
        async def backdate():
            async with gemini_model_router._lock:
                gemini_model_router._rpm_timestamps["gemini-3.5-flash-lite"] = [
                    t - 65.0 for t in gemini_model_router._rpm_timestamps["gemini-3.5-flash-lite"]
                ]
        asyncio.run(backdate())

        # Next request should evaluate from Model #1 and SELECT PRIMARY!
        res_recovered = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_recovered)
        model_rec, reason_rec = res_recovered
        self.assertEqual(model_rec.name, "gemini-3.5-flash-lite")
        self.assertEqual(reason_rec, "primary_available")

    # 7. No persistent downgrade: Request evaluates primary first on every new turn
    def test_no_persistent_downgrade(self):
        # Fill Model 1 (12 reqs)
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Request 13 uses Model 2
        res_13 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_13[0].name, "gemini-3.1-flash-lite")

        # Evict one timestamp from Model 1 (simulating 1 request aging out)
        async def remove_one():
            async with gemini_model_router._lock:
                gemini_model_router._rpm_timestamps["gemini-3.5-flash-lite"].pop(0)
        asyncio.run(remove_one())

        # Request 14 must return to Model 1 immediately
        res_14 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_14[0].name, "gemini-3.5-flash-lite")

    # 8. Concurrent requests cannot exceed configured safety RPM
    def test_concurrent_reservations_are_atomic(self):
        async def simulate_burst():
            tasks = [gemini_model_router.select_and_reserve_model() for _ in range(25)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(simulate_burst())
        model_counts = {}
        for res in results:
            if res is not None:
                m_name = res[0].name
                model_counts[m_name] = model_counts.get(m_name, 0) + 1

        # Model 1 must NOT exceed safe_rpm (12)
        self.assertEqual(model_counts.get("gemini-3.5-flash-lite", 0), 12)
        # Model 2 must NOT exceed safe_rpm (12)
        self.assertEqual(model_counts.get("gemini-3.1-flash-lite", 0), 12)
        # Model 3 gets the 25th request
        self.assertEqual(model_counts.get("gemma-4-31b", 0), 1)

    # 9. RPD threshold causes model to be skipped
    def test_rpd_threshold_skips_model(self):
        async def set_rpd_max():
            async with gemini_model_router._lock:
                gemini_model_router._rpd_counts["gemini-3.5-flash-lite"] = 1500
        asyncio.run(set_rpd_max())

        res = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res)
        model, _ = res
        # Primary skipped because RPD limit reached -> routes to Model 2
        self.assertEqual(model.name, "gemini-3.1-flash-lite")

    # 10. Upstream 429 from primary causes fallback to secondary
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_429_on_primary_falls_back_to_secondary(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # First model returns 429, second model returns 200 OK
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "60"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Forecast retrieved via secondary model."}],
                        "role": "model"
                    }
                }
            ]
        }

        mock_client.post.side_effect = [resp_429, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Will it rain?")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("secondary model", res.response_message.content)
        # Verify primary was suppressed
        status = asyncio.run(gemini_model_router.get_status())
        self.assertTrue(status["gemini-3.5-flash-lite"]["is_429_suppressed"])

    # 11. Upstream 429 on primary AND secondary falls back to tertiary (Gemma 4 31B)
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_double_429_falls_back_to_tertiary(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        resp_429_a = MagicMock(status_code=429, headers={})
        resp_429_b = MagicMock(status_code=429, headers={})
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Answer from Gemma 4 31B."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_429_a, resp_429_b, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Weather update?")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("Gemma 4 31B", res.response_message.content)

    # 12. All 4 models failing with 429 raises graceful error
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_all_models_429_raises_graceful_error(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.post.return_value = MagicMock(status_code=429, headers={})

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Test all fail")])
        with self.assertRaises(Exception) as ctx:
            asyncio.run(service.generate_weather_response(req))
        self.assertIn("rate limits", str(ctx.exception).lower())

    # 13. Tool calling and function responses preserve context across router calls
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_tool_calling_with_router(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # 1st call: functionCall get_current_weather
        resp_fc = MagicMock(status_code=200, json=lambda: {
            "candidates": [{
                "content": {
                    "role": "model",
                    "parts": [{
                        "functionCall": {
                            "name": "get_current_weather",
                            "args": {"latitude": 13.08, "longitude": 80.27}
                        }
                    }]
                }
            }]
        })

        # 2nd call: terminal answer referencing weather tool
        resp_text = MagicMock(status_code=200, json=lambda: {
            "candidates": [{
                "content": {
                    "role": "model",
                    "parts": [{"text": "It is currently 32°C in Chennai."}]
                }
            }]
        })

        mock_client.post.side_effect = [resp_fc, resp_text]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="What is the weather in Chennai?")],
            session_id="test_session_router"
        )
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("32°C", res.response_message.content)
        self.assertIn("get_current_weather", res.tools_used)

    # 14. Session context continuity
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_session_context_continuity(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        resp_turn1 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "I am WeatherGPT."}], "role": "model"}}]
        })
        resp_turn2 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "You asked about rain earlier."}], "role": "model"}}]
        })
        mock_client.post.side_effect = [resp_turn1, resp_turn2]

        service = GeminiAIService(api_key="mock_key")
        sid = "test_session_router"

        # Turn 1
        req1 = ChatRequest(messages=[ChatMessage(role="user", content="Who are you?")], session_id=sid)
        res1 = asyncio.run(service.generate_weather_response(req1))
        self.assertEqual(res1.session_id, sid)

        # Turn 2
        req2 = ChatRequest(messages=[ChatMessage(role="user", content="What did I ask?")], session_id=sid)
        res2 = asyncio.run(service.generate_weather_response(req2))
        self.assertIn("rain earlier", res2.response_message.content)

if __name__ == "__main__":
    unittest.main()
