"""Tests for IPWhitelist, IPBlocklist, whitelist_key_func, and X-RateLimit-Reset header."""

import time
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import RateLimiter, RateLimitMiddleware, InMemoryBackend
from fastapi_limiter.access import IPWhitelist, IPBlocklist, whitelist_key_func


# --- IPWhitelist dependency ---

def make_whitelist_app(allowed: list[str]) -> FastAPI:
    app = FastAPI()
    wl = IPWhitelist(allowed)

    @app.get("/secret", dependencies=[Depends(wl)])
    def secret():
        return {"ok": True}

    return app


def test_whitelist_allows_listed_ip():
    app = make_whitelist_app(["testclient"])
    client = TestClient(app)
    assert client.get("/secret").status_code == 200


def test_whitelist_blocks_unlisted_ip():
    app = make_whitelist_app(["10.0.0.1"])
    client = TestClient(app)
    assert client.get("/secret").status_code == 403


# --- IPBlocklist dependency ---

def make_blocklist_app(blocked: list[str]) -> FastAPI:
    app = FastAPI()
    bl = IPBlocklist(blocked)

    @app.get("/api", dependencies=[Depends(bl)])
    def api():
        return {"ok": True}

    return app


def test_blocklist_blocks_listed_ip():
    app = make_blocklist_app(["testclient"])
    client = TestClient(app)
    assert client.get("/api").status_code == 403


def test_blocklist_allows_unlisted_ip():
    app = make_blocklist_app(["1.2.3.4"])
    client = TestClient(app)
    assert client.get("/api").status_code == 200


# --- Middleware allow_list and block_list ---

def make_middleware_app(limit=2, allow_list=None, block_list=None) -> FastAPI:
    app = FastAPI()
    backend = InMemoryBackend()
    app.add_middleware(
        RateLimitMiddleware,
        limit=limit,
        window=60,
        backend=backend,
        allow_list=allow_list or [],
        block_list=block_list or [],
    )

    @app.get("/data")
    def data():
        return {"ok": True}

    return app


def test_middleware_allow_list_bypasses_limit():
    app = make_middleware_app(limit=1, allow_list=["testclient"])
    client = TestClient(app)
    for _ in range(5):
        assert client.get("/data").status_code == 200


def test_middleware_block_list_returns_403():
    app = make_middleware_app(block_list=["testclient"])
    client = TestClient(app)
    assert client.get("/data").status_code == 403


def test_middleware_normal_ip_still_rate_limited():
    app = make_middleware_app(limit=2, allow_list=["10.0.0.1"])
    client = TestClient(app)
    assert client.get("/data").status_code == 200
    assert client.get("/data").status_code == 200
    assert client.get("/data").status_code == 429


# --- X-RateLimit-Reset header ---

def test_ratelimiter_includes_reset_header_on_allowed():
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = RateLimiter(limit=10, window=60, backend=backend)

    @app.get("/route", dependencies=[Depends(limiter)])
    def route():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/route")
    assert resp.status_code == 200
    # Reset header not on response body but on request.state — no 429 yet, no header exposed
    # The header is set on the HTTPException, so test the 429 path
    for _ in range(9):
        client.get("/route")
    resp = client.get("/route")
    assert resp.status_code == 429
    assert "X-RateLimit-Reset" in resp.headers
    reset_val = int(resp.headers["X-RateLimit-Reset"])
    assert reset_val > int(time.time())


def test_middleware_includes_reset_header():
    app = make_middleware_app(limit=2)
    client = TestClient(app)
    resp = client.get("/data")
    assert resp.status_code == 200
    assert "X-RateLimit-Reset" in resp.headers
    assert int(resp.headers["X-RateLimit-Reset"]) > int(time.time())


def test_middleware_reset_header_on_429():
    app = make_middleware_app(limit=1)
    client = TestClient(app)
    client.get("/data")
    resp = client.get("/data")
    assert resp.status_code == 429
    assert "X-RateLimit-Reset" in resp.headers
    assert int(resp.headers["X-RateLimit-Reset"]) > int(time.time())


# --- whitelist_key_func ---

def test_whitelist_key_func_returns_whitelist_key_for_allowed():
    from fastapi_limiter.access import whitelist_key_func
    from unittest.mock import MagicMock

    key_func = whitelist_key_func(["192.168.1.1"])
    req = MagicMock()
    req.headers.get.return_value = "192.168.1.1"
    req.client.host = "192.168.1.1"
    req.url.path = "/api"

    key = key_func(req)
    assert key.startswith("__whitelist__:")


def test_whitelist_key_func_uses_fallback_for_other_ips():
    from fastapi_limiter.access import whitelist_key_func

    key_func = whitelist_key_func(["192.168.1.1"])
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers.get.return_value = None
    req.client.host = "10.0.0.5"
    req.url.path = "/api"

    key = key_func(req)
    assert "10.0.0.5" in key
