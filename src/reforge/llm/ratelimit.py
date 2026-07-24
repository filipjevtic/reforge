"""A tiny thread-safe rate limiter.

Judge calls fan out with task concurrency, so a shared limiter keeps reforge from
tripping provider rate limits. This is a simple minimum-interval gate, which is
enough for the call volumes reforge produces.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, calls_per_minute: float) -> None:
        self._min_interval = 60.0 / calls_per_minute if calls_per_minute > 0 else 0.0
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval
