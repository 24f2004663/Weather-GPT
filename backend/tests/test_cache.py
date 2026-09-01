import unittest
import asyncio
import time
from backend.core.cache import InMemoryTTLCache


class TestInMemoryCache(unittest.TestCase):
    # -----------------------------------------------------------------------
    # Existing tests (preserved, compatible with new dual-TTL storage)
    # -----------------------------------------------------------------------

    def test_cache_set_and_get(self):
        cache = InMemoryTTLCache(default_ttl_seconds=10)
        asyncio.run(cache.set("key1", {"temp": 28.5}))
        res = asyncio.run(cache.get("key1"))
        self.assertEqual(res, {"temp": 28.5})

    def test_cache_ttl_expiration(self):
        cache = InMemoryTTLCache(default_ttl_seconds=1)
        asyncio.run(cache.set("key_exp", "val", ttl_seconds=1))
        # Immediate read should succeed
        self.assertEqual(asyncio.run(cache.get("key_exp")), "val")
        # Sleep past fresh TTL
        time.sleep(1.1)
        self.assertIsNone(asyncio.run(cache.get("key_exp")))

    def test_cache_delete_and_clear(self):
        cache = InMemoryTTLCache(default_ttl_seconds=10)
        asyncio.run(cache.set("k1", "v1"))
        asyncio.run(cache.set("k2", "v2"))
        self.assertEqual(cache.size(), 2)

        deleted = asyncio.run(cache.delete("k1"))
        self.assertTrue(deleted)
        self.assertIsNone(asyncio.run(cache.get("k1")))
        self.assertEqual(cache.size(), 1)

        asyncio.run(cache.clear())
        self.assertEqual(cache.size(), 0)

    # -----------------------------------------------------------------------
    # New stale-cache tests
    # -----------------------------------------------------------------------

    def test_get_with_stale_fresh(self):
        """get_with_stale on a fresh entry returns (value, is_stale=False)."""
        cache = InMemoryTTLCache(default_ttl_seconds=60, default_stale_ttl_seconds=3600)
        asyncio.run(cache.set("fresh_key", {"data": 1}))
        result = asyncio.run(cache.get_with_stale("fresh_key"))
        self.assertIsNotNone(result)
        value, is_stale = result
        self.assertEqual(value, {"data": 1})
        self.assertFalse(is_stale)

    def test_get_with_stale_is_stale(self):
        """After fresh TTL expires but within stale TTL, get_with_stale returns (value, True)."""
        cache = InMemoryTTLCache(default_ttl_seconds=1, default_stale_ttl_seconds=3600)
        asyncio.run(cache.set("stale_key", {"data": 99}, ttl_seconds=1, stale_ttl_seconds=3600))
        # Fresh immediately
        result = asyncio.run(cache.get_with_stale("stale_key"))
        self.assertFalse(result[1])  # not stale yet
        # Pass fresh TTL
        time.sleep(1.1)
        result = asyncio.run(cache.get_with_stale("stale_key"))
        self.assertIsNotNone(result)
        value, is_stale = result
        self.assertEqual(value, {"data": 99})
        self.assertTrue(is_stale)
        # But regular get() should return None (stale)
        self.assertIsNone(asyncio.run(cache.get("stale_key")))

    def test_get_with_stale_fully_expired(self):
        """After both TTLs expire, get_with_stale returns None."""
        cache = InMemoryTTLCache(default_ttl_seconds=1, default_stale_ttl_seconds=1)
        asyncio.run(cache.set("exp_key", "val", ttl_seconds=1, stale_ttl_seconds=1))
        time.sleep(1.2)
        self.assertIsNone(asyncio.run(cache.get_with_stale("exp_key")))

    def test_get_with_stale_missing_key(self):
        """get_with_stale on non-existent key returns None."""
        cache = InMemoryTTLCache()
        result = asyncio.run(cache.get_with_stale("no_such_key"))
        self.assertIsNone(result)

    def test_stale_window_at_least_as_long_as_fresh(self):
        """Stale TTL is always >= fresh TTL (enforced in set())."""
        cache = InMemoryTTLCache(default_ttl_seconds=60, default_stale_ttl_seconds=30)
        # Even though stale_ttl_seconds < ttl_seconds, the set() enforces stale >= fresh
        asyncio.run(cache.set("k", "v", ttl_seconds=60, stale_ttl_seconds=10))
        time.sleep(0.1)
        result = asyncio.run(cache.get_with_stale("k"))
        self.assertIsNotNone(result)
        # Entry should still be accessible within the fresh window
        self.assertEqual(asyncio.run(cache.get("k")), "v")

    def test_cleanup_expired_removes_fully_expired(self):
        """cleanup_expired() purges entries past the stale TTL."""
        cache = InMemoryTTLCache(default_ttl_seconds=1, default_stale_ttl_seconds=1)
        asyncio.run(cache.set("k1", "v1", ttl_seconds=1, stale_ttl_seconds=1))
        asyncio.run(cache.set("k2", "v2", ttl_seconds=60, stale_ttl_seconds=60))
        time.sleep(1.2)
        purged = asyncio.run(cache.cleanup_expired())
        self.assertEqual(purged, 1)
        self.assertEqual(cache.size(), 1)
