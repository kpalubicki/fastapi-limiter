"""Tests for the InMemoryBackend sliding window implementation."""

import time
import threading
import pytest
from fastapi_limiter.backends import InMemoryBackend


def test_first_request_allowed():
    backend = InMemoryBackend()
    allowed, remaining, retry_after = backend.is_allowed("key", limit=5, window=60)
    assert allowed is True
    assert remaining == 4
    assert retry_after == 0


def test_requests_up_to_limit_allowed():
    backend = InMemoryBackend()
    for i in range(5):
        allowed, remaining, _ = backend.is_allowed("key", limit=5, window=60)
        assert allowed is True
        assert remaining == 4 - i


def test_request_over_limit_blocked():
    backend = InMemoryBackend()
    for _ in range(5):
        backend.is_allowed("key", limit=5, window=60)
    allowed, remaining, retry_after = backend.is_allowed("key", limit=5, window=60)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_different_keys_are_independent():
    backend = InMemoryBackend()
    for _ in range(5):
        backend.is_allowed("key-a", limit=5, window=60)
    allowed_a, _, _ = backend.is_allowed("key-a", limit=5, window=60)
    allowed_b, _, _ = backend.is_allowed("key-b", limit=5, window=60)
    assert allowed_a is False
    assert allowed_b is True


def test_reset_clears_state():
    backend = InMemoryBackend()
    for _ in range(5):
        backend.is_allowed("key", limit=5, window=60)
    backend.reset("key")
    allowed, remaining, _ = backend.is_allowed("key", limit=5, window=60)
    assert allowed is True
    assert remaining == 4


def test_window_expiry():
    backend = InMemoryBackend()
    for _ in range(3):
        backend.is_allowed("key", limit=3, window=1)

    blocked, _, _ = backend.is_allowed("key", limit=3, window=1)
    assert blocked is False

    time.sleep(1.1)
    allowed, remaining, _ = backend.is_allowed("key", limit=3, window=1)
    assert allowed is True
    assert remaining == 2


def test_thread_safety():
    backend = InMemoryBackend()
    results = []
    lock = threading.Lock()

    def make_request():
        allowed, _, _ = backend.is_allowed("shared", limit=50, window=60)
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=make_request) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed_count = sum(1 for r in results if r)
    blocked_count = sum(1 for r in results if not r)
    assert allowed_count == 50
    assert blocked_count == 50
