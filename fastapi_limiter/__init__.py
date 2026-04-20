"""fastapi-limiter: rate limiting middleware for FastAPI."""

from fastapi_limiter.limiter import RateLimiter, BurstLimiter
from fastapi_limiter.backends import InMemoryBackend, AsyncInMemoryBackend, AsyncRedisBackend
from fastapi_limiter.middleware import RateLimitMiddleware
from fastapi_limiter.dashboard import create_limits_router
from fastapi_limiter.keys import jwt_key_func
from fastapi_limiter.access import IPWhitelist, IPBlocklist, whitelist_key_func
from fastapi_limiter.metrics import create_metrics_router

__version__ = "0.1.0"
__all__ = [
    "RateLimiter", "BurstLimiter",
    "InMemoryBackend", "AsyncInMemoryBackend", "AsyncRedisBackend",
    "RateLimitMiddleware",
    "create_limits_router",
    "jwt_key_func",
    "IPWhitelist", "IPBlocklist", "whitelist_key_func",
    "create_metrics_router",
]
