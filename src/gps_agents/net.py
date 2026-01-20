from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class RateLimitConfig:
    max_calls: int = 1
    window_seconds: float = 1.0
    min_interval: float = 0.0  # enforce spacing between calls


class AsyncRateLimiter:
    """Simple sliding-window rate limiter with min-interval spacing."""

    def __init__(self, cfg: RateLimitConfig) -> None:
        self.cfg = cfg
        self._lock = asyncio.Lock()
        self._calls: list[float] = []  # timestamps
        self._last_call: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Enforce min interval
            sleep_needed = max(0.0, self.cfg.min_interval - (now - self._last_call))
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)
                now = time.monotonic()
            # Evict old calls
            cutoff = now - self.cfg.window_seconds
            self._calls = [t for t in self._calls if t >= cutoff]
            # If at capacity, wait until earliest drops out
            if len(self._calls) >= self.cfg.max_calls:
                wait_for = self._calls[0] + self.cfg.window_seconds - now
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                    now = time.monotonic()
                    cutoff = now - self.cfg.window_seconds
                    self._calls = [t for t in self._calls if t >= cutoff]
            # Record call
            self._calls.append(time.monotonic())
            self._last_call = time.monotonic()


class CircuitBreaker:
    """Basic circuit breaker with failure window and cooldown."""

    def __init__(self, max_failures: int = 5, window_seconds: float = 60.0, cooldown_seconds: float = 300.0) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._failures: list[float] = []
        self._opened_at: float | None = None

    def allow_call(self) -> bool:
        now = time.monotonic()
        if self._opened_at is not None:
            if now - self._opened_at < self.cooldown_seconds:
                return False
            # half-open: allow one call
            self._opened_at = None
            self._failures.clear()
        # clean history
        cutoff = now - self.window_seconds
        self._failures = [t for t in self._failures if t >= cutoff]
        return True

    def record_success(self) -> None:
        self._failures.clear()
        self._opened_at = None

    def record_failure(self) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._failures = [t for t in self._failures if t >= cutoff]
        self._failures.append(now)
        if len(self._failures) >= self.max_failures:
            self._opened_at = now


class NetGuards:
    """Registry for per-source rate limiters and circuit breakers."""

    def __init__(self) -> None:
        self._limiters: Dict[str, AsyncRateLimiter] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_limiter(self, key: str, default: RateLimitConfig) -> AsyncRateLimiter:
        key = key.lower()
        if key not in self._limiters:
            self._limiters[key] = AsyncRateLimiter(default)
        return self._limiters[key]

    def get_breaker(self, key: str, max_failures: int = 5, window_seconds: float = 60.0, cooldown_seconds: float = 300.0) -> CircuitBreaker:
        key = key.lower()
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker(max_failures, window_seconds, cooldown_seconds)
        return self._breakers[key]


# Global guards instance
GUARDS = NetGuards()


def report_status() -> dict:
    """Return a snapshot of breaker status and rate config for debugging."""
    out = {}
    for key, br in GUARDS._breakers.items():  # noqa: SLF001
        out.setdefault(key, {})["circuit_open"] = br._opened_at is not None  # noqa: SLF001
    for key, lim in GUARDS._limiters.items():  # noqa: SLF001
        out.setdefault(key, {})["rate"] = {
            "max_calls": lim.cfg.max_calls,
            "window_seconds": lim.cfg.window_seconds,
            "min_interval": lim.cfg.min_interval,
        }
    return out
