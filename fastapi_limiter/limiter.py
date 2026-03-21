"""RateLimiter dependency for use with FastAPI routes."""

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

        request.state.ratelimit_remaining = remaining
        request.state.ratelimit_limit = self.limit
        request.state.ratelimit_window = self.window

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.window),
                },
            )
