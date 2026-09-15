"""Redis 存取层：异步任务状态、事件流、任务载荷、任务队列与执行租约。

键一览：
- ``agentflow:job:{job_id}``         Hash，任务状态与产物信息（含 attempts / worker_id / heartbeat_at）
- ``agentflow:job:{job_id}:events``  List，事件流（NDJSON 行，供 /stream 增量读取）
- ``agentflow:job:{job_id}:payload`` String，请求体 JSON：worker 是独立进程，必须能从 Redis 取到输入
- ``agentflow:queue``                List，待执行队列（LPUSH 入队 / BRPOP 出队）
- ``agentflow:leases``               ZSet，member=job_id、score=租约到期时间戳：心跳续期 + 超时回收

执行模式见 ``app.config.run_mode()``：inline 时只用状态与事件流，queue 时额外用队列与租约。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .config import job_max_attempts, job_ttl_seconds, lease_seconds, redis_url
from .id_worker import next_job_id

QUEUE_KEY = "agentflow:queue"
LEASE_KEY = "agentflow:leases"

_client_lock = threading.Lock()
_client = None


class JobStoreError(RuntimeError):
    """Raised when Redis job storage is unavailable."""


def _build_client():
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


def _redis_client():
    """进程内共享一个客户端（复用连接池）。

    旧实现每个请求新建客户端并 ping 一次；72 节点规模下这会造成连接数放大与
    频繁握手。连接池在 Redis 重启后会自动重建连接，所以共享是安全的。
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


