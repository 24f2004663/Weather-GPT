import json
from typing import Optional
import httpx

from backend.core.config import settings
from backend.core.logging import logger
from backend.schemas.alerts import DisasterAlert
from backend.services.notifications.formatter import format_whatsapp_alert

SYSTEM_PROMPT = """You are WeatherGPT Emergency Alert Writer.
Your sole job is to rewrite authoritative disaster/emergency alerts into clear, urgent, user-facing notifications.

STRICT CONSTRAINTS:
1. NEVER invent or exaggerate facts:
   - Do NOT invent casualties, damage, evacuation orders, or government directives not present in the source.
   - Do NOT change or exaggerate the severity or urgency level.
   - Do NOT modify the affected geographic location or timing.
2. Remain 100% faithful to the provided authoritative source bulletin.
3. Explicitly preserve:
   - Source authority (e.g. SACHET/NDMA, GDACS)
   - Severity level
   - Affected state / district / area
   - Official safety instructions (if present)
4. Keep the message concise (150-250 words max), readable on mobile screens, formatted with emojis and bullet points for quick scanning in an emergency.
5. Generate ONLY the alert message text. Do not include markdown codeblocks or conversational filler ("Here is the alert:").
"""


async def generate_alert_message(alert: DisasterAlert, language: str = "en") -> str:
    """
    Generates a concise, clear user-facing emergency alert message using Gemini.
    Receives ONLY verified structured alert data. Never invents facts.
    Falls back to deterministic template formatting if Gemini is unavailable.
    """
    # Fallback default
    fallback_msg = format_whatsapp_alert(alert, language=language)

    if not settings.GEMINI_API_KEY:
        logger.debug("[Gemini Alert] GEMINI_API_KEY not configured, using fallback template")
        return fallback_msg

    alert_summary = {
        "source": alert.source.value if hasattr(alert.source, "value") else str(alert.source),
        "alert_id": alert.alert_id,
        "title": alert.title,
        "event_type": alert.event_type,
        "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        "urgency": alert.urgency.value if hasattr(alert.urgency, "value") else str(alert.urgency),
        "certainty": alert.certainty.value if hasattr(alert.certainty, "value") else str(alert.certainty),
        "headline": alert.headline,
        "description": alert.description,
        "instruction": alert.instruction,
        "affected_area": alert.affected_area,
        "affected_states": alert.affected_states,
        "affected_districts": alert.affected_districts,
        "issued_time": alert.issued_time.isoformat() if alert.issued_time else None,
        "expires_time": alert.expires_time.isoformat() if alert.expires_time else None,
        "target_language": language,
    }

    user_prompt = f"Please reformat this official emergency bulletin into a clear user-facing emergency message in language code '{language}':\n\n{json.dumps(alert_summary, indent=2)}"

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_prompt},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,  # Low temperature to prevent hallucination/creativity
                "maxOutputTokens": 400,
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        msg = parts[0]["text"].strip()
                        if msg:
                            logger.info(f"[Gemini Alert] Message generated successfully for alert: {alert.alert_id}")
                            return msg
            logger.warning(f"[Gemini Alert] API returned HTTP {res.status_code}, using fallback template")
    except Exception as e:
        logger.error(f"[Gemini Alert] Exception generating message: {str(e)}, using fallback template")

    return fallback_msg
