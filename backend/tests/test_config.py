import unittest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.config import settings

class TestConfigEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_config_status_code(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)

    def test_no_secrets_exposed_in_config(self):
        response = self.client.get("/api/config")
        data = response.json()
        
        # Verify no secret field names are exposed in response
        sensitive_keys = ["API_KEY", "SECRET", "PASSWORD", "TOKEN", "SERVICE_ROLE_KEY"]
        for key in sensitive_keys:
            self.assertNotIn(key, data)
            self.assertNotIn(key.lower(), data)

        self.assertEqual(data["project_name"], "WeatherGPT")
        self.assertIn("configured_services", data)
        self.assertIn("allowed_origins", data)
