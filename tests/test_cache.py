"""Redis is allowed to die: a broken cache must behave like a cache miss, never like an error."""
from __future__ import annotations

import time

from src.cache import NullCache, ResilientCache
from src.providers import DeterministicProvider
from src.repository import MemoryRepository
from src.retrieval import RetrievalService

# Port 1 is never a Redis server, so every call fails at connect time.
DEAD_REDIS_URL = "redis://127.0.0.1:1/0"


def test_dead_redis_is_a_fast_cache_miss() -> None:
    cache = ResilientCache(DEAD_REDIS_URL)
    start = time.perf_counter()
    assert cache.get("any-key") is None
    cache.set("any-key", {"value": 1}, ttl_seconds=60)  # must not raise
    assert cache.health() is False
    assert time.perf_counter() - start < 2.0


def test_dead_redis_is_skipped_after_first_failure() -> None:
    cache = ResilientCache(DEAD_REDIS_URL)
    calls = 0
    original_get = cache.client.get

    def counting_get(key):
        nonlocal calls
        calls += 1
        return original_get(key)

    cache.client.get = counting_get
    for _ in range(5):
        assert cache.get("any-key") is None
    assert calls == 1  # circuit breaker: Redis is not retried on every request


def test_retrieval_still_answers_when_redis_is_dead(repository: MemoryRepository) -> None:
    service = RetrievalService(repository, DeterministicProvider(), ResilientCache(DEAD_REDIS_URL), 900)
    results = service.search("jatah cuti tahunan", top_k=2)
    assert results[0].document_id == "HR-LEAVE-001"


def test_null_cache_never_stores() -> None:
    cache = NullCache()
    cache.set("key", [1, 2, 3], ttl_seconds=60)
    assert cache.get("key") is None
    assert cache.health() is False


def test_cache_key_contains_index_version(repository: MemoryRepository) -> None:
    old = RetrievalService(repository, DeterministicProvider(), NullCache(), 0, index_version="v1")
    new = RetrievalService(repository, DeterministicProvider(), NullCache(), 0, index_version="v2")
    assert old.cache_key("Cuti", 3) != new.cache_key("Cuti", 3)
    assert old.cache_key("Cuti  Tahunan", 3) == old.cache_key("cuti tahunan", 3)
    assert "cuti" not in old.cache_key("cuti tahunan", 3)  # raw user text never becomes a Redis key
