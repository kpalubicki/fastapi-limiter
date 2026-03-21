"""Optional ASGI middleware for global rate limiting."""

from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi_limiter.backends import Backend, InMemoryBackend


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that applies a global rate limit to all routes.

    Use this when you want one limit across the entire API rather than
    per-route limits. For per-route control use the RateLimiter dependency.

    Usage::

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            limit=100,
            window=60,
        )

    Args:
        limit: Maximum requests per window.
        window: Window duration in seconds.
        backend: Storage backend (default: InMemoryBackend).
        exclude_paths: List of path prefixes to skip (e.g. ["/health"]).
    """

    def __init__(
        self,
        app,
        limit: int = 60,
        window: int = 60,
        backend: Backend | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window
        self.backend = backend or InMemoryBackend()
        self.exclude_paths = exclude_paths or []

    async def dispatch(self, request: Request, call_next):
        for prefix in self.exclude_paths:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        forwarded = request.headers.get("X-Forwarded-For")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        key = f"{ip}:global"

        allowed, remaining, retry_after = self.backend.is_allowed(key, self.limit, self.window)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Too many requests. Try again in {retry_after}s."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
