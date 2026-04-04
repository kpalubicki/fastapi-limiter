"""Tests for jwt_key_func."""

import base64
import json

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from fastapi_limiter import RateLimiter, InMemoryBackend, jwt_key_func


def _make_token(payload: dict) -> str:
    """Build a minimal unsigned JWT with the given payload."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}."


def make_app(limit: int = 3) -> tuple[FastAPI, InMemoryBackend]:
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = RateLimiter(limit=limit, window=60, backend=backend, key_func=jwt_key_func())

    @app.get("/data", dependencies=[Depends(limiter)])
    def data():
        return {"ok": True}

    return app, backend


def test_jwt_key_uses_sub_claim():
    app, backend = make_app(limit=2)
    client = TestClient(app)
    token = _make_token({"sub": "user-alice"})
    headers = {"Authorization": f"Bearer {token}"}

    client.get("/data", headers=headers)
    client.get("/data", headers=headers)
    r = client.get("/data", headers=headers)
    assert r.status_code == 429


def test_different_users_have_separate_limits():
    app, backend = make_app(limit=2)
    client = TestClient(app)

    token_a = _make_token({"sub": "alice"})
    token_b = _make_token({"sub": "bob"})

    # exhaust alice's limit
    client.get("/data", headers={"Authorization": f"Bearer {token_a}"})
    client.get("/data", headers={"Authorization": f"Bearer {token_a}"})
    r_alice = client.get("/data", headers={"Authorization": f"Bearer {token_a}"})
    assert r_alice.status_code == 429

    # bob is unaffected
    r_bob = client.get("/data", headers={"Authorization": f"Bearer {token_b}"})
    assert r_bob.status_code == 200


def test_fallback_to_ip_when_no_token():
    app, _ = make_app(limit=2)
    client = TestClient(app)

    client.get("/data")
    client.get("/data")
    r = client.get("/data")
    assert r.status_code == 429


def test_fallback_to_ip_when_token_has_no_sub():
    app, _ = make_app(limit=2)
    client = TestClient(app)
    token = _make_token({"email": "alice@example.com"})  # no "sub"

    client.get("/data", headers={"Authorization": f"Bearer {token}"})
    client.get("/data", headers={"Authorization": f"Bearer {token}"})
    r = client.get("/data", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 429


def test_custom_claim():
    app = FastAPI()
    backend = InMemoryBackend()
    limiter = RateLimiter(limit=1, window=60, backend=backend, key_func=jwt_key_func(claim="email"))

    @app.get("/data", dependencies=[Depends(limiter)])
    def data():
        return {"ok": True}

    client = TestClient(app)
    token = _make_token({"email": "alice@example.com"})
    client.get("/data", headers={"Authorization": f"Bearer {token}"})
    r = client.get("/data", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 429
