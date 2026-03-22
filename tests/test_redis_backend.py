"""Tests for RedisBackend — run against a real Redis or skip if unavailable."""

import pytest
from unittest.mock import MagicMock, patch, call
from fastapi_limiter.backends import RedisBackend


def make_backend(url="redis://localhost:6379"):
    """Create a RedisBackend with a mocked redis connection."""
    with patch("redis.from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis
        backend = RedisBackend(url=url)
        backend._redis = mock_redis
    return backend, mock_redis


def _make_pipeline(existing_scores=None, zrem_return=None):
    """Helper that returns a mock pipeline mimicking redis pipeline().execute()."""
    pipe = MagicMock()
    existing: list[tuple[bytes, float]] = existing_scores or []
    pipe.execute.return_value = [None, existing, None, None]
    return pipe


def test_import_error_without_redis():
    with patch.dict("sys.modules", {"redis": None}):
        with pytest.raises(ImportError, match="pip install redis"):
            RedisBackend()


def test_first_request_allowed():
    backend, mock_redis = make_backend()
    pipe = _make_pipeline(existing_scores=[])
    mock_redis.pipeline.return_value = pipe

    allowed, remaining, retry_after = backend.is_allowed("key", limit=5, window=60)

    assert allowed is True
    assert remaining == 4
    assert retry_after == 0


def test_request_over_limit_blocked():
    import time
    backend, mock_redis = make_backend()
    now = time.time()
    # 5 existing entries = at the limit
    existing = [(f"ts{i}".encode(), now - i) for i in range(5)]
    pipe = _make_pipeline(existing_scores=existing)
    mock_redis.pipeline.return_value = pipe

    allowed, remaining, retry_after = backend.is_allowed("key", limit=5, window=60)

    assert allowed is False
    assert remaining == 0
    assert retry_after > 0
    # should undo the zadd
    mock_redis.zrem.assert_called_once()


def test_reset_calls_delete():
    backend, mock_redis = make_backend()
    backend.reset("mykey")
    mock_redis.delete.assert_called_once_with("rl:mykey")


def test_custom_prefix():
    with patch("redis.from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis
        backend = RedisBackend(url="redis://localhost", prefix="app:")
        backend._redis = mock_redis

    backend.reset("user:123")
    mock_redis.delete.assert_called_once_with("app:user:123")


def test_full_key_uses_prefix():
    backend, _ = make_backend()
    assert backend._full_key("route:POST:/items") == "rl:route:POST:/items"


def test_pipeline_called_correctly():
    backend, mock_redis = make_backend()
    pipe = _make_pipeline(existing_scores=[])
    mock_redis.pipeline.return_value = pipe

    backend.is_allowed("k", limit=10, window=30)

    pipe.zremrangebyscore.assert_called_once()
    pipe.zrange.assert_called_once()
    pipe.zadd.assert_called_once()
    pipe.expire.assert_called_once()
    pipe.execute.assert_called_once()
