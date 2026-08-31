import unittest
from fastapi.testclient import TestClient
from backend.main import app

class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check_status_code(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_health_check_payload_structure(self):
        response = self.client.get("/api/health")
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("version", data)
        self.assertIn("environment", data)
        self.assertIn("timestamp", data)
        self.assertIn("services", data)
        self.assertIsInstance(data["services"], dict)
        self.assertIn("open_meteo", data["services"])
        self.assertIn("gemini", data["services"])
        self.assertIn("supabase", data["services"])