class RedisJobStore:
    """Small Redis facade for async task lifecycle data."""

    def __init__(self, client=None) -> None:
        self.redis = client if client is not None else _redis_client()

    def ping(self) -> None:
        """探活：Redis 不可用时应由调用方转成 503，而不是让命令异常冒成 500。"""
        try:
            self.redis.ping()
        except Exception as exc:  # noqa: BLE001
            raise JobStoreError(f"Redis 不可用（{redis_url()}）：{exc}") from exc

    @staticmethod
    def new_job_id() -> str:
        return next_job_id()

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"agentflow:job:{job_id}"

    @staticmethod
    def _events_key(job_id: str) -> str:
        return f"agentflow:job:{job_id}:events"

    @staticmethod
    def _payload_key(job_id: str) -> str:
        return f"agentflow:job:{job_id}:payload"

    # ── 状态 ─────────────────────────────────────────────

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
            "attempts": 0,
            "worker_id": "",
            "heartbeat_at": "",
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

    # ── 任务载荷（worker 是独立进程，输入必须落 Redis）──────

    def set_payload(self, job_id: str, payload: dict[str, Any]) -> None:
        self.redis.set(
            self._payload_key(job_id),
            json.dumps(payload or {}, ensure_ascii=False),
            ex=job_ttl_seconds(),
        )

    def get_payload(self, job_id: str) -> dict[str, Any] | None:
        raw = self.redis.get(self._payload_key(job_id))
        if not raw:
            return None
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return item if isinstance(item, dict) else None

    # ── 队列 ─────────────────────────────────────────────

    def enqueue(self, job_id: str) -> None:
        self.redis.lpush(QUEUE_KEY, job_id)

    def reserve(self, timeout: int = 2) -> str | None:
        """阻塞取一个待执行 job_id（超时返回 None）。worker 空转时不烧 CPU。"""
        item = self.redis.brpop(QUEUE_KEY, timeout=timeout)
        if not item:
            return None
        value = item[1] if isinstance(item, (list, tuple)) else item
        return str(value or "").strip() or None

    def queue_length(self) -> int:
        return int(self.redis.llen(QUEUE_KEY) or 0)

    # ── 执行租约（心跳 + 超时回收）───────────────────────

    def claim(self, job_id: str, worker_id: str, phase: str = "prepare", lease: bool = True) -> int:
        """把 queued 任务置为 running 并登记租约；返回这是第几次尝试。

        ``lease=False`` 用于 inline 模式：API 进程内执行不参与超时回收
        （否则切到 queue 模式后，旧的内联任务会被 worker 判定失联并重跑）。
        """
        now = time.time()
        attempts = int(self.redis.hincrby(self._job_key(job_id), "attempts", 1))
        self.update_job(
            job_id,
            status="running",
            phase=phase,
            message="running",
            error="",
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=now,
            cost_time=0.0,
        )
        if lease:
            self.renew_lease(job_id, worker_id)
        self.append_event(
            job_id,
            {"type": "started", "job_id": job_id, "attempt": attempts, "worker_id": worker_id},
        )
        return attempts

    def renew_lease(self, job_id: str, worker_id: str, lease: int | None = None) -> None:
        seconds = int(lease or 0) or lease_seconds()
        now = time.time()
        self.redis.zadd(LEASE_KEY, {job_id: now + seconds})
        self.update_job(job_id, heartbeat_at=now, worker_id=worker_id)

    def release_lease(self, job_id: str) -> None:
        self.redis.zrem(LEASE_KEY, job_id)

    def running_count(self) -> int:
        """在跑任务数（全局并发真实值）：可用于扩容/告警。"""
        return int(self.redis.zcard(LEASE_KEY) or 0)

    def expired_leases(self, limit: int = 50) -> list[str]:
        """取出并移除已过期的租约，返回失联的 job_id 列表。"""
        now = time.time()
        rows = self.redis.zrangebyscore(LEASE_KEY, "-inf", now, start=0, num=max(1, int(limit)))
        out = [str(row).strip() for row in (rows or []) if str(row).strip()]
        if out:
            self.redis.zrem(LEASE_KEY, *out)
        return out

    # ── 终态与重试 ───────────────────────────────────────

    def requeue(self, job_id: str, reason: str, attempts: int) -> None:
        """放回队列等下一次尝试。

        顺序有意如此：先写事件（保留残留信息）→ 再翻状态 → 最后入队，
        这样 worker 取到时状态已经是 queued，不会因为状态不匹配被跳过。
        """
        self.append_event(
            job_id,
            {"type": "requeued", "job_id": job_id, "attempt": attempts, "reason": reason},
        )
        self.update_job(
            job_id,
            status="queued",
            phase="",
            message=f"requeued(attempt {attempts})",
            error=reason,
            worker_id="",
            heartbeat_at="",
        )
        self.release_lease(job_id)
        self.enqueue(job_id)

    def requeue_or_fail(
        self,
        job_id: str,
        reason: str,
        attempts: int,
        retryable: bool,
        emit_event: bool | None = None,
    ) -> str:
        """可重试且还没用尽次数 → 重排；否则判终态失败。返回最终状态。"""
        max_attempts = job_max_attempts()
        if retryable and attempts < max_attempts:
            self.requeue(job_id, reason, attempts)
            return "queued"
        return self.mark_failed(
            job_id, reason, attempts=attempts, emit_event=emit_event
        )

    def mark_failed(
        self,
        job_id: str,
        message: str,
        attempts: int = 0,
        cost_time: float = 0.0,
        emit_event: bool | None = None,
    ) -> str:
        """判终态失败。事件先落盘再翻状态，避免 /stream 提前退出漏掉最后一条事件。

        ``emit_event=None``（默认）自动判断：事件流最后一条已经是 error 就不再重复追加
        （执行体已写过详细错误时保持原样，也不会漏掉租约超时这类没人写事件的情况）。
        """
        if emit_event is None:
            emit_event = self._last_event_type(job_id) != "error"
        if emit_event:
            self.append_event(job_id, {"type": "error", "code": 500, "message": message})
        self.release_lease(job_id)
        self.update_job(
            job_id,
            status="failed",
            phase="error",
            message="failed",
            error=message,
            attempts=attempts or 0,
            finished_at=time.time(),
            cost_time=cost_time,
        )
        return "failed"

    def _last_event_type(self, job_id: str) -> str:
        rows = self.redis.lrange(self._events_key(job_id), -1, -1)
        if not rows:
            return ""
        try:
            item = json.loads(rows[0])
        except json.JSONDecodeError:
            return ""
        return str(item.get("type") or "") if isinstance(item, dict) else ""

    # ── 编码 ─────────────────────────────────────────────

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


__all__ = [
    "JobStoreError",
    "LEASE_KEY",
    "QUEUE_KEY",
    "RedisJobStore",
    "job_store",
]
