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
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass

class InMemoryTTLCache(BaseCache):
    """
    Thread-safe and async-compatible in-memory cache with TTL expiration.
    """
    def __init__(self, default_ttl_seconds: int = 600):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        async with self._lock:
            self._cache[key] = (value, expires_at)

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
        """Removes expired entries and returns count of purged items."""
        now = time.time()
        purged = 0
        async with self._lock:
            keys_to_remove = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in keys_to_remove:
                del self._cache[k]
                purged += 1
        return purged

    def size(self) -> int:
        return len(self._cache)

# Global singleton cache instance for application use
cache = InMemoryTTLCache(default_ttl_seconds=600)
