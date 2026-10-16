"""Tiny in-memory sliding-window rate limiter (per process; use a shared store if you run many workers)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.errors import AppError


class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise AppError("rate_limited", "Too many analyses in a short time. Please wait a minute and try again.", 429)
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory
                self._hits.clear()
