"""Storage backends for rate limit state."""

from __future__ import annotations

import asyncio
import time
import threading
from abc import ABC, abstractmethod
from collections import deque


class Backend(ABC):
    """Abstract base class for rate limit backends."""

    @abstractmethod
    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Check whether a request should be allowed.

        Args:
            key: Unique identifier for this client+route combination.
            limit: Maximum number of requests allowed in the window.
            window: Time window in seconds.

        Returns:
            Tuple of (allowed, remaining, retry_after).
            - allowed: True if the request should proceed.
            - remaining: How many requests are left in the window.
            - retry_after: Seconds until the window resets (0 if allowed).
        """

    @abstractmethod
    def reset(self, key: str) -> None:
        """Clear all rate limit state for a key."""


class InMemoryBackend(Backend):
    """Thread-safe in-memory backend using a sliding window algorithm.

    Suitable for single-process applications. Not shared across workers —
    use RedisBackend if you run multiple uvicorn workers or gunicorn processes.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        now = time.time()
        cutoff = now - window

        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()

            timestamps = self._windows[key]

            # drop timestamps outside the current window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            count = len(timestamps)

            if count >= limit:
                retry_after = int(timestamps[0] - cutoff) + 1
                return False, 0, retry_after

            timestamps.append(now)
            return True, limit - count - 1, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def stats(self) -> list[dict]:
        """Return current request counts for all tracked keys."""
        now = time.time()
        with self._lock:
            result = []
            for key, timestamps in self._windows.items():
                active = [t for t in timestamps if t > now - 3600]
                if active:
                    result.append({
                        "key": key,
                        "request_count": len(active),
                        "oldest_request_age_seconds": round(now - active[0], 1),
                    })
            return result


class AsyncInMemoryBackend:
    """Async-native in-memory backend using asyncio.Lock.

    Drop-in replacement for InMemoryBackend when running inside an async
    context (e.g. a single uvicorn worker). Use this with ``async def``
    key functions and async middleware. Not safe across multiple processes —
    use RedisBackend for that.

    Example::

        from fastapi_limiter.backends import AsyncInMemoryBackend
        backend = AsyncInMemoryBackend()
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        import time as _time

        now = _time.time()
        cutoff = now - window

        async with self._get_lock():
            if key not in self._windows:
                self._windows[key] = deque()

            timestamps = self._windows[key]
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            count = len(timestamps)
            if count >= limit:
                retry_after = int(timestamps[0] - cutoff) + 1
                return False, 0, retry_after

            timestamps.append(now)
            return True, limit - count - 1, 0

    async def reset(self, key: str) -> None:
        async with self._get_lock():
            self._windows.pop(key, None)

    async def stats(self) -> list[dict]:
        """Return current request counts for all tracked keys."""
        import time as _time
        now = _time.time()
        async with self._get_lock():
            result = []
            for key, timestamps in self._windows.items():
                active = [t for t in timestamps if t > now - 3600]
                if active:
                    result.append({
                        "key": key,
                        "request_count": len(active),
                        "oldest_request_age_seconds": round(now - active[0], 1),
                    })
            return result


class RedisBackend(Backend):
    """Redis-backed sliding window backend.

    Suitable for multi-process deployments (multiple uvicorn workers, gunicorn).
    Requires the ``redis`` package: ``pip install redis``.

    Args:
        url: Redis connection URL. Defaults to ``redis://localhost:6379``.
        prefix: Key prefix applied to all rate limit keys. Defaults to ``rl:``.

    Example::

        import redis
        from fastapi_limiter.backends import RedisBackend

        backend = RedisBackend(url="redis://localhost:6379")
    """

    def __init__(self, url: str = "redis://localhost:6379", prefix: str = "rl:") -> None:
        try:
            import redis as redis_lib
        except ImportError as e:
            raise ImportError(
                "RedisBackend requires the 'redis' package. Install it with: pip install redis"
            ) from e

        self._redis = redis_lib.from_url(url, decode_responses=False)
        self._prefix = prefix

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        import time

        full_key = self._full_key(key)
        now = time.time()
        cutoff = now - window

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(full_key, "-inf", cutoff)
        pipe.zrange(full_key, 0, -1, withscores=True)
        pipe.zadd(full_key, {str(now).encode(): now})
        pipe.expire(full_key, window + 1)
        results = pipe.execute()

        existing: list[tuple[bytes, float]] = results[1]
        count = len(existing)

        if count >= limit:
            oldest_score = existing[0][1] if existing else now
            retry_after = int(oldest_score - cutoff) + 1
            # undo the zadd we just did
            self._redis.zrem(full_key, str(now).encode())
            return False, 0, retry_after

        return True, limit - count - 1, 0

    def reset(self, key: str) -> None:
        self._redis.delete(self._full_key(key))


class AsyncRedisBackend:
    """Async Redis-backed sliding window backend using ``redis.asyncio``.

    Drop-in async replacement for RedisBackend. Uses the async interface
    bundled in redis-py >= 4.2 — no extra package required beyond ``redis``.

    Suitable for async FastAPI apps with multiple workers. Shares state across
    processes via Redis.

    Args:
        url: Redis connection URL. Defaults to ``redis://localhost:6379``.
        prefix: Key prefix applied to all rate limit keys. Defaults to ``rl:``.

    Example::

        from fastapi_limiter.backends import AsyncRedisBackend

        backend = AsyncRedisBackend(url="redis://localhost:6379")
    """

    def __init__(self, url: str = "redis://localhost:6379", prefix: str = "rl:") -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ImportError(
                "AsyncRedisBackend requires the 'redis' package (>= 4.2). "
                "Install it with: pip install redis"
            ) from e

        self._redis = aioredis.from_url(url, decode_responses=False)
        self._prefix = prefix

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        import time

        full_key = self._full_key(key)
        now = time.time()
        cutoff = now - window

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(full_key, "-inf", cutoff)
        pipe.zrange(full_key, 0, -1, withscores=True)
        pipe.zadd(full_key, {str(now).encode(): now})
        pipe.expire(full_key, window + 1)
        results = await pipe.execute()

        existing: list[tuple[bytes, float]] = results[1]
        count = len(existing)

        if count >= limit:
            oldest_score = existing[0][1] if existing else now
            retry_after = int(oldest_score - cutoff) + 1
            await self._redis.zrem(full_key, str(now).encode())
            return False, 0, retry_after

        return True, limit - count - 1, 0

    async def reset(self, key: str) -> None:
        await self._redis.delete(self._full_key(key))
