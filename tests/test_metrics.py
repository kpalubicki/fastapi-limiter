"""Tests for Prometheus metrics endpoint."""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import RateLimiter, InMemoryBackend
from fastapi_limiter.metrics import create_metrics_router


def make_app() -> tuple[FastAPI, InMemoryBackend]:
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = RateLimiter(limit=10, window=60, backend=backend)

    @app.get("/api", dependencies=[Depends(limiter)])
    def api():
        return {"ok": True}

    app.include_router(create_metrics_router(backend))
    return app, backend


def test_metrics_empty_when_no_requests():
    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "rate_limit_requests_active" in resp.text


def test_metrics_shows_active_keys_after_requests():
    app, _ = make_app()
    client = TestClient(app)

    client.get("/api")
    client.get("/api")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "rate_limit_requests_active" in resp.text
    assert "rate_limit_oldest_request_age_seconds" in resp.text
    assert 'key="' in resp.text


def test_metrics_content_type_is_text():
    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/metrics")
    assert "text" in resp.headers["content-type"]


def test_metrics_custom_prefix():
    app = FastAPI()
    backend = InMemoryBackend()
    app.include_router(create_metrics_router(backend, prefix="/custom-metrics"))
    client = TestClient(app)

    resp = client.get("/custom-metrics")
    assert resp.status_code == 200


def test_metrics_format_is_prometheus():
    app, _ = make_app()
    client = TestClient(app)
    client.get("/api")

    resp = client.get("/metrics")
    lines = resp.text.strip().splitlines()
    help_lines = [l for l in lines if l.startswith("# HELP")]
    type_lines = [l for l in lines if l.startswith("# TYPE")]
    assert len(help_lines) >= 2
    assert len(type_lines) >= 2
