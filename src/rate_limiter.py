from __future__ import annotations

import functools
import time
import threading
from collections import defaultdict
from typing import Callable

# ---------------------------------------------------------------------------
# Yahoo Finance rate limits (unofficial, community-observed):
#   - 1 request per second sustained
#   - 2000 requests per hour
#   - Cache identical calls for 60 s to avoid wasting quota
# ---------------------------------------------------------------------------

_MIN_INTERVAL = 1.2       # seconds between calls
_HOURLY_LIMIT = 1900       # safety margin below 2000
_WINDOW = 3600.0


class RateLimiter:
    def __init__(self, min_interval: float = _MIN_INTERVAL, hourly_limit: int = _HOURLY_LIMIT) -> None:
        self._min_interval = min_interval
        self._hourly_limit = hourly_limit
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._timestamps: list[float] = []

    def _purge_old(self) -> None:
        cutoff = time.monotonic() - _WINDOW
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()

            # Enforce per-request spacing
            since_last = now - self._last_call
            if since_last < self._min_interval:
                time.sleep(self._min_interval - since_last)
                now = time.monotonic()

            # Enforce hourly cap
            self._purge_old()
            if len(self._timestamps) >= self._hourly_limit:
                oldest = self._timestamps[0]
                wait_until = oldest + _WINDOW
                sleep_for = wait_until - now
                if sleep_for > 0:
                    time.sleep(sleep_for)
                    now = time.monotonic()
                    self._purge_old()

            self._last_call = now
            self._timestamps.append(now)


# Global instance shared across all market-data calls
_rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Simple in-memory TTL cache for identical calls (symbol x interval)
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60.0  # 1 minute


def cached_call(ttl: float = _CACHE_TTL):
    """Decorator that caches return value keyed by (*args, **kwargs) for `ttl` seconds."""
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__name__}:{args}:{kwargs}"
            now = time.monotonic()
            with _cache_lock:
                if key in _cache:
                    ts, val = _cache[key]
                    if now - ts < ttl:
                        return val
            _rate_limiter.wait()
            result = fn(*args, **kwargs)
            with _cache_lock:
                _cache[key] = (now, result)
            return result

        return wrapper

    return decorator
