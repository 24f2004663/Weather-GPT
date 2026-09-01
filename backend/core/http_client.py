import asyncio
from typing import Optional
import httpx

from backend.core.config import settings
from backend.core.logging import logger

class HTTPClientManager:
    """
    Centralized HTTP client manager providing connection pooling, keep-alive reuse,
    and graceful lifecycle management across all outbound external provider services.
    """
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def get_client(self) -> httpx.AsyncClient:
        """
        Returns the shared pooled httpx.AsyncClient instance, initializing on-demand if necessary.
        """
        if self._client is not None and not self._client.is_closed:
            return self._client

        async with self._lock:
            if self._client is None or self._client.is_closed:
                limits = httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0
                )
                self._client = httpx.AsyncClient(
                    limits=limits,
                    timeout=settings.HTTP_TIMEOUT_SECONDS,
                    follow_redirects=True
                )
                logger.debug("Initialized pooled HTTP AsyncClient for external provider requests")
            return self._client

    async def close(self) -> None:
        """
        Gracefully closes active pooled connections during application shutdown.
        """
        async with self._lock:
            if self._client is not None and not self._client.is_closed:
                await self._client.aclose()
                self._client = None
                logger.debug("Closed pooled HTTP AsyncClient")

http_client_manager = HTTPClientManager()
