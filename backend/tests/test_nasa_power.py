import unittest
import asyncio
from unittest.mock import patch, MagicMock
import httpx

from backend.services.weather.nasa_power import NasaPowerProvider
from backend.core.errors import UpstreamProviderError, UpstreamTimeoutError, InvalidCoordinatesError
from backend.core.cache import cache

class TestNasaPowerProvider(unittest.TestCase):
    def setUp(self):
        self.provider = NasaPowerProvider(timeout=2.0)
        asyncio.run(cache.clear())

    @patch("httpx.AsyncClient.get")
    def test_climatology_normalization_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "properties": {
                "parameter": {
                    "T2M": {
                        "JAN": 25.1, "FEB": 26.5, "MAR": 28.9, "APR": 31.4,
                        "MAY": 33.2, "JUN": 32.5, "JUL": 30.8, "AUG": 30.1,
                        "SEP": 29.5, "OCT": 28.2, "NOV": 26.1, "DEC": 25.0,
                        "ANN": 28.9
                    },
                    "PRECTOTCORR": {
                        "JAN": 0.8, "FEB": 0.5, "MAR": 0.4, "APR": 0.9,
                        "MAY": 1.8, "JUN": 2.5, "JUL": 3.8, "AUG": 4.5,
                        "SEP": 5.2, "OCT": 9.8, "NOV": 12.1, "DEC": 5.4,
                        "ANN": 3.9
                    },
                    "ALLSKY_SFC_SW_DWN": {
                        "JAN": 5.2, "FEB": 6.1, "MAR": 6.8, "APR": 6.9,
                        "MAY": 6.5, "JUN": 5.8, "JUL": 5.3, "AUG": 5.4,
                        "SEP": 5.6, "OCT": 4.9, "NOV": 4.4, "DEC": 4.7,
                        "ANN": 5.6
                    },
                    "RH2M": {
                        "JAN": 72.0, "FEB": 68.0, "MAR": 65.0, "APR": 68.0,
                        "MAY": 65.0, "JUN": 60.0, "JUL": 63.0, "AUG": 65.0,
                        "SEP": 70.0, "OCT": 78.0, "NOV": 82.0, "DEC": 77.0,
                        "ANN": 69.4
                    },
                    "WS10M": {
                        "JAN": 3.2, "FEB": 3.1, "MAR": 3.4, "APR": 3.8,
                        "MAY": 4.2, "JUN": 4.5, "JUL": 4.1, "AUG": 3.9,
                        "SEP": 3.5, "OCT": 3.1, "NOV": 3.4, "DEC": 3.5,
                        "ANN": 3.6
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        res = asyncio.run(self.provider.get_climatology(lat=13.08, lon=80.28))
        self.assertEqual(res.provider, "NASA POWER")
        self.assertIn("T2M", res.annual_averages)
        self.assertEqual(res.annual_averages["T2M"], 28.9)
        self.assertEqual(len(res.monthly_data), 12)
        self.assertEqual(res.monthly_data[0].month, "JAN")
        self.assertEqual(res.monthly_data[0].temperature_2m_c, 25.1)

    def test_invalid_coordinates(self):
        with self.assertRaises(InvalidCoordinatesError):
            asyncio.run(self.provider.get_climatology(lat=-95.0, lon=80.0))
