import unittest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from backend.services.ai.alert_message import generate_alert_message, SYSTEM_PROMPT
from backend.schemas.alerts import DisasterAlert, AlertSeverity, AlertStatus, AlertUrgency, AlertCertainty, GeographicScope, AlertSource


def create_sample_alert():
    return DisasterAlert(
        alert_id="ALERT-GEMINI-101",
        source=AlertSource.SACHET_NDMA,
        title="Cyclone Storm Warning",
        event_type="Cyclone",
        severity=AlertSeverity.EXTREME,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        headline="Severe Cyclone Warning for Coastal Tamil Nadu",
        description="Heavy to very heavy rainfall expected across Chennai.",
        instruction="Stay indoors in secure shelters. Fishermen advised not to venture into sea.",
        affected_area="Coastal Tamil Nadu (Chennai)",
        scope=GeographicScope.DISTRICT,
        affected_states=["Tamil Nadu"],
        affected_districts=["Chennai"],
        issued_time=datetime.now(timezone.utc),
        is_active=True,
    )


class TestGeminiAlertMessageGenerator(unittest.TestCase):

    def test_system_prompt_prohibits_fabrication(self):
        self.assertIn("NEVER invent or exaggerate facts", SYSTEM_PROMPT)
        self.assertIn("Do NOT invent casualties", SYSTEM_PROMPT)
        self.assertIn("Do NOT change or exaggerate the severity", SYSTEM_PROMPT)

    @patch("backend.services.ai.alert_message.settings")
    def test_fallback_when_api_key_missing(self, mock_settings):
        mock_settings.GEMINI_API_KEY = None
        alert = create_sample_alert()

        msg = asyncio.run(generate_alert_message(alert, language="en"))
        # Should return fallback formatted string
        self.assertIn("SACHET / NDMA", msg)
        self.assertIn("Cyclone", msg)
        self.assertIn("EXTREME", msg)

    @patch("backend.services.ai.alert_message.httpx.AsyncClient.post")
    @patch("backend.services.ai.alert_message.settings")
    def test_successful_gemini_message_generation(self, mock_settings, mock_post):
        mock_settings.GEMINI_API_KEY = "test_key"
        mock_settings.GEMINI_MODEL = "gemini-3.5-flash-lite"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "🚨 OFFICIAL EMERGENCY ALERT: Severe Cyclone Warning along Coastal Tamil Nadu. Stay indoors."}
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        alert = create_sample_alert()
        msg = asyncio.run(generate_alert_message(alert, language="en"))

        self.assertIn("OFFICIAL EMERGENCY ALERT", msg)
        self.assertIn("Severe Cyclone Warning", msg)
        mock_post.assert_called_once()

    @patch("backend.services.ai.alert_message.httpx.AsyncClient.post")
    @patch("backend.services.ai.alert_message.settings")
    def test_fallback_on_gemini_error(self, mock_settings, mock_post):
        mock_settings.GEMINI_API_KEY = "test_key"
        mock_settings.GEMINI_MODEL = "gemini-3.5-flash-lite"
        mock_post.side_effect = Exception("API rate limit")

        alert = create_sample_alert()
        msg = asyncio.run(generate_alert_message(alert, language="en"))

        # Fallback template returned on exception
        self.assertIn("Cyclone", msg)
        self.assertIn("EXTREME", msg)



if __name__ == "__main__":
    unittest.main()
