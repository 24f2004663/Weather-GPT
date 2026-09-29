"""
Tests for Numerical Weather Prediction model selection (PS 26068 Key Feature 3).

Open-Meteo blends several NWP systems under "best_match". Without a models parameter
a forecast could not be attributed to, or pinned to, a named model such as GFS or ICON.
"""
import unittest

from backend.services.weather.open_meteo import (
    NWP_MODELS,
    DEFAULT_NWP_MODEL,
    normalize_model,
    _make_weather_cache_key,
    open_meteo_provider,
)


class TestModelRegistry(unittest.TestCase):
    def test_gfs_is_available(self):
        """PS 26068 names GFS explicitly."""
        self.assertIn("gfs_seamless", NWP_MODELS)

    def test_major_global_models_are_available(self):
        for model_id in ("icon_seamless", "ecmwf_ifs025", "gem_seamless",
                         "jma_seamless", "ukmo_seamless"):
            self.assertIn(model_id, NWP_MODELS)

    def test_every_model_is_attributable_to_an_issuing_centre(self):
        for model_id, meta in NWP_MODELS.items():
            with self.subTest(model=model_id):
                self.assertTrue(meta.get("label"))
                self.assertTrue(meta.get("centre"))


class TestNormalizeModel(unittest.TestCase):
    def test_supported_ids_pass_through(self):
        self.assertEqual(normalize_model("gfs_seamless"), "gfs_seamless")
        self.assertEqual(normalize_model("ecmwf_ifs025"), "ecmwf_ifs025")

    def test_case_and_padding_are_normalized(self):
        self.assertEqual(normalize_model("  GFS_SEAMLESS "), "gfs_seamless")

    def test_unknown_or_missing_values_fall_back_to_the_blend(self):
        for value in (None, "", "   ", "wrf", "bogus_model", "'; DROP TABLE"):
            with self.subTest(value=value):
                self.assertEqual(normalize_model(value), DEFAULT_NWP_MODEL)

    def test_fallback_never_produces_an_unsupported_id(self):
        self.assertIn(normalize_model("nonsense"), NWP_MODELS)


class TestCacheKeyIsolation(unittest.TestCase):
    def test_models_do_not_share_a_cache_entry(self):
        """
        Models disagree by whole degrees for the same point, so a shared key would
        serve one model's forecast under another model's name.
        """
        gfs = _make_weather_cache_key(13.08, 80.27, 3, True, "gfs_seamless")
        icon = _make_weather_cache_key(13.08, 80.27, 3, True, "icon_seamless")
        blend = _make_weather_cache_key(13.08, 80.27, 3, True, "best_match")
        self.assertNotEqual(gfs, icon)
        self.assertNotEqual(gfs, blend)
        self.assertEqual(len({gfs, icon, blend}), 3)

    def test_same_model_and_point_share_a_key(self):
        self.assertEqual(
            _make_weather_cache_key(13.08, 80.27, 3, True, "gfs_seamless"),
            _make_weather_cache_key(13.0812, 80.2744, 3, True, "gfs_seamless"),
        )

    def test_model_id_appears_in_the_key(self):
        self.assertIn("gfs_seamless",
                      _make_weather_cache_key(13.08, 80.27, 3, True, "gfs_seamless"))


class TestUpstreamParameter(unittest.IsolatedAsyncioTestCase):
    """The selected model must actually reach Open-Meteo, not just the cache key."""

    async def _params_for(self, model):
        captured = {}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"timezone": "Asia/Kolkata", "utc_offset_seconds": 19800,
                        "current": {"time": "2026-09-29T11:30", "temperature_2m": 30.0,
                                    "weather_code": 0}}

        class FakeClient:
            async def get(self, url, params=None, timeout=None):
                captured["params"] = params
                return FakeResponse()

        from backend.services.weather import open_meteo as om
        from unittest.mock import AsyncMock, patch
        from backend.core.cache import cache

        await cache.clear()
        with patch.object(om.http_client_manager, "get_client",
                          AsyncMock(return_value=FakeClient())):
            resp = await open_meteo_provider.get_forecast(
                lat=13.08, lon=80.27, days=1, include_hourly=False, model=model
            )
        return captured.get("params", {}), resp

    async def test_named_model_is_sent_upstream(self):
        params, resp = await self._params_for("gfs_seamless")
        self.assertEqual(params.get("models"), "gfs_seamless")
        self.assertEqual(resp.weather_model, "gfs_seamless")

    async def test_blend_omits_the_parameter(self):
        """best_match is Open-Meteo's own default; sending it is redundant."""
        params, resp = await self._params_for("best_match")
        self.assertNotIn("models", params)
        self.assertEqual(resp.weather_model, "best_match")

    async def test_unsupported_model_is_not_forwarded_upstream(self):
        params, resp = await self._params_for("wrf_custom")
        self.assertNotIn("models", params)
        self.assertEqual(resp.weather_model, DEFAULT_NWP_MODEL)


if __name__ == "__main__":
    unittest.main()
