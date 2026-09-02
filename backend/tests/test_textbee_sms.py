import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from backend.services.notifications.textbee_sms import TextBeeSMSAdapter, textbee_sms_adapter
from backend.schemas.notifications import (
    NotificationPayload,
    NotificationChannel,
    NotificationStatus,
)


class TestTextBeeSMSAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = TextBeeSMSAdapter(
            api_key="test_tb_api_key_123",
            device_id="test_tb_device_456",
            base_url="https://api.textbee.dev/api/v1",
            dry_run=False,
        )
        self.payload = NotificationPayload(
            recipient_identifier="+919876543210",
            channel=NotificationChannel.SMS,
            title="Emergency Alert",
            message="Test Emergency SMS",
        )

    # 1. TextBee adapter success using mocked API response
    def test_textbee_sms_adapter_success_mocked(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "SMS dispatched successfully",
            "data": {"id": "tb_msg_998877"},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(self.adapter.send_notification(self.payload))

            self.assertEqual(status.status, NotificationStatus.SENT)
            self.assertEqual(status.provider_reference, "tb_msg_998877")

            # Verify request headers and body format
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs.get("headers", {})
            json_body = call_kwargs.get("json", {})

            self.assertEqual(headers.get("x-api-key"), "test_tb_api_key_123")
            self.assertEqual(json_body.get("recipients"), ["+919876543210"])
            self.assertEqual(json_body.get("deviceId"), "test_tb_device_456")
            self.assertEqual(json_body.get("message"), "Test Emergency SMS")

    # 2. TextBee adapter API failure handling
    def test_textbee_sms_adapter_api_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Invalid API key or unauthorized device."}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            status = asyncio.run(self.adapter.send_notification(self.payload))

            self.assertEqual(status.status, NotificationStatus.FAILED)
            self.assertIn("Invalid API key", status.error_message)

    # 3. TextBee timeout/network error handling
    def test_textbee_sms_adapter_network_timeout(self):
        import httpx

        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
            status = asyncio.run(self.adapter.send_notification(self.payload))

            self.assertEqual(status.status, NotificationStatus.RETRYING)
            self.assertIn("timed out", status.error_message)

    # 4. TextBee missing configuration guard
    def test_textbee_sms_missing_configuration(self):
        unconf_adapter = TextBeeSMSAdapter(api_key="", device_id="", dry_run=False)
        status = asyncio.run(unconf_adapter.send_notification(self.payload))

        self.assertEqual(status.status, NotificationStatus.FAILED)
        self.assertIn("not configured", status.error_message)

    # 5. TextBee dry-run simulation mode
    def test_textbee_sms_dry_run_simulation(self):
        sim_adapter = TextBeeSMSAdapter(
            api_key="test_tb_key",
            device_id="test_device",
            dry_run=True,
        )
        status = asyncio.run(sim_adapter.send_notification(self.payload))

        self.assertEqual(status.status, NotificationStatus.SIMULATED)
        self.assertTrue(status.is_simulated)
        self.assertTrue(status.provider_reference.startswith("sim_tb_sms_"))


if __name__ == "__main__":
    unittest.main()
