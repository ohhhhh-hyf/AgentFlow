"""独立任务 worker：从 Redis 队列取任务执行。

启动（可多开，或加 --concurrency 提升单进程并发）::

    python -m app.worker --concurrency 4 --grace 300

设计要点：
- **并发上限**：本进程开 ``--concurrency`` 个执行槽，全局并发 = 所有 worker 的并发之和；
  槽位只有在空闲时才去取任务，所以取到的任务立刻就能跑，不会"取了却排队"。
- **租约 + 心跳**：任务执行期间每 ``AGENTFLOW_HEARTBEAT_SECONDS`` 续期一次租约
  （ZSet，score=到期时间）。worker 崩溃/被杀后没人续期，租约自然过期。
- **超时回收**：每个 worker 都会周期性扫描过期租约；在跑的任务收回后按重试策略处理
  （可重试则重排，次数用尽判失败）。这是"重启卡死"的解法。
- **优雅停机**：收到 SIGTERM/SIGINT 后停止取新任务，把手上任务跑完再退出；
  超过 ``--grace`` 秒仍未跑完则退出，任务由租约超时兜底重排，不会丢。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import types
from typing import Awaitable, Callable

from .config import (
    heartbeat_seconds,
    job_max_attempts,
    lease_seconds,
    run_mode,
)
from .executor import JobOutcome, execute_job, request_from_payload
from .job_store import JobStoreError, job_store
from .tasks import LINE_NAMES

logger = logging.getLogger("agentflow.worker")

ExecuteFn = Callable[[str, str, str, object, str, str], Awaitable[JobOutcome]]
REAP_INTERVAL_SECONDS = 10.0
RESERVE_TIMEOUT_SECONDS = 2


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _heartbeat_loop(store, job_id: str, name: str, stop: asyncio.Event) -> None:
    interval = max(1, heartbeat_seconds())
    while not stop.is_set():
        try:
            await asyncio.to_thread(store.renew_lease, job_id, name)
        except Exception as exc:  # noqa: BLE001 - 续期失败不中断执行，租约到期由回收兜底
            logger.warning("lease renew failed job=%s err=%s", job_id, exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            return


async def _handle_job(store, job_id: str, name: str, execute: ExecuteFn) -> None:
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        logger.warning("skip job=%s (not found)", job_id)
        return
    status = str(job.get("status") or "")
    if status != "queued":
        # 重复入队、已被其它 worker 取走、或已被取消：直接跳过
        logger.info("skip job=%s status=%s", job_id, status or "-")
        return

    payload = await asyncio.to_thread(store.get_payload, job_id)
    if not payload:
        await asyncio.to_thread(
            store.mark_failed, job_id, "任务载荷缺失（payload 未写入或已过期）"
        )
        return
    domain, task, req, user_id, request_id = request_from_payload(payload)
    if task not in LINE_NAMES:
        await asyncio.to_thread(store.mark_failed, job_id, f"任务载荷非法：task={task}")
        return

    attempts = await asyncio.to_thread(store.claim, job_id, name)
    hb_stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_loop(store, job_id, name, hb_stop))
    try:
        outcome = await execute(job_id, domain, task, req, user_id, request_id)
    except asyncio.CancelledError:
        raise  # 停机超时被取消：保留 running + 租约，由回收器重排
    except Exception as exc:  # noqa: BLE001 - 执行体异常一律按可重试处理
        outcome = types.SimpleNamespace(
            ok=False, retryable=True, message=f"执行异常：{exc}", cost_time=0.0
        )
    finally:
        hb_stop.set()
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)

    if outcome.ok:
        await asyncio.to_thread(store.release_lease, job_id)
        logger.info("job done job=%s attempt=%s dur=%.1fs", job_id, attempts, outcome.cost_time)
        return

    final = await asyncio.to_thread(
        store.requeue_or_fail,
        job_id,
        outcome.message,
        attempts,
        bool(outcome.retryable),
    )
    logger.warning(
        "job unfinished job=%s attempt=%s/%s -> %s err=%s",
        job_id,
        attempts,
        job_max_attempts(),
        final,
        outcome.message,
    )


async def _slot(store, name: str, stop: asyncio.Event, execute: ExecuteFn) -> None:
    """一个执行槽：空闲时才取任务，取到即执行（并发上限 = 槽位数）。"""
    while not stop.is_set():
        try:
            job_id = await asyncio.to_thread(store.reserve, RESERVE_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - Redis 抖动：等一会再试
            logger.error("reserve failed err=%s", exc)
            await asyncio.sleep(1.0)
            continue
        if not job_id:
            continue
        if stop.is_set():
            # 停机中：放回队列，不要让它从队列里消失
            await asyncio.to_thread(store.enqueue, job_id)
            return
        try:
            await _handle_job(store, job_id, name, execute)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 单条任务异常不影响整个槽位
            logger.exception("job handler error job=%s err=%s", job_id, exc)


async def _reap_once(store) -> int:
    """回收租约过期的任务（执行它的 worker 已经不在了）。"""
    expired = await asyncio.to_thread(store.expired_leases)
    if not expired:
        return 0

    async def _one(job_id: str) -> None:
        job = await asyncio.to_thread(store.get_job, job_id)
        if job is None:
            return
        if str(job.get("status") or "") != "running":
            await asyncio.to_thread(store.release_lease, job_id)
            return
        attempts = int(job.get("attempts") or 0)
        reason = f"worker 失联（心跳超时 {lease_seconds()}s）"
        final = await asyncio.to_thread(
            store.requeue_or_fail, job_id, reason, attempts, True, True
        )
        logger.warning("reclaim job=%s attempts=%s -> %s", job_id, attempts, final)

    await asyncio.gather(*[_one(job_id) for job_id in expired])
    return len(expired)


async def _reaper_loop(store, stop: asyncio.Event, interval: float = REAP_INTERVAL_SECONDS) -> None:
    while not stop.is_set():
        try:
            reaped = await _reap_once(store)
            if reaped:
                logger.info("reclaimed %s jobs", reaped)
        except Exception as exc:  # noqa: BLE001 - 回收失败下一轮再试
            logger.warning("reap scan failed err=%s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(1.0, interval))
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            return


async def run_worker(
    concurrency: int = 1,
    grace: int = 300,
    *,
    stop: asyncio.Event | None = None,
    execute: ExecuteFn = execute_job,
    reap_interval: float = REAP_INTERVAL_SECONDS,
) -> None:
    """跑 worker 主循环，直到 ``stop`` 被置位（或某个槽位/回收器异常退出）。"""
    stop = stop or asyncio.Event()
    store = job_store()
    store.ping()  # 连不上就直接失败，别启动一个空转的 worker
    name = worker_id()
    concurrency = max(1, int(concurrency))

    slots = [
        asyncio.create_task(_slot(store, name, stop, execute), name=f"slot-{index}")
        for index in range(concurrency)
    ]
    reaper = asyncio.create_task(_reaper_loop(store, stop, reap_interval), name="reaper")
    stopper = asyncio.create_task(stop.wait(), name="stopper")
    logger.info(
        "worker start id=%s concurrency=%s lease=%ss heartbeat=%ss max_attempts=%s",
        name,
        concurrency,
        lease_seconds(),
        heartbeat_seconds(),
        job_max_attempts(),
    )
    try:
        await asyncio.wait(
            [*slots, reaper, stopper], return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        stop.set()
        pending = [task for task in slots if not task.done()]
        if pending:
            logger.info("draining: %s running jobs, grace=%ss", len(pending), grace)
            _done, still = await asyncio.wait(pending, timeout=max(0, int(grace)))
            for task in still:
                logger.warning("grace timeout, slot cancelled (job will be reclaimed by lease)")
                task.cancel()
        for task in slots:
            if not task.done():
                task.cancel()
        await asyncio.gather(*slots, return_exceptions=True)
        for task in (reaper, stopper):
            if not task.done():
                task.cancel()
        await asyncio.gather(reaper, stopper, return_exceptions=True)
        logger.info("worker exit id=%s", name)


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError):  # Windows：退化为普通信号处理器
            try:
                signal.signal(sig, lambda *_: stop.set())
            except (ValueError, OSError):  # 非主线程等场景直接放弃
                pass


async def _amain(concurrency: int, grace: int) -> None:
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    await run_worker(concurrency=concurrency, grace=grace, stop=stop)


def _env_int(name: str, default: int) -> int:
    try:
        value = int((os.getenv(name) or "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def main() -> None:
    from .config import load_env

    load_env()  # 必须先加载：--concurrency/--grace 的默认值在解析参数时就要读 .env
    parser = argparse.ArgumentParser(description="AgentFlow 异步任务 worker（消费 Redis 队列）")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_env_int("AGENTFLOW_WORKER_CONCURRENCY", 1),
        help="本进程同时执行的任务数，默认 1（可用环境变量 AGENTFLOW_WORKER_CONCURRENCY 指定）",
    )
    parser.add_argument(
        "--grace",
        type=int,
        default=_env_int("AGENTFLOW_WORKER_GRACE", 300),
        help="收到停机信号后等待在跑任务收尾的秒数，默认 300",
    )
    args = parser.parse_args()
    from tools.core.logging_config import setup_logging

    setup_logging()   # 与 API 侧共用同一套日志格式（时间戳 + 级别 + 模块）
    if run_mode() != "queue":
        logger.warning(
            "run_mode=%s: tasks are not queued, worker will idle"
            " (set AGENTFLOW_RUN_MODE=queue in .env to enable)",
            run_mode(),
        )
    try:
        asyncio.run(_amain(args.concurrency, args.grace))
    except JobStoreError as exc:
        raise SystemExit(f"启动失败：{exc}") from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
