"""Optional mountable router exposing rate limit state at /limits."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi_limiter.backends import InMemoryBackend, AsyncInMemoryBackend


def create_limits_router(
    backend: InMemoryBackend | AsyncInMemoryBackend,
    prefix: str = "/limits",
) -> APIRouter:
    """Return an APIRouter with a GET endpoint showing active rate limit keys.

    Mount it in your app to get visibility into current rate limit state::

        from fastapi_limiter.dashboard import create_limits_router

        backend = InMemoryBackend()
        app.include_router(create_limits_router(backend))

    The ``GET /limits`` endpoint returns a list of active keys with their
    current request count and the age of the oldest tracked request.

    Args:
        backend: The InMemoryBackend or AsyncInMemoryBackend instance to inspect.
        prefix: Route path for the dashboard endpoint. Defaults to ``/limits``.
    """
    router = APIRouter()
    is_async = isinstance(backend, AsyncInMemoryBackend)

    if is_async:
        @router.get(prefix)
        async def limits_async():
            """Active rate limit keys and current request counts."""
            return {"limits": await backend.stats()}
    else:
        @router.get(prefix)
        def limits_sync():
            """Active rate limit keys and current request counts."""
            return {"limits": backend.stats()}

    return router
