from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import redis

logger = logging.getLogger(__name__)


class ResilientCache:
    """Redis cache that is allowed to die: every failure behaves like a cache miss."""

    SOCKET_TIMEOUT_SECONDS = 0.2
    # Circuit breaker: after a connection failure, skip Redis for this long instead of
    # paying the timeout again on every request while Redis is down.
    COOLDOWN_SECONDS = 30.0

    def __init__(self, redis_url: str) -> None:
        # Short timeouts: a dead Redis must cost milliseconds, not the whole request budget.
        self.client: redis.Redis | None = redis.Redis.from_url(
            redis_url,
            socket_timeout=self.SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=self.SOCKET_TIMEOUT_SECONDS,
        )
        self._skip_until = 0.0

    def _available(self) -> bool:
        return self.client is not None and time.monotonic() >= self._skip_until

    def _trip(self, operation: str, exc: Exception) -> None:
        self._skip_until = time.monotonic() + self.COOLDOWN_SECONDS
        # Log the error type only: messages can carry connection details.
        logger.warning(
            "cache %s failed (%s); skipping Redis for %ss",
            operation, type(exc).__name__, self.COOLDOWN_SECONDS,
        )

    def health(self) -> bool:
        # Always really asks Redis, even during cooldown, so /readyz shows the truth.
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except (redis.RedisError, OSError):
            return False

    def get(self, key: str) -> Any | None:
        if not self._available():
            return None
        try:
            raw = self.client.get(key)
        except (redis.RedisError, OSError) as exc:
            self._trip("get", exc)
            return None
        try:
            return None if raw is None else json.loads(raw)
        except ValueError:
            logger.warning("cached value is not valid JSON; treating as miss")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """Store a value. Returns False when it was not stored, so callers that must not
        continue without it (ticket drafts, K25) can fail closed."""
        if not self._available() or ttl_seconds <= 0:
            return False
        try:
            payload = json.dumps(value)  # JSON only: never pickle, so cached data cannot run code
        except (TypeError, ValueError):
            logger.warning("value is not JSON-serializable; not cached")
            return False
        try:
            self.client.set(key, payload, ex=ttl_seconds)
        except (redis.RedisError, OSError) as exc:
            self._trip("set", exc)
            return False
        return True

    def pop(self, key: str) -> Any | None:
        """Read and delete in one atomic step (GETDEL): of two concurrent callers, one gets the
        value and the other gets None. A failure behaves like "nothing there"."""
        if not self._available():
            return None
        try:
            raw = self.client.getdel(key)
        except (redis.RedisError, OSError) as exc:
            self._trip("pop", exc)
            return None
        try:
            return None if raw is None else json.loads(raw)
        except ValueError:
            return None


class NullCache(ResilientCache):
    """No cache at all. Used by tests and when Redis is deliberately off."""

    def __init__(self) -> None:
        self.client = None
        self._skip_until = 0.0


class MemoryCache(ResilientCache):
    """In-process stand-in for Redis with the same TTL and atomic pop. Tests only."""

    def __init__(self) -> None:
        self.client = None
        self._skip_until = 0.0
        self._values: dict[str, tuple[float, str]] = {}  # key -> (expires_at, JSON text)
        self._lock = threading.Lock()

    def health(self) -> bool:
        return True

    def _live(self, key: str) -> str | None:
        stored = self._values.get(key)
        if stored is None:
            return None
        if stored[0] <= time.monotonic():
            del self._values[key]
            return None
        return stored[1]

    def get(self, key: str) -> Any | None:
        with self._lock:
            raw = self._live(key)
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            return False
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError):
            return False
        with self._lock:
            self._values[key] = (time.monotonic() + ttl_seconds, payload)
        return True

    def pop(self, key: str) -> Any | None:
        with self._lock:
            raw = self._live(key)
            self._values.pop(key, None)
        return None if raw is None else json.loads(raw)

    def expire_all(self) -> None:
        """Tests: behave as if every TTL has run out."""
        with self._lock:
            self._values.clear()
