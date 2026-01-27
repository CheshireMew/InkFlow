"""
InkFlow HTTP Client

Shared HTTP client with connection pooling.
Adapted from Lumina project.
"""

import logging
import asyncio
from typing import Optional
import httpx

logger = logging.getLogger("HTTPClient")


class HTTPClientPool:
    """Manages a shared httpx.AsyncClient with connection pooling."""
    
    DEFAULT_TIMEOUT = httpx.Timeout(
        connect=5.0,
        read=60.0,  # LLM calls may take long
        write=30.0,
        pool=5.0
    )
    
    DEFAULT_LIMITS = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
        keepalive_expiry=30.0
    )
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._is_closed = False
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get the shared HTTP client. Creates one if needed."""
        if self._client is not None and not self._is_closed:
            return self._client
        
        async with self._lock:
            if self._client is not None and not self._is_closed:
                return self._client
            
            self._client = httpx.AsyncClient(
                timeout=self.DEFAULT_TIMEOUT,
                limits=self.DEFAULT_LIMITS,
                http2=True,
            )
            self._is_closed = False
            logger.info("⚡ HTTP client initialized")
            return self._client
    
    async def close(self):
        """Close the HTTP client."""
        async with self._lock:
            if self._client and not self._is_closed:
                await self._client.aclose()
                self._is_closed = True
                self._client = None
                logger.info("🔌 HTTP client closed")


# Global instance
_pool: Optional[HTTPClientPool] = None


def _get_pool() -> HTTPClientPool:
    global _pool
    if _pool is None:
        _pool = HTTPClientPool()
    return _pool


async def get_http_client() -> httpx.AsyncClient:
    """Get the shared HTTP client."""
    return await _get_pool().get_client()


async def close_http_client():
    """Close the shared HTTP client."""
    await _get_pool().close()


async def http_post_json(url: str, json_data: dict, **kwargs) -> dict:
    """POST JSON and return JSON response."""
    client = await get_http_client()
    response = await client.post(url, json=json_data, **kwargs)
    response.raise_for_status()
    return response.json()
