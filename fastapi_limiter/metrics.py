"""Prometheus-format metrics endpoint for rate limit state."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from fastapi_limiter.backends import InMemoryBackend, AsyncInMemoryBackend


def create_metrics_router(
    backend: InMemoryBackend | AsyncInMemoryBackend,
    prefix: str = "/metrics",
) -> APIRouter:
    """Return an APIRouter exposing rate limit stats in Prometheus text format.

    Mounts a ``GET /metrics`` endpoint that emits two gauge metrics:

    - ``rate_limit_requests_active`` — current request count per key (last hour)
    - ``rate_limit_oldest_request_age_seconds`` — age of the oldest request per key

    Usage::

        from fastapi_limiter.metrics import create_metrics_router

        backend = InMemoryBackend()
        app.include_router(create_metrics_router(backend))

        # Scrape with: curl http://localhost:8000/metrics

    Args:
        backend: The InMemoryBackend or AsyncInMemoryBackend instance to inspect.
        prefix: Route path for the metrics endpoint. Defaults to ``/metrics``.
    """
    router = APIRouter()
    is_async = isinstance(backend, AsyncInMemoryBackend)

    def _render(stats: list[dict]) -> str:
        lines = [
            "# HELP rate_limit_requests_active Active request count per rate limit key (last hour)",
            "# TYPE rate_limit_requests_active gauge",
        ]
        for entry in stats:
            label = entry["key"].replace('"', '\\"')
            lines.append(f'rate_limit_requests_active{{key="{label}"}} {entry["request_count"]}')

        lines += [
            "",
            "# HELP rate_limit_oldest_request_age_seconds Age of the oldest tracked request per key",
            "# TYPE rate_limit_oldest_request_age_seconds gauge",
        ]
        for entry in stats:
            label = entry["key"].replace('"', '\\"')
            lines.append(
                f'rate_limit_oldest_request_age_seconds{{key="{label}"}} {entry["oldest_request_age_seconds"]}'
            )

        return "\n".join(lines) + "\n"

    if is_async:
        @router.get(prefix, response_class=PlainTextResponse, include_in_schema=False)
        async def metrics_async():
            stats = await backend.stats()
            return _render(stats)
    else:
        @router.get(prefix, response_class=PlainTextResponse, include_in_schema=False)
        def metrics_sync():
            stats = backend.stats()
            return _render(stats)

    return router
