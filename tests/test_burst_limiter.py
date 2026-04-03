"""Tests for BurstLimiter dependency."""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import BurstLimiter, InMemoryBackend


def make_app(burst_limit=3, burst_window=5, sustained_limit=10, sustained_window=60):
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = BurstLimiter(
        burst_limit=burst_limit,
        burst_window=burst_window,
        sustained_limit=sustained_limit,
        sustained_window=sustained_window,
        backend=backend,
    )

    @app.get("/data", dependencies=[Depends(limiter)])
    def data():
        return {"ok": True}

    return app


def test_burst_limiter_allows_under_both_limits():
    client = TestClient(make_app(burst_limit=3, sustained_limit=10))
    for _ in range(3):
        r = client.get("/data")
        assert r.status_code == 200


def test_burst_limiter_blocks_on_burst_exceeded():
    client = TestClient(make_app(burst_limit=2, sustained_limit=20))
    client.get("/data")
    client.get("/data")
    r = client.get("/data")
    assert r.status_code == 429
    assert "Burst limit" in r.json()["detail"]
    assert "Retry-After" in r.headers


def test_burst_limiter_blocks_on_sustained_exceeded():
    client = TestClient(make_app(burst_limit=100, sustained_limit=2, sustained_window=60))
    client.get("/data")
    client.get("/data")
    r = client.get("/data")
    assert r.status_code == 429
    assert "Sustained" in r.json()["detail"]


def test_burst_limiter_invalid_burst_window():
    with pytest.raises(ValueError, match="burst_window must be shorter"):
        BurstLimiter(burst_limit=5, burst_window=60, sustained_limit=10, sustained_window=60)


def test_burst_limiter_invalid_zero_limit():
    with pytest.raises(ValueError, match="burst_limit must be a positive integer"):
        BurstLimiter(burst_limit=0, burst_window=5, sustained_limit=10, sustained_window=60)


def test_burst_limiter_retry_after_header():
    client = TestClient(make_app(burst_limit=1, sustained_limit=100))
    client.get("/data")
    r = client.get("/data")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
