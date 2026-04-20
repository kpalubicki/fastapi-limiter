"""RateLimiter dependency for use with FastAPI routes."""

import time
from fastapi import Request, HTTPException
from typing import Callable, Optional
from fastapi_limiter.backends import Backend, InMemoryBackend

_default_backend = InMemoryBackend()


def _default_key(request: Request) -> str:
    """Build a rate limit key from the client IP and route path."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "testclient"
    return f"{ip}:{request.url.path}"


class RateLimiter:
    """FastAPI dependency that enforces a per-route rate limit.

    Usage::

        from fastapi import Depends
        from fastapi_limiter import RateLimiter

        @app.get("/search", dependencies=[Depends(RateLimiter(limit=10, window=60))])
        async def search():
            ...

    Args:
        limit: Maximum number of requests allowed per window.
        window: Time window in seconds.
        backend: Storage backend. Defaults to a shared InMemoryBackend.
        key_func: Callable that returns a string key from the request.
                  Defaults to IP + route path.
    """

    def __init__(
        self,
        limit: int,
        window: int,
        backend: Optional[Backend] = None,
        key_func: Optional[Callable] = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        if window <= 0:
            raise ValueError("window must be a positive integer")

        self.limit = limit
        self.window = window
        self.backend = backend or _default_backend
        self.key_func = key_func or _default_key

    async def __call__(self, request: Request) -> None:
        key = self.key_func(request)
        allowed, remaining, retry_after = self.backend.is_allowed(key, self.limit, self.window)
        reset_at = int(time.time()) + (retry_after if not allowed else self.window)

        request.state.ratelimit_remaining = remaining
        request.state.ratelimit_limit = self.limit
        request.state.ratelimit_window = self.window
        request.state.ratelimit_reset = reset_at

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.window),
                    "X-RateLimit-Reset": str(reset_at),
                },
            )


class BurstLimiter:
    """FastAPI dependency that enforces both a burst and a sustained rate limit.

    Allows short traffic spikes while still enforcing a long-term rate cap.
    Both limits must pass — if either is exceeded the request is rejected.

    Usage::

        from fastapi import Depends
        from fastapi_limiter import BurstLimiter

        limiter = BurstLimiter(
            burst_limit=10, burst_window=5,       # up to 10 req in 5 seconds
            sustained_limit=60, sustained_window=60,  # up to 60 req per minute
        )

        @app.get("/search", dependencies=[Depends(limiter)])
        async def search():
            ...

    Args:
        burst_limit: Maximum requests allowed in the short burst window.
        burst_window: Short window duration in seconds (e.g. 5).
        sustained_limit: Maximum requests allowed in the sustained window.
        sustained_window: Long window duration in seconds (e.g. 60).
        backend: Storage backend. Defaults to a shared InMemoryBackend.
        key_func: Callable that returns a string key from the request.
    """

    def __init__(
        self,
        burst_limit: int,
        burst_window: int,
        sustained_limit: int,
        sustained_window: int,
        backend: Optional[Backend] = None,
        key_func: Optional[Callable] = None,
    ) -> None:
        for name, val in [
            ("burst_limit", burst_limit), ("burst_window", burst_window),
            ("sustained_limit", sustained_limit), ("sustained_window", sustained_window),
        ]:
            if val <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if burst_window >= sustained_window:
            raise ValueError("burst_window must be shorter than sustained_window")

        self.burst_limit = burst_limit
        self.burst_window = burst_window
        self.sustained_limit = sustained_limit
        self.sustained_window = sustained_window
        self.backend = backend or _default_backend
        self.key_func = key_func or _default_key

    async def __call__(self, request: Request) -> None:
        key = self.key_func(request)

        burst_allowed, _, burst_retry = self.backend.is_allowed(
            f"{key}:burst", self.burst_limit, self.burst_window
        )
        if not burst_allowed:
            reset_at = int(time.time()) + burst_retry
            raise HTTPException(
                status_code=429,
                detail=f"Burst limit exceeded. Try again in {burst_retry}s.",
                headers={
                    "Retry-After": str(burst_retry),
                    "X-RateLimit-Limit": str(self.burst_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.burst_window),
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        sustained_allowed, _, sustained_retry = self.backend.is_allowed(
            f"{key}:sustained", self.sustained_limit, self.sustained_window
        )
        if not sustained_allowed:
            reset_at = int(time.time()) + sustained_retry
            raise HTTPException(
                status_code=429,
                detail=f"Sustained rate limit exceeded. Try again in {sustained_retry}s.",
                headers={
                    "Retry-After": str(sustained_retry),
                    "X-RateLimit-Limit": str(self.sustained_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.sustained_window),
                    "X-RateLimit-Reset": str(reset_at),
                },
            )
