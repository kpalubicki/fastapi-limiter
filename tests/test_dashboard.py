"""Tests for the /limits dashboard router."""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import RateLimiter, InMemoryBackend, create_limits_router
from fastapi_limiter.backends import AsyncInMemoryBackend


def make_app(backend: InMemoryBackend) -> FastAPI:
    app = FastAPI()
    limiter = RateLimiter(limit=10, window=60, backend=backend)

    @app.get("/data", dependencies=[Depends(limiter)])
    def data():
        return {"ok": True}

    app.include_router(create_limits_router(backend))
    return app


def test_limits_empty_on_start():
    backend = InMemoryBackend()
    client = TestClient(make_app(backend))
    r = client.get("/limits")
    assert r.status_code == 200
    assert r.json() == {"limits": []}


def test_limits_shows_key_after_request():
    backend = InMemoryBackend()
    client = TestClient(make_app(backend))
    client.get("/data")
    r = client.get("/limits")
    data = r.json()
    assert len(data["limits"]) == 1
    entry = data["limits"][0]
    assert entry["request_count"] == 1
    assert "key" in entry
    assert "oldest_request_age_seconds" in entry


def test_limits_counts_multiple_requests():
    backend = InMemoryBackend()
    client = TestClient(make_app(backend))
    for _ in range(5):
        client.get("/data")
    r = client.get("/limits")
    assert r.json()["limits"][0]["request_count"] == 5


def test_limits_custom_prefix():
    backend = InMemoryBackend()
    app = FastAPI()
    app.include_router(create_limits_router(backend, prefix="/admin/rate-limits"))
    client = TestClient(app)
    r = client.get("/admin/rate-limits")
    assert r.status_code == 200
    assert "limits" in r.json()


def test_limits_async_backend():
    backend = AsyncInMemoryBackend()
    app = FastAPI()
    app.include_router(create_limits_router(backend))
    client = TestClient(app)
    r = client.get("/limits")
    assert r.status_code == 200
    assert r.json() == {"limits": []}
