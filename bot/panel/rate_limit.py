"""Dependency-free login rate limiting primitives."""

import time


class LoginRateLimiter:
    """Process-local sliding-window limiter keyed by client identifier."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        recent = [stamp for stamp in self._failures.get(key, []) if stamp > cutoff]
        self._failures[key] = recent
        return recent

    def is_blocked(self, key: str, *, now: float | None = None) -> bool:
        stamp = now if now is not None else time.monotonic()
        return len(self._recent(key, stamp)) >= self.max_attempts

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        stamp = now if now is not None else time.monotonic()
        self._recent(key, stamp).append(stamp)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
