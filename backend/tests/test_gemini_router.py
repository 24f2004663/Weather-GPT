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
        gemini_model_router.reload_registry()
        asyncio.run(gemini_model_router.reset_state())
        asyncio.run(session_store.clear_session("test_session_router"))

    def tearDown(self):
        asyncio.run(gemini_model_router.reset_state())

    # -----------------------------------------------------------------------
    # Test 1: One-turn, one Gemini call (1 HTTP POST -> RPM=1, RPD=1)
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_single_turn_single_http_call_accounting(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.post.return_value = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Terminal answer."}], "role": "model"}}]
        })

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Hello")])
        res = asyncio.run(service.generate_weather_response(req))

        status = asyncio.run(gemini_model_router.get_status())
        # Exactly 1 HTTP POST = 1 RPM reservation, 1 RPD count
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 1)
        self.assertEqual(status["gemma-4-31b-it"]["current_rpd"], 1)

    # -----------------------------------------------------------------------
    # Test 2: One-turn, three tool iterations (3 HTTP POSTs -> RPM=3, RPD=3)
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_three_tool_iterations_consume_three_slots(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Call 1: tool call 1
        resp_1 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"query": "Chennai"}}}], "role": "model"}}]
        })
        # Call 2: tool call 2
        resp_2 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "get_current_weather", "args": {"latitude": 13.08, "longitude": 80.27}}}], "role": "model"}}]
        })
        # Call 3: terminal text
        resp_3 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "The weather in Chennai is 32°C."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_1, resp_2, resp_3]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Weather in Chennai?")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertEqual(mock_client.post.call_count, 3)
        status = asyncio.run(gemini_model_router.get_status())
        # 3 HTTP calls = 3 RPM reservations and 3 RPD counts (NOT 1!)
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 3)
        self.assertEqual(status["gemma-4-31b-it"]["current_rpd"], 3)

    # -----------------------------------------------------------------------
    # Test 3: Maximum 5 iterations -> RPM=5, RPD=5
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_max_five_iterations_consume_five_slots(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # 5 tool calls hitting max_tool_iterations
        resp_fc = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"query": "Chennai"}}}], "role": "model"}}]
        })
        mock_client.post.side_effect = [resp_fc] * 5

        service = GeminiAIService(api_key="mock_key", max_tool_iterations=5)
        req = ChatRequest(messages=[ChatMessage(role="user", content="Loop test")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertEqual(mock_client.post.call_count, 5)
        status = asyncio.run(gemini_model_router.get_status())
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 5)
        self.assertEqual(status["gemma-4-31b-it"]["current_rpd"], 5)

    # -----------------------------------------------------------------------
    # Test 4: Primary reaches 25 actual requests -> next request routes to Model 2
    # -----------------------------------------------------------------------
    def test_primary_exhaustion_cascades_to_secondary(self):
        for i in range(25):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            model, _ = res
            self.assertEqual(model.name, "gemma-4-31b-it")

        # 26th actual request routes to Model 2 (gemma-4-26b-a4b-it)
        res_26 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_26)
        model_26, reason_26 = res_26
        self.assertEqual(model_26.name, "gemma-4-26b-a4b-it")
        self.assertEqual(model_26.priority, 2)

    # -----------------------------------------------------------------------
    # Test 5: Multiple user requests accounting across model boundary
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_multiple_users_per_http_request_accounting(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Pre-fill Model 1 to 23/25
        for _ in range(23):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        resp_tool = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "get_current_weather", "args": {"latitude": 13.08, "longitude": 80.27}}}], "role": "model"}}]
        })
        resp_text = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "32°C in Chennai."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_tool, resp_text]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="User 1 query")])
        asyncio.run(service.generate_weather_response(req))

        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 has reached 25/25
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 25)

        # Next user call should now route to Model 2 (gemma-4-26b-a4b-it)!
        mock_client.post.side_effect = [resp_text]
        req2 = ChatRequest(messages=[ChatMessage(role="user", content="User 2 query")])
        asyncio.run(service.generate_weather_response(req2))

        status2 = asyncio.run(gemini_model_router.get_status())
        self.assertEqual(status2["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 6: Tool loop capacity exhaustion: Model 1 switches to Model 2 mid-loop
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_mid_tool_loop_model_switch_when_primary_exhausted(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Pre-fill Model 1 to 24/25 RPM
        for _ in range(24):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Iteration 0: consumes slot #25 on Model 1 (Model 1 is now full: 25/25)
        resp_tool = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"query": "Chennai"}}}], "role": "model"}}]
        })
        # Iteration 1: Model 1 full, seamlessly switches to Model 2 (1/25 on Model 2)
        resp_text = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Resolved and finished."}], "role": "model"}}]
        })
        mock_client.post.side_effect = [resp_tool, resp_text]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Lookup Chennai")])
        res = asyncio.run(service.generate_weather_response(req))

        status = asyncio.run(gemini_model_router.get_status())
        # Call 1 was on Model 1 (now 25/25)
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 25)
        # Call 2 was on Model 2 (now 1/25)
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 7: Fallback to Model 2 does not permanently downgrade future requests
    # -----------------------------------------------------------------------
    def test_no_persistent_downgrade(self):
        # Fill Model 1 (25 reqs)
        for _ in range(25):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Request 26 uses Model 2
        res_26 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_26[0].name, "gemma-4-26b-a4b-it")

        # Evict one timestamp from Model 1 (simulating 1 request aging out)
        async def remove_one():
            async with gemini_model_router._lock:
                gemini_model_router._rpm_timestamps["gemma-4-31b-it"].pop(0)
        asyncio.run(remove_one())

        # Request 27 must return to Model 1 immediately
        res_27 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_27[0].name, "gemma-4-31b-it")

    # -----------------------------------------------------------------------
    # Test 8: Return to primary after rolling 60s window cools
    # -----------------------------------------------------------------------
    def test_rolling_window_expiration_restores_primary(self):
        for _ in range(25):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Backdate timestamps by 65s
        async def backdate():
            async with gemini_model_router._lock:
                gemini_model_router._rpm_timestamps["gemma-4-31b-it"] = [
                    t - 65.0 for t in gemini_model_router._rpm_timestamps["gemma-4-31b-it"]
                ]
        asyncio.run(backdate())

        res_rec = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_rec[0].name, "gemma-4-31b-it")

    # -----------------------------------------------------------------------
    # Test 9: 429 counts exactly ONE request for that POST and suppresses model
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_429_accounting_and_fallback(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        resp_429 = MagicMock(status_code=429, headers={"Retry-After": "60"})
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Recovered via Model 2."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_429, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Test 429")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("Model 2", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 was attempted once (counted 1) and is now suppressed
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 1)
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        # Model 2 succeeded (counted 1)
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 10: 429 during tool loop (Call 1 OK, Call 2 returns 429)
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_429_during_tool_loop(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Call 1 (Model 1): tool call
        resp_1 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"query": "Delhi"}}}], "role": "model"}}]
        })
        # Call 2 (Model 1): returns 429
        resp_2 = MagicMock(status_code=429, headers={"Retry-After": "60"})
        # Call 3 (Model 2 fallback): receives tool return and produces terminal answer
        resp_3 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Delhi weather answer."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_1, resp_2, resp_3]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Delhi weather")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("Delhi weather answer", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 had 2 calls (1 success + 1 429) -> current_rpm = 2
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 2)
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        # Model 2 completed the turn -> current_rpm = 1
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 11: Concurrent reservations are atomic across 3 cascade models
    # -----------------------------------------------------------------------
    def test_concurrent_reservations_are_atomic(self):
        async def simulate_burst():
            tasks = [gemini_model_router.select_and_reserve_model() for _ in range(60)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(simulate_burst())
        model_counts = {}
        for res in results:
            if res is not None:
                m_name = res[0].name
                model_counts[m_name] = model_counts.get(m_name, 0) + 1

        self.assertEqual(model_counts.get("gemma-4-31b-it", 0), 25)
        self.assertEqual(model_counts.get("gemma-4-26b-a4b-it", 0), 25)
        self.assertEqual(model_counts.get("gemini-3.1-flash-lite", 0), 10)

    # -----------------------------------------------------------------------
    # Test 12: RPD threshold skips model
    # -----------------------------------------------------------------------
    def test_rpd_threshold_skips_model(self):
        async def set_rpd_max():
            async with gemini_model_router._lock:
                gemini_model_router._rpd_counts["gemma-4-31b-it"] = 1000
        asyncio.run(set_rpd_max())

        res = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res)
        model, _ = res
        self.assertEqual(model.name, "gemma-4-26b-a4b-it")

    # -----------------------------------------------------------------------
    # Test 13: 503 / high demand triggers fallback cascade to Model 2
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_503_temporary_failure_triggers_fallback_to_secondary(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Primary model (gemma-4-31b-it) returns 503 Service Unavailable ("high demand")
        resp_503 = MagicMock(status_code=503, text="This model is currently experiencing high demand.")
        # Secondary model (gemma-4-26b-a4b-it) succeeds with 200 OK
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Successfully answered via Gemma 4 26B-A4B-IT fallback."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_503, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Forecast for Bengaluru")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("fallback", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 was attempted once (counted 1) and is now suppressed
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 1)
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        # Model 2 took over and succeeded
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 14: Model name with accidental trailing newline/whitespace is stripped
    # -----------------------------------------------------------------------
    def test_settings_strips_trailing_whitespace_and_newlines(self):
        from backend.core.config import Settings
        s = Settings(GEMINI_MODEL_1="gemma-4-31b-it\n", GEMINI_API_KEY="test_key \n")
        self.assertEqual(s.GEMINI_MODEL_1, "gemma-4-31b-it")
        self.assertEqual(s.GEMINI_API_KEY, "test_key")

    # -----------------------------------------------------------------------
    # Test 15: HTTP 404 unavailable model triggers automatic fallback cascade
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_404_unavailable_model_triggers_fallback_cascade(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Primary model returns 404 (e.g. no longer available to new users)
        resp_404 = MagicMock(status_code=404, text='{"error": {"code": 404, "message": "This model is no longer available"}}')
        # Secondary model returns 200 OK
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Resolved via secondary model after 404."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_404, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Weather check")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("secondary model after 404", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 was attempted once and suppressed
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 1)
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        # Model 2 succeeded
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 16: Verify exact cascade priority order and model IDs
    # -----------------------------------------------------------------------
    def test_exact_cascade_priority_and_models(self):
        models = [m.name for m in gemini_model_router._models]
        self.assertEqual(models, [
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
            "gemini-3.1-flash-lite",
        ])

    # -----------------------------------------------------------------------
    # Test 17: Fallback reaches final tier (gemini-3.1-flash-lite)
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_cascade_reaches_final_tier_gemini_31_flash_lite(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Model 1 returns 404
        resp_404 = MagicMock(status_code=404, text="Model 1 not found")
        # Model 2 returns 503
        resp_503 = MagicMock(status_code=503, text="Model 2 high demand")
        # Model 3 (gemini-3.1-flash-lite) returns 200 OK
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Answer from final tier: gemini-3.1-flash-lite."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_404, resp_503, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Final fallback test")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("gemini-3.1-flash-lite", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        self.assertTrue(status["gemma-4-26b-a4b-it"]["is_429_suppressed"])
        self.assertEqual(status["gemini-3.1-flash-lite"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 18: HTTP 500 internal server error triggers fallback cascade
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_500_internal_error_triggers_fallback_cascade(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Primary model (gemma-4-31b-it) returns 500 Internal Server Error
        resp_500 = MagicMock(status_code=500, text='{"error": {"code": 500, "message": "Internal error encountered."}}')
        # Secondary model (gemma-4-26b-a4b-it) returns 200 OK
        resp_200 = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Answered via secondary model after 500."}], "role": "model"}}]
        })

        mock_client.post.side_effect = [resp_500, resp_200]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="500 fallback test")])
        res = asyncio.run(service.generate_weather_response(req))

        self.assertIn("secondary model after 500", res.response_message.content)
        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 was attempted once and is now suppressed
        self.assertEqual(status["gemma-4-31b-it"]["current_rpm"], 1)
        self.assertTrue(status["gemma-4-31b-it"]["is_429_suppressed"])
        # Model 2 took over and succeeded
        self.assertEqual(status["gemma-4-26b-a4b-it"]["current_rpm"], 1)

if __name__ == "__main__":
    unittest.main()
