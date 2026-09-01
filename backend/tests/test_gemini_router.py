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
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 1)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpd"], 1)

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
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 3)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpd"], 3)

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
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 5)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpd"], 5)

    # -----------------------------------------------------------------------
    # Test 4: Primary reaches 12 actual requests -> next request routes to Model 2
    # -----------------------------------------------------------------------
    def test_primary_exhaustion_cascades_to_secondary(self):
        for i in range(12):
            res = asyncio.run(gemini_model_router.select_and_reserve_model())
            model, _ = res
            self.assertEqual(model.name, "gemini-3.5-flash-lite")

        # 13th actual request routes to Model 2
        res_13 = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res_13)
        model_13, reason_13 = res_13
        self.assertEqual(model_13.name, "gemini-3.1-flash-lite")
        self.assertEqual(model_13.priority, 2)

    # -----------------------------------------------------------------------
    # Test 5: Multiple user requests (5 users × 3 calls = 15 total HTTP calls)
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_multiple_users_per_http_request_accounting(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Each user request triggers 2 HTTP calls (1 tool call + 1 text)
        resp_tool = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "get_current_weather", "args": {"latitude": 13.08, "longitude": 80.27}}}], "role": "model"}}]
        })
        resp_text = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "32°C in Chennai."}], "role": "model"}}]
        })

        # 6 user requests × 2 HTTP calls = 12 total HTTP calls
        mock_client.post.side_effect = [resp_tool, resp_text] * 6

        service = GeminiAIService(api_key="mock_key")
        for i in range(6):
            req = ChatRequest(messages=[ChatMessage(role="user", content=f"User {i} query")])
            asyncio.run(service.generate_weather_response(req))

        status = asyncio.run(gemini_model_router.get_status())
        # Model 1 has received 12 actual HTTP calls (6 users × 2 calls)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 12)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpd"], 12)

        # 7th user's first HTTP call should now route to Model 2!
        mock_client.post.side_effect = [resp_text]
        req7 = ChatRequest(messages=[ChatMessage(role="user", content="User 7 query")])
        asyncio.run(service.generate_weather_response(req7))

        status2 = asyncio.run(gemini_model_router.get_status())
        self.assertEqual(status2["gemini-3.1-flash-lite"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 6: Tool loop capacity exhaustion: Model 1 switches to Model 2 mid-loop
    # -----------------------------------------------------------------------
    @patch("backend.core.http_client.http_client_manager.get_client")
    def test_mid_tool_loop_model_switch_when_primary_exhausted(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Pre-fill Model 1 to 11/12 RPM
        for _ in range(11):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Iteration 0: consumes slot #12 on Model 1 (Model 1 is now full: 12/12)
        resp_tool = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"query": "Chennai"}}}], "role": "model"}}]
        })
        # Iteration 1: Model 1 full, seamlessly switches to Model 2 (1/12 on Model 2)
        resp_text = MagicMock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": "Resolved and finished."}], "role": "model"}}]
        })
        mock_client.post.side_effect = [resp_tool, resp_text]

        service = GeminiAIService(api_key="mock_key")
        req = ChatRequest(messages=[ChatMessage(role="user", content="Lookup Chennai")])
        res = asyncio.run(service.generate_weather_response(req))

        status = asyncio.run(gemini_model_router.get_status())
        # Call 1 was on Model 1 (now 12/12)
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 12)
        # Call 2 was on Model 2 (now 1/12)
        self.assertEqual(status["gemini-3.1-flash-lite"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 7: Fallback to Model 2 does not permanently downgrade future requests
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # Test 8: Return to primary after rolling 60s window cools
    # -----------------------------------------------------------------------
    def test_rolling_window_expiration_restores_primary(self):
        for _ in range(12):
            asyncio.run(gemini_model_router.select_and_reserve_model())

        # Backdate timestamps by 65s
        async def backdate():
            async with gemini_model_router._lock:
                gemini_model_router._rpm_timestamps["gemini-3.5-flash-lite"] = [
                    t - 65.0 for t in gemini_model_router._rpm_timestamps["gemini-3.5-flash-lite"]
                ]
        asyncio.run(backdate())

        res_rec = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertEqual(res_rec[0].name, "gemini-3.5-flash-lite")

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
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 1)
        self.assertTrue(status["gemini-3.5-flash-lite"]["is_429_suppressed"])
        # Model 2 succeeded (counted 1)
        self.assertEqual(status["gemini-3.1-flash-lite"]["current_rpm"], 1)

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
        self.assertEqual(status["gemini-3.5-flash-lite"]["current_rpm"], 2)
        self.assertTrue(status["gemini-3.5-flash-lite"]["is_429_suppressed"])
        # Model 2 completed the turn -> current_rpm = 1
        self.assertEqual(status["gemini-3.1-flash-lite"]["current_rpm"], 1)

    # -----------------------------------------------------------------------
    # Test 11: Concurrent reservations are atomic
    # -----------------------------------------------------------------------
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

        self.assertEqual(model_counts.get("gemini-3.5-flash-lite", 0), 12)
        self.assertEqual(model_counts.get("gemini-3.1-flash-lite", 0), 12)
        self.assertEqual(model_counts.get("gemma-4-31b", 0), 1)

    # -----------------------------------------------------------------------
    # Test 12: RPD threshold skips model
    # -----------------------------------------------------------------------
    def test_rpd_threshold_skips_model(self):
        async def set_rpd_max():
            async with gemini_model_router._lock:
                gemini_model_router._rpd_counts["gemini-3.5-flash-lite"] = 1000
        asyncio.run(set_rpd_max())

        res = asyncio.run(gemini_model_router.select_and_reserve_model())
        self.assertIsNotNone(res)
        model, _ = res
        self.assertEqual(model.name, "gemini-3.1-flash-lite")

if __name__ == "__main__":
    unittest.main()
