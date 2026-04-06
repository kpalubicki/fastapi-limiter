"""Tests for AsyncRedisBackend using a mocked async Redis client."""

from __future__ import annotations

import time
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi_limiter.backends import AsyncRedisBackend


class FakeAsyncRedis:
    """Minimal in-memory async Redis fake for testing sorted-set operations."""

    def __init__(self):
        self._data: dict[str, list[tuple[bytes, float]]] = defaultdict(list)

    async def zrem(self, key, *members):
        self._data[key] = [(m, s) for m, s in self._data[key] if m not in members]

    async def delete(self, key):
        self._data.pop(key, None)

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeAsyncRedis):
        self._redis = redis
        self._cmds: list = []

    def zremrangebyscore(self, key, min_score, max_score):
        self._cmds.append(("zremrangebyscore", key, float(min_score) if min_score != "-inf" else float("-inf"), float(max_score)))
        return self

    def zrange(self, key, start, stop, withscores=False):
        self._cmds.append(("zrange", key, withscores))
        return self

    def zadd(self, key, mapping):
        self._cmds.append(("zadd", key, mapping))
        return self

    def expire(self, key, ttl):
        self._cmds.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for cmd in self._cmds:
            if cmd[0] == "zremrangebyscore":
                _, key, min_s, max_s = cmd
                self._redis._data[key] = [(m, s) for m, s in self._redis._data[key] if s > max_s]
                results.append(None)
            elif cmd[0] == "zrange":
                _, key, withscores = cmd
                entries = list(self._redis._data[key])
                results.append(entries if withscores else [m for m, _ in entries])
            elif cmd[0] == "zadd":
                _, key, mapping = cmd
                for member, score in mapping.items():
                    self._redis._data[key].append((member, score))
                    self._redis._data[key].sort(key=lambda x: x[1])
                results.append(1)
            elif cmd[0] == "expire":
                results.append(1)
        self._cmds.clear()
        return results


def _make_backend(fake_redis: FakeAsyncRedis) -> AsyncRedisBackend:
    with patch("redis.asyncio.from_url", return_value=fake_redis):
        return AsyncRedisBackend()


@pytest.mark.asyncio
async def test_async_redis_allows_under_limit():
    fake = FakeAsyncRedis()
    backend = _make_backend(fake)
    for _ in range(3):
        allowed, remaining, retry_after = await backend.is_allowed("key1", limit=5, window=60)
        assert allowed
        assert retry_after == 0
    assert remaining == 2  # 5 limit - 3 used - 1 (current) = 1 remaining slot after this call


@pytest.mark.asyncio
async def test_async_redis_blocks_over_limit():
    fake = FakeAsyncRedis()
    backend = _make_backend(fake)
    for _ in range(5):
        await backend.is_allowed("key2", limit=5, window=60)
    allowed, remaining, retry_after = await backend.is_allowed("key2", limit=5, window=60)
    assert not allowed
    assert remaining == 0
    assert retry_after >= 1


@pytest.mark.asyncio
async def test_async_redis_reset_clears_key():
    fake = FakeAsyncRedis()
    backend = _make_backend(fake)
    for _ in range(5):
        await backend.is_allowed("key3", limit=5, window=60)
    await backend.reset("key3")
    allowed, _, _ = await backend.is_allowed("key3", limit=5, window=60)
    assert allowed


@pytest.mark.asyncio
async def test_async_redis_separate_keys():
    fake = FakeAsyncRedis()
    backend = _make_backend(fake)
    for _ in range(5):
        await backend.is_allowed("user-a", limit=5, window=60)
    blocked, _, _ = await backend.is_allowed("user-a", limit=5, window=60)
    allowed, _, _ = await backend.is_allowed("user-b", limit=5, window=60)
    assert not blocked
    assert allowed


def test_async_redis_import_error():
    with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
        with pytest.raises(ImportError, match="AsyncRedisBackend requires"):
            AsyncRedisBackend()
