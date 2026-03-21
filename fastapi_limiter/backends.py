"""Storage backends for rate limit state."""

from __future__ import annotations

import time
import threading
from abc import ABC, abstractmethod
from collections import deque


class Backend(ABC):
    """Abstract base class for rate limit backends."""

    @abstractmethod
    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Check whether a request should be allowed.

        Args:
            key: Unique identifier for this client+route combination.
            limit: Maximum number of requests allowed in the window.
            window: Time window in seconds.

        Returns:
            Tuple of (allowed, remaining, retry_after).
            - allowed: True if the request should proceed.
            - remaining: How many requests are left in the window.
            - retry_after: Seconds until the window resets (0 if allowed).
        """

    @abstractmethod
    def reset(self, key: str) -> None:
        """Clear all rate limit state for a key."""


class InMemoryBackend(Backend):
    """Thread-safe in-memory backend using a sliding window algorithm.

    Suitable for single-process applications. Not shared across workers —
    use RedisBackend if you run multiple uvicorn workers or gunicorn processes.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        now = time.time()
        cutoff = now - window

        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()

            timestamps = self._windows[key]

            # drop timestamps outside the current window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            count = len(timestamps)

            if count >= limit:
                retry_after = int(timestamps[0] - cutoff) + 1
                return False, 0, retry_after

            timestamps.append(now)
            return True, limit - count - 1, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)
