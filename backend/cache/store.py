"""
cache/store.py — In-memory TTL cache for Etherscan responses.
Prevents redundant API calls during repeated demo runs and protects
against the 5 req/sec free-tier rate limit.
"""
import time
import asyncio
from typing import Any, Optional
from config import settings


class TTLCache:
    """
    Simple in-memory key-value cache with per-entry TTL.
    Thread-safe for asyncio use (single-threaded event loop).
    """

    def __init__(self, default_ttl: int = 3600):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._store:
                value, expires_at = self._store[key]
                if time.monotonic() < expires_at:
                    return value
                else:
                    del self._store[key]
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        async with self._lock:
            self._store[key] = (value, time.monotonic() + effective_ttl)

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# ─── Global singleton ─────────────────────────────────────────────────────────
_cache_instance: Optional[TTLCache] = None


def get_cache() -> TTLCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = TTLCache(default_ttl=settings.cache_ttl_seconds)
    return _cache_instance


cache = get_cache()
