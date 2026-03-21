"""Tests for the RateLimiter dependency and RateLimitMiddleware."""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import RateLimiter, InMemoryBackend, RateLimitMiddleware


def make_app_with_limiter(limit: int = 3, window: int = 60) -> FastAPI:
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = RateLimiter(limit=limit, window=window, backend=backend)

    @app.get("/limited", dependencies=[Depends(limiter)])
    def limited():
        return {"ok": True}

    @app.get("/open")
    def open_route():
        return {"ok": True}

    return app


def make_app_with_middleware(limit: int = 3, window: int = 60) -> FastAPI:
    app = FastAPI()
    backend = InMemoryBackend()
    app.add_middleware(
        RateLimitMiddleware,
        limit=limit,
        window=window,
        backend=backend,
        exclude_paths=["/health"],
    )

    @app.get("/data")
    def data():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# --- RateLimiter dependency tests ---

def test_limiter_allows_requests_under_limit():
    client = TestClient(make_app_with_limiter(limit=3))
    for _ in range(3):
        r = client.get("/limited")
        assert r.status_code == 200


def test_limiter_blocks_over_limit():
    client = TestClient(make_app_with_limiter(limit=3))
    for _ in range(3):
        client.get("/limited")
    r = client.get("/limited")
    assert r.status_code == 429
    assert "Too many requests" in r.json()["detail"]


def test_limiter_includes_retry_after_header():
    client = TestClient(make_app_with_limiter(limit=1))
    client.get("/limited")
    r = client.get("/limited")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_limiter_does_not_affect_other_routes():
    client = TestClient(make_app_with_limiter(limit=1))
    client.get("/limited")
    client.get("/limited")  # blocked
    r = client.get("/open")
    assert r.status_code == 200


def test_limiter_rejects_invalid_limit():
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        RateLimiter(limit=0, window=60)


def test_limiter_rejects_invalid_window():
    with pytest.raises(ValueError, match="window must be a positive integer"):
        RateLimiter(limit=10, window=-1)


# --- RateLimitMiddleware tests ---

def test_middleware_allows_requests_under_limit():
    client = TestClient(make_app_with_middleware(limit=3))
    for _ in range(3):
        r = client.get("/data")
        assert r.status_code == 200


def test_middleware_blocks_over_limit():
    client = TestClient(make_app_with_middleware(limit=2))
    client.get("/data")
    client.get("/data")
    r = client.get("/data")
    assert r.status_code == 429


def test_middleware_excludes_health_path():
    client = TestClient(make_app_with_middleware(limit=1))
    client.get("/data")
    client.get("/data")  # blocked
    r = client.get("/health")
    assert r.status_code == 200


def test_middleware_adds_ratelimit_headers():
    client = TestClient(make_app_with_middleware(limit=5))
    r = client.get("/data")
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
