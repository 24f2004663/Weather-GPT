import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, Tuple

class BaseCache(ABC):
    """
    Abstract cache contract to allow pluggable caching backends (In-Memory, Redis, Supabase).
    """
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Return value if within fresh TTL, None otherwise."""
        pass

    @abstractmethod
    async def get_with_stale(self, key: str) -> Optional[Tuple[Any, bool]]:
        """
        Return (value, is_stale) if within stale TTL, None if fully expired.
        is_stale=True means fresh TTL has passed but stale TTL has not.
        Use for fallback on upstream provider failures.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None, stale_ttl_seconds: Optional[int] = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass


class InMemoryTTLCache(BaseCache):
    """
    Thread-safe and async-compatible in-memory cache with dual TTL:
    - Fresh TTL: data served normally within this window
    - Stale TTL: data available as fallback on upstream failures beyond fresh TTL

    NOTE: This cache is process-local. It is lost on any process restart,
    Render cold start, or scale-out to multiple workers. It does NOT persist
    across deployments. A Redis-backed cache would be needed for cross-process
    sharing, but is not required for the current single-worker prototype.
    """
    def __init__(self, default_ttl_seconds: int = 600, default_stale_ttl_seconds: int = 7200):
        # Stores: (value, fresh_expires_at, stale_expires_at)
        self._cache: Dict[str, Tuple[Any, float, float]] = {}
        self._default_ttl = default_ttl_seconds
        self._default_stale_ttl = default_stale_ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Return value only if within fresh TTL. Returns None if stale or expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, fresh_exp, stale_exp = entry
            now = time.time()
            if now > stale_exp:
                # Fully expired — remove entry
                del self._cache[key]
                return None
            if now > fresh_exp:
                # Within stale window but not fresh — not returned by normal get()
                return None
            return value

    async def get_with_stale(self, key: str) -> Optional[Tuple[Any, bool]]:
        """
        Return (value, is_stale) if entry exists within stale TTL.
        Returns None only if fully expired or not present.
        is_stale=True means the fresh TTL has expired but the stale window has not.
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, fresh_exp, stale_exp = entry
            now = time.time()
            if now > stale_exp:
                del self._cache[key]
                return None
            is_stale = now > fresh_exp
            return (value, is_stale)

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None, stale_ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        stale_ttl = stale_ttl_seconds if stale_ttl_seconds is not None else self._default_stale_ttl
        now = time.time()
        fresh_exp = now + ttl
        stale_exp = now + max(ttl, stale_ttl)  # stale window always >= fresh window
        async with self._lock:
            self._cache[key] = (value, fresh_exp, stale_exp)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """Removes fully expired entries (past stale TTL) and returns count of purged items."""
        now = time.time()
        purged = 0
        async with self._lock:
            keys_to_remove = [k for k, (_, _, stale_exp) in self._cache.items() if now > stale_exp]
            for k in keys_to_remove:
                del self._cache[k]
                purged += 1
        return purged

    def size(self) -> int:
        return len(self._cache)


# Global singleton cache instance for application use
# default_ttl_seconds is overridden per-call via the ttl_seconds argument;
# default_stale_ttl_seconds is overridden similarly.
cache = InMemoryTTLCache(default_ttl_seconds=600, default_stale_ttl_seconds=7200)
