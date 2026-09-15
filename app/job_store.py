"""Redis-backed async task state and event store."""
from __future__ import annotations

import json
import time
from typing import Any

from .config import job_ttl_seconds, redis_url
from .id_worker import next_job_id


class JobStoreError(RuntimeError):
    """Raised when Redis job storage is unavailable."""


def _redis_client():
    try:
        import redis
    except ModuleNotFoundError as exc:
        raise JobStoreError("未安装 redis Python 客户端，请执行 pip install -r requirements.txt") from exc
    url = redis_url()
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001
        raise JobStoreError(f"Redis 不可用（{url}）：{exc}") from exc
    return client


class RedisJobStore:
    """Small Redis facade for async task lifecycle data."""

    def __init__(self) -> None:
        self.redis = _redis_client()

    @staticmethod
    def new_job_id() -> str:
        return next_job_id()

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"agentflow:job:{job_id}"

    @staticmethod
    def _events_key(job_id: str) -> str:
        return f"agentflow:job:{job_id}:events"

    def create_job(
        self,
        *,
        job_id: str,
        request_id: str,
        user_id: str,
        domain: str,
        task: str,
    ) -> dict[str, Any]:
        now = time.time()
        payload = {
            "job_id": job_id,
            "request_id": request_id,
            "user_id": user_id,
            "domain": domain,
            "task": task,
            "status": "queued",
            "phase": "",
            "message": "queued",
            "error": "",
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "finished_at": "",
            "cost_time": 0.0,
            "token_usage": 0,
            "cache_hit": 0,
            "file_name": "",
            "result": "",
        }
        key = self._job_key(job_id)
        ttl = job_ttl_seconds()
        self.redis.hset(key, mapping={k: self._encode(v) for k, v in payload.items()})
        self.redis.expire(key, ttl)
        self.redis.expire(self._events_key(job_id), ttl)
        self.append_event(job_id, {"type": "queued", "job_id": job_id, "request_id": request_id})
        return payload

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        data = self.redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        return {k: self._decode(v) for k, v in data.items()}

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields.setdefault("updated_at", time.time())
        key = self._job_key(job_id)
        self.redis.hset(key, mapping={k: self._encode(v) for k, v in fields.items()})
        self.redis.expire(key, job_ttl_seconds())

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        payload = dict(event or {})
        payload.setdefault("ts", time.time())
        key = self._events_key(job_id)
        self.redis.rpush(key, json.dumps(payload, ensure_ascii=False))
        self.redis.expire(key, job_ttl_seconds())

    def events_since(self, job_id: str, cursor: int) -> list[dict[str, Any]]:
        rows = self.redis.lrange(self._events_key(job_id), cursor, -1)
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                item = json.loads(row)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                out.append(item)
        return out

    @staticmethod
    def _encode(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _decode(value: str) -> Any:
        raw = value or ""
        if raw in {"", "None"}:
            return ""
        if raw in {"true", "false"}:
            return raw == "true"
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            pass
        if raw[:1] in {"{", "["}:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return raw


def job_store() -> RedisJobStore:
    return RedisJobStore()


__all__ = ["JobStoreError", "RedisJobStore", "job_store"]
