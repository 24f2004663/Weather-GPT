import unittest
import asyncio
import time
from backend.core.cache import InMemoryTTLCache

class TestInMemoryCache(unittest.TestCase):
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
        # Sleep past TTL
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
