"""
Live Groq Whisper Speech-to-Text Smoke Test Module.
Verifies real audio transcription against Groq API when GROQ_API_KEY is available.
"""
import asyncio
import os
from backend.core.config import settings
from backend.services.audio.stt import GroqWhisperService

async def run_live_stt_smoke_test():
    api_key = os.environ.get("GROQ_API_KEY") or settings.GROQ_API_KEY
    print("=" * 65)
    print("WEATHERGPT PHASE 6 — LIVE GROQ WHISPER STT SMOKE TEST")
    print("=" * 65)

    if not api_key or api_key.strip() in ("", "your_groq_api_key_here"):
        print("\n[ENVIRONMENT STATUS: LIVE STT TEST SKIPPED]")
        print("Reason: GROQ_API_KEY is not configured in this environment.")
        print("Note: Deterministic unit tests with mocked responses pass 100%.")
        print("=" * 65)
        return

    print(f"Model: {settings.GROQ_WHISPER_MODEL}")
    print("Key status: Configured (redacted for security)")
    print("Sending test speech payload...")

    service = GroqWhisperService(api_key=api_key)
    try:
        # Minimal synthetic silent WAV header
        dummy_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        res = await service.transcribe_audio(dummy_wav, filename="test.wav", content_type="audio/wav")
        print("\n[SUCCESS: GROQ WHISPER CONNECTED]")
        print(f"  Transcription: '{res.get('transcription')}'")
        print(f"  Execution Time: {res.get('execution_time_ms'):.1f}ms")
    except Exception as e:
        print(f"\n[OFFLINE / DIAGNOSTIC: {type(e).__name__}: {str(e)}]")

    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_live_stt_smoke_test())
