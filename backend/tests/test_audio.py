import unittest
import asyncio
import io
import httpx
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.audio.stt import GroqWhisperService, GroqConfigMissingError, groq_whisper_service
from backend.services.audio.tts import browser_tts_service
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError, WeatherGPTError

class TestAudioServices(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.stt_service = GroqWhisperService(api_key="mock_groq_key", model="whisper-large-v3", timeout=2.0)

    def test_missing_groq_config_error(self):
        svc = GroqWhisperService(api_key=None)
        with self.assertRaises(GroqConfigMissingError):
            asyncio.run(svc.transcribe_audio(b"dummy_audio_bytes"))

    def test_empty_audio_buffer_error(self):
        with self.assertRaises(WeatherGPTError):
            asyncio.run(self.stt_service.transcribe_audio(b""))

    @patch("httpx.AsyncClient.post")
    def test_successful_transcription(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "Will it rain in Chennai tomorrow?"}
        mock_post.return_value = mock_resp

        res = asyncio.run(self.stt_service.transcribe_audio(b"fake_audio_content", language="en"))
        self.assertEqual(res["transcription"], "Will it rain in Chennai tomorrow?")
        self.assertEqual(res["model"], "whisper-large-v3")
        self.assertIn("execution_time_ms", res)

    @patch("httpx.AsyncClient.post")
    def test_groq_timeout_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("Timeout")
        with self.assertRaises(UpstreamTimeoutError):
            asyncio.run(self.stt_service.transcribe_audio(b"fake_audio_content"))

    @patch("httpx.AsyncClient.post")
    def test_groq_upstream_500_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Groq Error"
        mock_post.return_value = mock_resp

        with self.assertRaises(UpstreamProviderError):
            asyncio.run(self.stt_service.transcribe_audio(b"fake_audio_content"))

    @patch("backend.services.audio.stt.groq_whisper_service.transcribe_audio")
    def test_transcribe_audio_endpoint(self, mock_transcribe):
        mock_transcribe.return_value = {
            "transcription": "Is it hot outside?",
            "language": "en",
            "model": "whisper-large-v3",
            "execution_time_ms": 120.5
        }

        audio_file = io.BytesIO(b"fake_wav_bytes")
        response = self.client.post(
            "/api/audio/transcribe",
            files={"file": ("test.wav", audio_file, "audio/wav")},
            data={"language": "en"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["transcription"], "Is it hot outside?")

    def test_browser_tts_metadata(self):
        meta = asyncio.run(browser_tts_service.get_synthesis_metadata("Weather update", language="hi"))
        self.assertEqual(meta["mode"], "browser_native")
        self.assertEqual(meta["language"], "hi")
        self.assertEqual(meta["char_count"], 14)
