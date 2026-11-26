"""Login rate limit (Phase 6 security). Blocks password guessing without changing login rules.

- Counts FAILED attempts per client IP in a sliding window.
- After MAX_FAILURES inside WINDOW, further attempts get 429 until the window passes.
- A successful login clears the counter for that IP.
- In-memory: fine for the single API container. Resets on restart (documented limitation).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60


class LoginRateLimiter:
    def __init__(self, max_failures: int = MAX_FAILURES, window_seconds: int = WINDOW_SECONDS, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def is_blocked(self, ip: str) -> bool:
        with self._lock:
            q = self._failures.get(ip)
            if not q:
                return False
            self._prune(q, self._clock())
            return len(q) >= self.max_failures

    def record_failure(self, ip: str) -> None:
        with self._lock:
            now = self._clock()
            q = self._failures[ip]
            self._prune(q, now)
            q.append(now)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
