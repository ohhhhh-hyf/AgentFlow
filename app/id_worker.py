"""Distributed-style ID generation for API request/job identifiers."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

BEGIN_TIMESTAMP = 1640995200
COUNT_BITS = 32
ID_KEY_PREFIX = "agentflow:id:"

_local_lock = threading.Lock()
_local_counts: dict[str, int] = {}


def _redis_client():
    """Create a Redis client when the optional redis package is available."""
    try:
        import redis
    except ModuleNotFoundError:
        return None
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


class RedisIdWorker:
    """Generate sortable numeric IDs using epoch seconds + daily sequence.

    The layout mirrors the Java worker the user provided:
    ``(seconds_since_BEGIN_TIMESTAMP << COUNT_BITS) | daily_count``.
    Redis is used for cross-process increments when available. In local demo
    environments without Redis, an in-process counter keeps the API usable.
    """

    def __init__(self) -> None:
        self._redis = _redis_client()

    def next_id(self, key_prefix: str) -> int:
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp()) - BEGIN_TIMESTAMP
        date = now.strftime("%Y%m%d")
        count = self._next_count(key_prefix, date)
        return (timestamp << COUNT_BITS) | count

    def _next_count(self, key_prefix: str, date: str) -> int:
        # request/job share one daily sequence so their numeric suffixes do not
        # collide visually when generated in the same second.
        key = f"{ID_KEY_PREFIX}global:{date}"
        if self._redis is not None:
            count = self._redis.incr(key)
            self._redis.expire(key, 3 * 24 * 60 * 60)
            return int(count)
        with _local_lock:
            _local_counts[key] = _local_counts.get(key, 0) + 1
            return _local_counts[key]


_worker = RedisIdWorker()


def next_prefixed_id(prefix: str) -> str:
    """Return an ID such as ``request_636...`` or ``job_636...``."""
    clean = (prefix or "id").strip().strip("_") or "id"
    return f"{clean}_{_worker.next_id(clean)}"


def next_request_id() -> str:
    return next_prefixed_id("request")


def next_job_id() -> str:
    return next_prefixed_id("job")


__all__ = ["RedisIdWorker", "next_job_id", "next_prefixed_id", "next_request_id"]
