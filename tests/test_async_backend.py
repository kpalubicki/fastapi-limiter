"""Tests for AsyncInMemoryBackend."""

from __future__ import annotations

import pytest
from fastapi_limiter.backends import AsyncInMemoryBackend


@pytest.fixture
def backend() -> AsyncInMemoryBackend:
    return AsyncInMemoryBackend()


async def test_allows_first_request(backend: AsyncInMemoryBackend) -> None:
    allowed, remaining, retry_after = await backend.is_allowed("key", limit=5, window=60)
    assert allowed is True
    assert remaining == 4
    assert retry_after == 0


async def test_blocks_when_limit_reached(backend: AsyncInMemoryBackend) -> None:
    for _ in range(3):
        await backend.is_allowed("key", limit=3, window=60)

    allowed, remaining, retry_after = await backend.is_allowed("key", limit=3, window=60)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


async def test_independent_keys(backend: AsyncInMemoryBackend) -> None:
    for _ in range(3):
        await backend.is_allowed("a", limit=3, window=60)

    allowed_a, _, _ = await backend.is_allowed("a", limit=3, window=60)
    allowed_b, _, _ = await backend.is_allowed("b", limit=3, window=60)

    assert allowed_a is False
    assert allowed_b is True


async def test_reset_clears_state(backend: AsyncInMemoryBackend) -> None:
    for _ in range(3):
        await backend.is_allowed("key", limit=3, window=60)

    await backend.reset("key")

    allowed, remaining, _ = await backend.is_allowed("key", limit=3, window=60)
    assert allowed is True
    assert remaining == 2


async def test_remaining_decrements(backend: AsyncInMemoryBackend) -> None:
    _, r1, _ = await backend.is_allowed("key", limit=5, window=60)
    _, r2, _ = await backend.is_allowed("key", limit=5, window=60)
    _, r3, _ = await backend.is_allowed("key", limit=5, window=60)

    assert r1 == 4
    assert r2 == 3
    assert r3 == 2
