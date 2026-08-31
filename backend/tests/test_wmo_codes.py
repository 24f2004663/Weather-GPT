import unittest
from backend.services.weather.wmo_codes import decode_wmo_code, WMO_CODE_MAP

class TestWMOCodes(unittest.TestCase):
    def test_known_wmo_codes(self):
        name, desc, icon = decode_wmo_code(0)
        self.assertEqual(name, "Clear Sky")
        self.assertEqual(icon, "clear-day")

        name, desc, icon = decode_wmo_code(65)
        self.assertEqual(name, "Heavy Rain")
        self.assertEqual(icon, "rain-heavy")

        name, desc, icon = decode_wmo_code(95)
        self.assertEqual(name, "Thunderstorm")
        self.assertEqual(icon, "thunderstorm")

    def test_unknown_wmo_code_fallback(self):
        name, desc, icon = decode_wmo_code(9999)
        self.assertEqual(name, "Unknown")
        self.assertEqual(icon, "cloudy")
