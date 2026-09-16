"""AgentFlow 自测：接口清单守卫 + 异步任务队列机制（队列 / 租约 / 回收 / 重试 / 停机）。

不调用模型、不联网（执行体用桩替换），秒级跑完::

    python -m app.selftest

安全约定：队列部分**只在独立 DB 上运行**，默认 5 号库，绝不动 0 号库里的真实任务数据；
可用 ``AGENTFLOW_SELFTEST_REDIS_URL`` 覆盖（DB 不能是 0）。接口清单守卫不需要 Redis。

端到端的 HTTP 链路（提交 / 状态 / 结果 / 事件流）请用 minutes_async_*.py 四个脚本验证。
"""
from __future__ import annotations

import asyncio
import copy
import re
import json
import os
import sys
import time

os.environ.setdefault("AGENTFLOW_SELFTEST_REDIS_URL", "redis://127.0.0.1:6379/5")
os.environ["REDIS_URL"] = os.environ["AGENTFLOW_SELFTEST_REDIS_URL"]
os.environ.pop("AGENTFLOW_RUN_MODE", None)

if __package__ in {None, ""}:  # 支持 python app/selftest.py 直接运行
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import executor  # noqa: E402
from app.executor import JobOutcome  # noqa: E402
from app.job_store import RedisJobStore, job_store  # noqa: E402
from app.schemas import Extra, TaskRequest  # noqa: E402
from app.tasks import ApiError  # noqa: E402
import app.worker as worker  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{(' | ' + detail) if detail else ''}")


class RecordingStore(RedisJobStore):
    """记录"写事件"与"翻状态"的先后顺序，用于验证终态事件不会晚于状态。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.order: list[tuple[str, str]] = []

    def append_event(self, job_id, event):
        self.order.append(("event", str((event or {}).get("type"))))
        return super().append_event(job_id, event)

    def update_job(self, job_id, **fields):
        if "status" in fields:
            self.order.append(("status", str(fields["status"])))
        return super().update_job(job_id, **fields)


class FakeResponse:
    """替代 stream_task 的返回值，body_iterator 产出 NDJSON 行。"""

    def __init__(self, lines) -> None:
        self.body_iterator = self._gen(lines)

    @staticmethod
    async def _gen(lines):
        for line in lines:
            yield line


def ndjson(*payloads) -> list[str]:
    return [json.dumps(payload, ensure_ascii=False) + "\n" for payload in payloads]


def make_job(store, task: str = "minutes", texts=None) -> str:
    job_id = store.new_job_id()
    request_id = job_id.replace("job_", "request_")
    store.create_job(
        job_id=job_id, request_id=request_id, user_id="1", domain="meeting", task=task
    )
    store.set_payload(
        job_id,
        {
            "domain": "meeting", "task": task, "user_id": "1", "request_id": request_id,
            "texts": texts if texts is not None else {"transcript": "测试文本"}, "docs": [],
            "extra": {}, "time": "",
        },
    )
    return job_id


def fake_executor(result_factory):
    calls: list[str] = []

    async def _run(job_id, domain, task, req, user_id, request_id):
        calls.append(job_id)
        return result_factory(job_id, len(calls))

    _run.calls = calls
    return _run


async def run_one_round(execute, budget: float = 2.5) -> None:
    stop = asyncio.Event()
    run = asyncio.create_task(
        worker.run_worker(1, grace=10, stop=stop, execute=execute, reap_interval=0.5)
    )
    await asyncio.sleep(budget)
    stop.set()
    await asyncio.wait_for(run, timeout=20)


# ── 接口清单守卫：路由面与 app/tasklines.py 的声明保持一致 ──────

def test_routes() -> None:
    """不需要 Redis：只核对 FastAPI 暴露的路由面与任务线声明是否同步。"""
    from app.main import app
    from app.tasklines import DOMAINS

    routes = {
        (getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", None) or [])))
        for route in app.routes
        if getattr(route, "path", None)
    }

    expected: set[tuple[str, tuple[str, ...]]] = set()
    for domain, items in DOMAINS.items():
        base = f"/api/v1/{domain}"
        for item in items:
            expected.add((f"{base}/{item.line}", ("POST",)))
            expected.add((f"{base}/{item.line}/stream", ("POST",)))
            if item.files:
                expected.add((f"{base}/{item.line}/file/{{request_id}}/{{file_name}}", ("GET",)))
                expected.add((f"{base}/{item.line}/preview", ("GET",)))
    missing = sorted(expected - routes)
    check(
        "任务线路由与 app/tasklines.py 声明一致",
        not missing,
        f"缺少 {len(missing)} 条：{missing}" if missing else f"{len(expected)} 条齐全",
    )

    removed = {
        ("/api/v1/meeting/consensus", ("POST",)),
        ("/api/v1/meeting/decision", ("POST",)),
        ("/api/v1/meeting/minutes/file", ("GET",)),
        ("/api/v1/notes/graph/file", ("GET",)),
    }
    check("已移除的端点形态不再暴露", not (removed & routes),
          f"仍存在：{sorted(removed & routes)}" if removed & routes else "便捷下载 / 同义 URL 已下线")

    async_group = {
        ("/api/v1/tasks", ("POST",)),
        ("/api/v1/tasks/{job_id}", ("GET",)),
        ("/api/v1/tasks/{job_id}/result", ("GET",)),
        ("/api/v1/tasks/{job_id}/stream", ("GET",)),
    }
    check("异步任务接口四件套齐全", async_group <= routes,
          f"缺少：{sorted(async_group - routes)}" if async_group - routes else "提交/状态/结果/事件流")

    misc = {("/api/v1/health", ("GET",)), ("/data", ())}
    check("健康检查与 /data 静态目录已挂载", misc <= routes,
          f"缺少：{sorted(misc - routes)}" if misc - routes else "/api/v1/health、/data")


# ── 队列 / 租约 / 回收 / 重试 / 停机 ─────────────────────────

async def test_queue(store) -> None:
    store.redis.flushdb()

    job = make_job(store)
    store.enqueue(job)
    ex = fake_executor(lambda jid, n: JobOutcome(True, False, "", 0.1))
    await run_one_round(ex)
    got = store.get_job(job)
    check("队列被执行", ex.calls == [job], f"calls={ex.calls}")
    check("attempts 记为 1", int(got["attempts"]) == 1, f"attempts={got['attempts']}")
    check("worker_id 已写入", bool(got["worker_id"]), f"worker_id={got['worker_id']}")
    check("心跳时间已写入", bool(got["heartbeat_at"]), f"heartbeat_at={got['heartbeat_at']}")
    check("完成后释放租约", store.running_count() == 0, f"zcard={store.running_count()}")
    check("队列已空", store.queue_length() == 0, f"llen={store.queue_length()}")

    store.redis.flushdb()
    job = make_job(store)
    store.enqueue(job)
    ex = fake_executor(lambda jid, n: JobOutcome(False, True, f"boom-{n}", 0.1))
    await run_one_round(ex, budget=3.0)
    got = store.get_job(job)
    events = [e["type"] for e in store.events_since(job, 0)]
    check("可重试失败会重排后重试", int(got["attempts"]) == 2, f"attempts={got['attempts']}")
    check("次数用尽判失败", got["status"] == "failed", f"status={got['status']}")
    check("保留最后一次错误", "boom-2" in str(got["error"]), f"error={got['error']}")
    check("事件流含重排", "requeued" in events, f"events={events}")
    check("事件流含两次 started", events.count("started") == 2, f"events={events}")
    check("重试后释放租约", store.running_count() == 0)

    store.redis.flushdb()
    job = make_job(store)
    store.enqueue(job)
    ex = fake_executor(lambda jid, n: JobOutcome(False, False, "缺少必填项", 0.1))
    await run_one_round(ex)
    got = store.get_job(job)
    check("输入类错误不重试（只 1 次）", int(got["attempts"]) == 1, f"attempts={got['attempts']}")
    check("输入类错误直接判失败", got["status"] == "failed", f"status={got['status']}")

    store.redis.flushdb()
    job = make_job(store)
    store.claim(job, "ghost-worker")
    store.renew_lease(job, "ghost-worker", lease=1)
    await asyncio.sleep(1.2)
    reaped = await worker._reap_once(store)
    after = store.get_job(job)
    check("失联任务被回收", reaped == 1, f"reaped={reaped}")
    check("回收后重排回队列", after["status"] == "queued", f"status={after['status']}")
    check("回收保留尝试计数", int(after["attempts"]) == 1, f"attempts={after['attempts']}")
    check("回收原因写明失联", "失联" in str(after["error"]), f"error={after['error']}")
    check("租约已清", store.running_count() == 0, f"zcard={store.running_count()}")
    check("不会重复回收", await worker._reap_once(store) == 0)

    store.redis.flushdb()
    slow = make_job(store)
    waiting = make_job(store)
    store.enqueue(slow)
    store.enqueue(waiting)

    async def slow_exec(job_id, domain, task, req, user_id, request_id):
        await asyncio.sleep(1.5)
        return JobOutcome(True, False, "", 1.5)

    started = time.time()
    stop = asyncio.Event()
    run = asyncio.create_task(
        worker.run_worker(1, grace=10, stop=stop, execute=slow_exec, reap_interval=0.5)
    )
    await asyncio.sleep(0.5)
    stop.set()
    await asyncio.wait_for(run, timeout=20)
    elapsed = time.time() - started
    check("优雅停机等手上任务跑完", elapsed >= 1.5, f"{elapsed:.2f}s")
    check("手上的任务未被丢弃", store.get_job(slow)["status"] == "running")
    check("停机后不取新任务", store.get_job(waiting)["status"] == "queued",
          f"status={store.get_job(waiting)['status']}")
    check("未开始的任务仍在队列", store.queue_length() == 1, f"llen={store.queue_length()}")

    store.redis.flushdb()
    stop = asyncio.Event()
    run = asyncio.create_task(worker.run_worker(1, grace=5, stop=stop,
                                               execute=fake_executor(lambda j, n: JobOutcome(True)),
                                               reap_interval=0.5))
    await asyncio.sleep(0.2)
    t0 = time.time()
    stop.set()
    await asyncio.wait_for(run, timeout=10)
    check("空队列停机不被 BRPOP 卡住", time.time() - t0 < 3.0, f"{time.time() - t0:.2f}s")

    store.redis.flushdb()
    job = make_job(store)
    store.enqueue(job)
    ex = fake_executor(lambda jid, n: JobOutcome(True, False, "", 0.1))
    await run_one_round(ex, budget=1.5)
    store.enqueue(job)  # 重复投递
    before = len(ex.calls)
    await run_one_round(ex, budget=1.5)
    check("状态非 queued 的重复投递被跳过", len(ex.calls) == before, f"calls={len(ex.calls)}")


# ── 执行体契约：事件顺序 / 错误分类 / 载荷往返 ────────────────

async def test_executor(store) -> None:
    store.redis.flushdb()
    real = job_store()
    recorder = RecordingStore(real.redis)
    executor.job_store = lambda: recorder
    req = TaskRequest(texts={"transcript": "测试"}, docs=[], extra=Extra(), time="")
    done_event = {
        "type": "done", "code": 0, "request_id": "request_t", "message": "success",
        "quality_warning": None,
        "monitor": {"token_usage": 123, "cache_hit": 45, "cost_time": 9.5},
        "data": {"text": "# 正文", "file_name": "minutes.html"},
    }
    original_stream = executor.stream_task

    async def ok_stream(*args, **kwargs):
        return FakeResponse(ndjson(
            {"type": "phase", "node": "meeting_understanding"},
            {"type": "chunk", "line": "minutes", "title": "会议纪要", "text": "# 正"},
            done_event,
        ))

    executor.stream_task = ok_stream
    job_id = make_job(store)
    outcome = await executor.execute_job(job_id, "meeting", "minutes", req, "1", "request_t")
    job = store.get_job(job_id)
    order = recorder.order
    check("成功路径 outcome.ok", outcome.ok)
    check("状态 succeeded", job["status"] == "succeeded", f"status={job['status']}")
    check("结果已落盘", isinstance(job.get("result"), dict), f"type={type(job.get('result')).__name__}")
    check("monitor 字段写入", (job["token_usage"], job["cache_hit"]) == (123, 45),
          f"token={job['token_usage']} cache={job['cache_hit']}")
    check("done 事件先于 status=succeeded（竞态已修）",
          ("event", "done") in order and order.index(("event", "done")) < order.index(("status", "succeeded")),
          f"order={order}")
    check("chunk 只推进进度不改状态", order.count(("status", "succeeded")) == 1, f"order={order}")
    events = [e["type"] for e in store.events_since(job_id, 0)]
    check("phase/chunk 事件进事件流（/stream 要能回放）",
          "phase" in events and "chunk" in events, f"events={events}")

    async def bad_input(*args, **kwargs):
        raise ApiError(400, "minutes 缺少必填项：texts 中 transcript")

    executor.stream_task = bad_input
    job_id = make_job(store)
    outcome = await executor.execute_job(job_id, "meeting", "minutes", req, "1", "request_t")
    events = store.events_since(job_id, 0)
    check("4xx 判为不可重试", outcome.retryable is False, f"retryable={outcome.retryable}")
    check("4xx error 事件带 400", [e.get("code") for e in events if e["type"] == "error"] == [400],
          f"events={[(e['type'], e.get('code')) for e in events]}")

    async def boom(*args, **kwargs):
        raise RuntimeError("连接超时")

    executor.stream_task = boom
    job_id = make_job(store)
    outcome = await executor.execute_job(job_id, "meeting", "minutes", req, "1", "request_t")
    events = store.events_since(job_id, 0)
    check("运行异常判为可重试", outcome.retryable is True, f"retryable={outcome.retryable}")
    check("运行异常 error 事件带 500",
          [e.get("code") for e in events if e["type"] == "error"] == [500],
          f"events={[(e['type'], e.get('code')) for e in events]}")

    async def err_400(*args, **kwargs):
        return FakeResponse(ndjson({"type": "error", "code": 400, "message": "文件不存在"}))

    executor.stream_task = err_400
    job_id = make_job(store)
    outcome = await executor.execute_job(job_id, "meeting", "minutes", req, "1", "request_t")
    events = store.events_since(job_id, 0)
    check("流内 code=400 不可重试", outcome.retryable is False)
    check("流内 error 事件只落一条", [e["type"] for e in events].count("error") == 1,
          f"events={[e['type'] for e in events]}")

    async def err_500(*args, **kwargs):
        return FakeResponse(ndjson({"type": "error", "code": 500, "message": "模型超时"}))

    executor.stream_task = err_500
    job_id = make_job(store)
    outcome = await executor.execute_job(job_id, "meeting", "minutes", req, "1", "request_t")
    check("流内 code=500 可重试", outcome.retryable is True)
    executor.stream_task = original_stream

    # 终态失败兜底：最后一条事件不是 error 时应补一条
    job_id = make_job(store)
    store.mark_failed(job_id, "租约超时", attempts=1)
    events = [e["type"] for e in store.events_since(job_id, 0)]
    check("mark_failed 兜底补 error 事件", events[-1] == "error", f"events={events}")
    job_id = make_job(store)
    store.append_event(job_id, {"type": "error", "code": 400, "message": "已有"})
    store.mark_failed(job_id, "重复的失败", attempts=1)
    events = [e["type"] for e in store.events_since(job_id, 0)]
    check("已有 error 时不重复追加", events.count("error") == 1, f"events={events}")

    original = TaskRequest(
        texts={"transcript": "转写", "keypoints": "重点", "notes": "笔记"},
        docs=["a.docx", "b.jpg"],
        extra=Extra(template="meeting_minutes_team_meeting", profile="teacher", subject="数学",
                    style="time", project="p1", memory=True),
        time="2026-09-15",
    )
    payload = executor.payload_from_request("meeting", "minutes_trace", original,
                                           user_id="u9", request_id="request_x")
    domain, task, restored, user_id, request_id = executor.request_from_payload(payload)
    check("载荷往返：标识字段", (domain, task, user_id, request_id)
          == ("meeting", "minutes_trace", "u9", "request_x"),
          f"{(domain, task, user_id, request_id)}")
    check("载荷往返：texts", restored.texts == original.texts, f"{restored.texts}")
    check("载荷往返：docs", restored.docs == original.docs, f"{restored.docs}")
    check("载荷往返：extra", restored.extra.model_dump() == original.extra.model_dump(),
          f"{restored.extra.model_dump()}")
    check("载荷往返：time", restored.time == original.time, f"{restored.time}")
    executor.job_store = job_store


# ── 异步四接口的统一响应体（对外契约，不需要 Redis）──────────

SHAPE_KEYS = {"code", "job_id", "request_id", "status", "message", "text", "file_name", "monitor"}
MONITOR_KEYS = {"token_usage", "cache_hit", "cost_time"}
DONE_EVENT = {
    "type": "done", "code": 0, "request_id": "request_t", "message": "success",
    "quality_warning": None,
    "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6},
    "data": {"text": "# 正文", "file_name": "minutes.html"},
}


def test_async_response_shape() -> None:
    """锁定四个异步接口共用同一份响应体（字段集与关键取值）。"""
    from app.routes.tasks import _event_view, _job_view

    base = {
        "job_id": "job_1", "request_id": "request_1", "status": "queued", "message": "queued",
        "error": "", "file_name": "", "token_usage": 0, "cache_hit": 0, "cost_time": 0.0,
    }
    cases = [
        ("提交", dict(base), False, {"status": "queued", "message": "queued", "text": None}),
        ("状态(执行中)", {**base, "status": "running", "message": "running:minutes",
                      "token_usage": 8200, "cache_hit": 5120, "cost_time": 3.2},
         False, {"status": "running", "message": "running:minutes", "text": None,
                 "token_usage": 8200}),
        ("状态(已成功，不给正文)", {**base, "status": "succeeded", "message": "success",
                            "file_name": "minutes.html", "result": DONE_EVENT},
         False, {"status": "succeeded", "text": None, "file_name": "minutes.html"}),
        ("结果(已成功)", {**base, "status": "succeeded", "message": "success",
                      "file_name": "minutes.html", "result": DONE_EVENT},
         True, {"status": "succeeded", "text": "# 正文", "file_name": "minutes.html"}),
        ("结果(失败，不再 409)", {**base, "status": "failed", "message": "failed",
                            "error": "texts / docs 至少提供一个"},
         True, {"status": "failed", "message": "texts / docs 至少提供一个", "text": None}),
    ]
    for name, job, with_text, expected in cases:
        view = _job_view(job, with_text=with_text)
        extra = {"quality_warning"} if "quality_warning" in view else set()
        check(f"统一响应体字段集：{name}", set(view) == SHAPE_KEYS | extra, f"keys={sorted(view)}")
        check(f"monitor 字段集：{name}", set(view["monitor"]) == MONITOR_KEYS)
        for key, value in expected.items():
            got = view["monitor"].get(key, view.get(key)) if key in MONITOR_KEYS else view.get(key)
            check(f"{name} → {key}", got == value, f"{key}={got!r}" + ("" if got == value else f"（期望 {value!r}）"))

    warning_job = {**base, "status": "succeeded", "message": "success",
                   "result": {**DONE_EVENT, "quality_warning": "模板被拒，已降级"}}
    check("质量提示作为可选字段出现",
          _job_view(warning_job, with_text=True).get("quality_warning") == "模板被拒，已降级")

    samples = {
        "queued": {"type": "queued", "request_id": "request_1"},
        "started": {"type": "started", "attempt": 1},
        "phase": {"type": "phase", "node": "minutes"},
        "chunk": {"type": "chunk", "title": "会议纪要", "text": "# 正"},
        "requeued": {"type": "requeued", "attempt": 1, "reason": "模型超时"},
        "error": {"type": "error", "code": 500, "message": "模型超时"},
        "done": DONE_EVENT,
    }
    for etype, raw in samples.items():
        view = _event_view("job_1", raw)
        check(f"事件 {etype} 恒定 type/job_id/status/message",
              view.get("type") == etype and view.get("job_id") == "job_1"
              and view.get("status") and view.get("message"),
              f"view={view}")
    done_view = _event_view("job_1", DONE_EVENT)
    check("done 事件 = 结果接口（仅多一个 type）",
          set(done_view) - {"type"} == SHAPE_KEYS and "quality_warning" not in done_view,
          f"keys={sorted(done_view)}")
    check("done 事件带完整产物",
          done_view["text"] == "# 正文" and done_view["file_name"] == "minutes.html"
          and done_view["monitor"]["cost_time"] == 9.6)


# ── 目录顺序轴 / 覆盖：原文位置来自入库元数据，缺节必须补得回来 ──────

class _FakeKB:
    """只提供 list_chunks 的假知识库（briefing/位置表/补缺都只消费元数据）。"""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def list_chunks(self, **_kwargs) -> list[dict]:
        return [{"metadata": dict(row)} for row in self._rows]

    def list_files(self, **_kwargs) -> list[str]:
        return sorted({str(r.get("source") or "") for r in self._rows})


def _fake_rows() -> list[dict]:
    """模仿 OCR 合并稿入库后的元数据：chunk_index 递增、层级/分数取自入库。"""
    src = "ocr_20990101_000000.md"
    rows: list[dict] = []

    def add(heading: str, ci: str, score: int, kind: str, path: str, chapter: str,
            topic: str = "") -> None:
        rows.append(
            {
                "source": src,
                "chapter": chapter,
                "topic": topic,
                "heading": heading,
                "heading_path_text": path,
                "page": "",
                "chunk_index": ci,
                "heading_score": str(score),
                "heading_kind": kind,
                "content_tags": "",
                "contains_formula": "0",
                "role": "notes",
            }
        )

    # 前两页：层级浅 → score=3 / evidence（正是被隐藏的那两节）
    add("一维束缚态", "0-0", 3, "evidence", "一维束缚态", "一维束缚态")
    add("一维半无限深方势阱", "2-0", 3, "evidence", "一维半无限深方势阱", "一维半无限深方势阱")
    # 后文：层级正常 → 5/6 分
    add("一维谐振子", "6-0", 5, "topic", "一维谐振子", "一维谐振子")
    add("幂级数解法", "9-0", 5, "knowledge_point", "一维谐振子 / 幂级数解法",
        "一维谐振子", "幂级数解法")
    add("氢原子", "30-0", 6, "chapter", "氢原子", "氢原子")
    add("例题1", "34-0", 5, "knowledge_point", "氢原子 / 例题1", "氢原子", "例题1")
    return rows


def test_catalog_order_and_coverage() -> None:
    """不需要 OCR / 模型 / 真实知识库：位置轴来自入库元数据，缺节能被补回并保序。"""
    import domain.notes.tasks.catalog.gather as gather

    kb = _FakeKB(_fake_rows())
    original = gather.open_knowledge
    import tools.knowledge.cite as cite_mod

    original_cite = cite_mod.open_knowledge
    gather.open_knowledge = lambda user_id="": kb
    cite_mod.open_knowledge = lambda user_id="": kb  # 元数据回退骨架也走这个入口
    try:
        ctx = "【用户ID】__selftest__\n【学科/课程】wuli\n"
        grouped = gather._brief_chunks(kb, "__selftest__", "wuli")
        cands = gather._title_candidates(grouped)
        order = [row["path"][0] for row in cands]
        check("候选顺序 = 原文位置（不再按标题字符串）",
              order[0] == "一维束缚态" and order[1] == "一维半无限深方势阱",
              f"前两条={order[:2]}")
        pos = gather.build_catalog_position_map(ctx)
        check("位置表能拿到前两页的位置",
              pos.get("一维束缚态") == 0 and pos.get("一维半无限深方势阱") == 1,
              f"pos={ {k: pos.get(k) for k in ('一维束缚态', '一维半无限深方势阱', '氢原子')} }")
        brief = gather.build_catalog_briefing(ctx)
        # 骨架段标题：Md 来源为【原文骨架（权威）】，元数据回退骨架为【来源结构骨架】
        skeleton_seg = next(
            (s for s in brief.split("【")
             if s.startswith("原文骨架（权威）") or s.startswith("来源结构骨架")),
            "",
        )
        # 元数据骨架只收 high/medium 信号（低分标题留作正文 evidence）；
        # 低分小节由 Md 骨架那条路兜（test_skeleton_parse_and_contract 已覆盖）
        check("有骨架时强信号标题进骨架段（权威输入）",
              "一维谐振子" in skeleton_seg and "氢原子" in skeleton_seg,
              f"骨架段首={skeleton_seg[:60]!r}")
        import domain.notes.tasks.catalog.skeleton as skeleton_mod

        original_build = skeleton_mod.build_source_skeleton
        skeleton_mod.build_source_skeleton = lambda _ctx: {"topics": []}
        try:
            fallback_brief = gather.build_catalog_briefing(ctx)
        finally:
            skeleton_mod.build_source_skeleton = original_build
        low_seg = next((s for s in fallback_brief.split("【") if s.startswith("低可信标题")), "")
        check("无骨架回退时低可信标题列出名字并允许用作小节",
              "一维半无限深方势阱" in low_seg and "照常建主题或 KP" in low_seg,
              f"段首={low_seg[:60]!r}")
        check("例题类标题仍不进补缺范围",
              all("例题" not in " / ".join(c["path"]) for c in cands if gather._fillable_title(c)),
              "fillable 含例题")

        draft = {
            "chapters": [
                {
                    "id": "ch_001",
                    "name": "氢原子",
                    "topics": [{
                        "id": "tp_001",
                        "name": "哈密顿量",
                        "knowledge_points": [{"id": "kp_001", "name": "氢原子哈密顿量",
                                              "importance": "3"}],
                    }],
                }
            ]
        }
        # P4 起：有骨架时输出侧补缺让位（覆盖由骨架侧 restore 负责），所以这里改验
        # "补缺不动目录" + "骨架还原把缺的整节补回并保序"。
        same = gather.complement_catalog_coverage(copy.deepcopy(draft), ctx)
        check("有骨架时输出侧补缺不改目录",
              json.dumps(same, ensure_ascii=False, sort_keys=True)
              == json.dumps(draft, ensure_ascii=False, sort_keys=True),
              f"章={[c.get('name') for c in same.get('chapters') or []]}")

        from domain.notes.tasks.catalog.skeleton import (
            build_source_skeleton,
            restore_from_skeleton,
        )

        skeleton = build_source_skeleton(ctx)
        filled, restore_report = restore_from_skeleton(copy.deepcopy(draft), skeleton)
        names = [c.get("name") for c in filled.get("chapters") or []]
        # 元数据骨架只认 high/medium 信号（低分标题留作正文），所以补回的是 `一维谐振子`
        # 这类强信号节点；两个低分小节由 Md 骨架那条路负责（见 test_skeleton_* 系列）
        check("缺的整节由骨架还原补回目录（program_restore）",
              "一维谐振子" in restore_report["restored_topics"] and "氢原子" in names,
              f"章={names} 补齐={restore_report['restored_topics']}")
        check("还原不产生同名重复节点",
              len(gather._catalog_node_names(filled)) == len(set(gather._catalog_node_names(filled)))
              and "氢原子" in names,
              f"章={names}")
        ordered = gather.order_catalog_by_source(filled, ctx)
        restored_topics = [
            str(t.get("name"))
            for c in ordered.get("chapters") or []
            for t in c.get("topics") or []
        ]
        quality = _coverage_tools().evaluate(skeleton, ordered)
        check("还原后同级顺序仍单调（顺序跟骨架）",
              restored_topics.count("一维谐振子") == 1 and not quality["level_violations"],
              f"主题={restored_topics} violations={quality['level_violations'][:2]}")
        kp_names = [str(k.get("name")) for c in ordered.get("chapters") or []
                    for t in c.get("topics") or [] for k in t.get("knowledge_points") or []]
        check("还原的 KP 带 program_restore 标记且不重复建",
              all(
                  sum(1 for n in kp_names if n == name) == 1 for name in set(kp_names)
              ) and any(
                  str(k.get("node_status")) == "program_restore"
                  for c in ordered.get("chapters") or []
                  for t in c.get("topics") or []
                  for k in t.get("knowledge_points") or []
              ),
              f"kp={kp_names[:6]}")
    finally:
        gather.open_knowledge = original
        cite_mod.open_knowledge = original_cite


def test_ingest_position_axis() -> None:
    """不需要知识库：页块标记 → page/page_span；md 无条件写递增块序；层级按文件归一。"""
    from tools.knowledge.document_processor import _chunks_by_heading

    sample = (
        "<!-- ocr-pages: 1-2 -->\n### 一维束缚态\n\n定态薛定谔方程与连续性条件。\n\n"
        "### 半无限深方势阱\n\n分区求解并匹配边界条件。\n\n"
        "<!-- ocr-pages: 3-4 -->\n### 谐振子\n\n幂级数解法构造递推关系。\n"
    )
    chunks = _chunks_by_heading(sample, "data/__selftest__/ocr/wuli/ocr_x.md")
    metas = [c.metadata for c in chunks]
    check("页块标记写进 page/page_span",
          [m.get("page") for m in metas] == [1, 1, 3]
          and [m.get("page_span") for m in metas] == ["1-2", "1-2", "3-4"],
          f"page={[m.get('page') for m in metas]} span={[m.get('page_span') for m in metas]}")
    check("md 块带文件内递增 chunk_index",
          [m.get("chunk_index") for m in metas] == ["0-0", "1-0", "2-0"],
          f"ci={[m.get('chunk_index') for m in metas]}")
    check("标题层级按文件内最浅层归一（整篇 ### → 1 级）",
          all(m.get("heading_level") == 1 for m in metas)
          and all(str(m.get("heading_level_raw")) == "3" for m in metas),
          f"lvl={[m.get('heading_level') for m in metas]} raw={[m.get('heading_level_raw') for m in metas]}")
    check("归一后不再被判成低分证据",
          all(int(m.get("heading_score") or 0) >= 4 for m in metas)
          and all(m.get("heading_kind") != "evidence" for m in metas),
          f"score={[m.get('heading_score') for m in metas]} kind={[m.get('heading_kind') for m in metas]}")
    check("标记行不进块正文",
          all("ocr-pages" not in c.text for c in chunks), "标记泄进正文")

    # 文件内已有 # 时不做移位（避免整篇被抬级）
    body = "这是正文段落，长度足够通过块级内容门，避免退化成单块兜底路径。"
    mixed = f"# 章一\n\n{body}\n\n### 小节\n\n{body}再来一句以凑够长度。\n"
    mixed_chunks = _chunks_by_heading(mixed, "x.md")
    lvls = [c.metadata.get("heading_level") for c in mixed_chunks]
    raws = [c.metadata.get("heading_level_raw") for c in mixed_chunks]
    check("文件已有 # 时保持原层级、只记录 raw",
          lvls == [1, 3] and raws == [None, None], f"lvl={lvls} raw={raws}")


def test_metadata_source_skeleton() -> None:
    """没有 OCR Md 文件时，catalog 可从知识库 metadata 生成虚拟骨架并补缺。"""
    import copy
    import domain.notes.tasks.catalog.skeleton as skeleton_mod

    rows = _fake_rows()
    kb = _FakeKB(rows)

    # build_metadata_skeleton 在函数内 import open_knowledge；这里 patch cite 模块入口。
    import tools.knowledge.cite as cite

    old_cite = cite.open_knowledge
    cite.open_knowledge = lambda user_id="": kb
    try:
        ctx = "【用户ID】__selftest_no_md__\n【学科/课程】wuli\n"
        sk = skeleton_mod.build_source_skeleton(ctx)
        names = [t.get("name") for t in sk.get("topics") or []]
        check("无 Md 时回退 metadata 虚拟骨架",
              sk.get("kind") == "metadata" and "一维谐振子" in names and "氢原子" in names,
              f"kind={sk.get('kind')} topics={names}")
        pos = skeleton_mod.skeleton_position_map(sk)
        check("虚拟骨架也提供排序位置",
              pos.get("一维谐振子") is not None and pos.get("氢原子") is not None
              and pos["一维谐振子"] < pos["氢原子"],
              f"pos={ {k: pos.get(k) for k in ('一维谐振子', '氢原子')} }")
        draft = {
            "chapters": [{
                "id": "ch_001",
                "name": "氢原子",
                "topics": [{
                    "id": "tp_001",
                    "name": "哈密顿量",
                    "knowledge_points": [{"id": "kp_001", "name": "氢原子哈密顿量"}],
                }],
            }]
        }
        restored, report = skeleton_mod.restore_from_skeleton(copy.deepcopy(draft), sk)
        restored_topics = [
            t.get("name")
            for c in restored.get("chapters") or []
            for t in c.get("topics") or []
            if isinstance(t, dict)
        ]
        check("虚拟骨架参与补缺",
              report["restored_topics"] and "一维谐振子" in restored_topics,
              f"restored={report} topics={restored_topics}")
    finally:
        cite.open_knowledge = old_cite


def _coverage_tools():
    """加载覆盖校验脚本（与 CLI 同一套判定口径，避免两套实现漂移）。"""
    import importlib.util
    from pathlib import Path as _Path

    path = _Path(__file__).resolve().parents[1] / "tools" / "scripts" / "check_catalog_coverage.py"
    spec = importlib.util.spec_from_file_location("_agentflow_coverage_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_SKELETON_MD = """<!-- ocr-pages: 1-2 -->
### 一维束缚态

在一维情况下，定态薛定谔方程简化为二阶常微分方程，边界条件由势函数给出连续性要求。

### 一维半无限深方势阱

势函数在有限高度处截断，分区求解后匹配边界条件，能量本征值离散。

<!-- ocr-pages: 3-4 -->
## 一维束缚态（续）

分离变量后角向部分与径向部分解耦，角向方程给出球谐函数形式的解。

### 补充：坐标系变换

直角坐标与球坐标的度规不同，梯度算子要随之改写，便于后续计算。

#### 例题 1

把梯度算子写成球坐标分量形式，注意角向分量的 1/r 与 1/(r sinθ) 因子。

<!-- ocr-pages: 5-8 -->
# 氢原子

## 概率密度角度分布与径向分布

### 径向分布函数

只与 r 有关，$P(r)dr = |R_{nl}(r)|^2 r^2 dr$ 表示半径 r 处厚度 dr 球壳内的概率。

概率密度角度分布由球谐函数决定，径向分布由拉盖尔多项式决定。
"""


def test_skeleton_parse_and_contract() -> None:
    """不需要 OCR / 模型 / 知识库：md → 三级骨架（层级映射、修补四规则、顺序、契约）。"""
    from domain.notes.tasks.catalog.skeleton import (
        is_item_heading,
        parse_md_skeleton,
        skeleton_position_map,
        skeleton_prompt_block,
    )

    skeleton = parse_md_skeleton(_SKELETON_MD, source="ocr_selftest.md")
    stats = skeleton["stats"]
    chapters = [c["name"] for c in skeleton["chapters"]]
    check("按文件层级数归一：三级文件 → 出章（span=3）",
          stats["span"] == 3 and stats["levels"] == [1, 2, 3],
          f"span={stats['span']} levels={stats['levels']}")
    check("章 = 原文一级/最浅级标题（按原文顺序）",
          chapters == ["一维束缚态", "氢原子"],
          f"chapters={chapters}")
    check("续页标题并入同名节点（修补①）",
          "一维束缚态（续）" not in chapters
          and any("分离变量" in str(c.get("body") or "") for c in skeleton["chapters"]),
          f"chapters={chapters}")
    chapter_topics = {
        c["name"]: [t["name"] for t in c.get("topics") or []] for c in skeleton["chapters"]
    }
    # 与章同级的「一维半无限深方势阱」在原文里是章内的小节：层级归一（R1）把它按
    # 「X / X（续）」的容器关系降为主题，挂在「一维束缚态」下（不再单列成假章）。
    check("二级标题 = 主题、挂在所属章下（层级映射）",
          chapter_topics.get("一维束缚态") == ["一维半无限深方势阱", "补充：坐标系变换"]
          and chapter_topics.get("氢原子") == ["概率密度角度分布与径向分布"],
          f"chapter_topics={chapter_topics}")
    check("名字去序号/尾部标点（修补④）",
          all("例题" not in n for n in sum(chapter_topics.values(), [])),
          f"names={sum(chapter_topics.values(), [])}")
    spans = [c["page_span"] for c in skeleton["chapters"]]
    check("页块标记写进 page/page_span",
          spans[0] == "1-2" and spans[-1] == "5-8", f"span={spans}")
    orders = [c["order"] for c in skeleton["chapters"]]
    check("order 严格递增（文件序 → 页序 → 节序）",
          orders == sorted(orders) and len(set(orders)) == len(orders), f"orders={orders}")
    probe = next(
        (t for c in skeleton["chapters"] for t in c.get("topics") or []
         if t["name"] == "补充：坐标系变换"),
        None,
    )
    points = [p["name"] for p in (probe or {}).get("points") or []]
    check("细碎标题（例题）不建节点，其正文并入父节点正文",
          is_item_heading("例题 1") and points == []
          and "梯度算子" in str((probe or {}).get("body") or ""),
          f"points={points} body={str((probe or {}).get('body'))[:26]!r}")
    kp_topic = next(
        (t for c in skeleton["chapters"] for t in c.get("topics") or []
         if t["name"] == "概率密度角度分布与径向分布"),
        None,
    )
    check("三级文件里第三层 = 知识点（径向分布函数）",
          [p["name"] for p in (kp_topic or {}).get("points") or []] == ["径向分布函数"],
          f"points={[p['name'] for p in (kp_topic or {}).get('points') or []]}")
    check("章正文可读（紧接子标题的章正文为空，属正常）",
           sum(1 for c in skeleton["chapters"] if c["body"]) >= 1
           and any(not c["body"] for c in skeleton["chapters"]),
           f"bodies={[len(c['body']) for c in skeleton['chapters']]}")
    block = skeleton_prompt_block(skeleton)
    check("prompt 段带 C/T/P 三级标记与硬约束",
          "[C chapter order=" in block and "[T topic order=" in block and "[P kp order=" in block
          and "必须覆盖骨架里**每一个** C（章，若有）/ T（主题）/ P（知识点）" in block
          and "章一律沿用骨架给出的章名与顺序" in block
          and "请从正文提炼" in block,
          f"len={len(block)}")
    pos = skeleton_position_map(skeleton)
    check("位置表覆盖章/主题/知识点（含去序号写法）",
          "氢原子" in pos and "补充坐标系变换" in pos
          and pos["氢原子"] > pos["一维束缚态"],
          f"sample={ {k: pos[k] for k in list(pos)[:4]} }")
    check("体检观测指标：每主题 KP 数上限",
          stats["chapters"] == 2 and stats["max_kp_per_topic"] == 1,
          f"chapters={stats['chapters']} max_kp_per_topic={stats['max_kp_per_topic']}")


def test_skeleton_restore_and_order() -> None:
    """不需要模型：模型漏节点/乱序/降级后，骨架校验把覆盖与顺序拉回硬指标。"""
    from domain.notes.tasks.catalog.skeleton import parse_md_skeleton, restore_from_skeleton

    coverage = _coverage_tools()
    skeleton = parse_md_skeleton(_SKELETON_MD, source="ocr_selftest.md")

    # 模型输出：漏掉第 1、2 个主题，乱序 KP，把一个 KP 降级进 items
    draft = {
        "chapters": [
            {
                "id": "ch_001",
                "name": "量子力学基础",
                "topics": [
                    {
                        "id": "tp_001",
                        "name": "氢原子",
                        "knowledge_points": [
                            {"id": "kp_001", "name": "概率密度角度分布与径向分布", "importance": "3"},
                        ],
                    },
                    {
                        "id": "tp_002",
                        "name": "一维束缚态",
                        "knowledge_points": [
                            {"id": "kp_002", "name": "补充：坐标系变换", "knowledge_items": ["例题 1"]},
                        ],
                    },
                ],
            }
        ]
    }
    before = coverage.evaluate(skeleton, draft)
    restored, report = restore_from_skeleton(copy.deepcopy(draft), skeleton)
    after = coverage.evaluate(skeleton, restored)
    check("模型漏的主题被补回（program_restore）",
          len(report["restored_topics"]) >= 1 and after["coverage"] > before["coverage"],
          f"before={before['coverage']:.2f} after={after['coverage']:.2f} "
          f"补齐={report['restored_topics'] + report['restored_points']}")
    check("骨架校验后覆盖 100%（顺序由下一步保序负责）",
          after["coverage"] == 1.0 and not after["uncovered_topics"] and not after["uncovered_points"],
          f"缺主题={after['uncovered_topics']} 缺KP={after['uncovered_points']}")
    check("降级进 items 的不再重复建节点（算覆盖）",
          not any("补充坐标系变换" == n for n in after["uncovered_points"]),
          f"demoted={report['demoted_kept']}")

    from domain.notes.tasks.catalog.steps.catalog_agent import _reorder_by_source_order
    from domain.notes.tasks.catalog.skeleton import skeleton_position_map

    shuffled = copy.deepcopy(restored)
    for chapter in shuffled["chapters"]:
        chapter["topics"] = list(reversed(chapter.get("topics") or []))
        for topic in chapter["topics"]:
            topic["knowledge_points"] = list(reversed(topic.get("knowledge_points") or []))
    ordered = _reorder_by_source_order(shuffled, skeleton_position_map(skeleton))
    final = coverage.evaluate(skeleton, ordered)
    check("同级保序：章/主题/KP 顺序回到原文顺序",
          final["ok"] and not final["level_violations"],
          f"violations={final['level_violations'][:2]}")


_CONTENT_MD = """<!-- ocr-pages: 1-2 -->
### 一维半无限深方势阱

势函数在有限高度处截断，分区求解后匹配边界条件，能量本征值离散。

<!-- ocr-pages: 3-4 -->
### 补充：坐标系变换

直角坐标与球坐标的度规不同，梯度算子要随之改写，便于后续计算。
"""


def test_catalog_taxonomy() -> None:
    """内容词表：**按形态判定 + 单一来源 + 可配置**（不枚举见过的具体名字）。"""
    from domain.notes.tasks.catalog import taxonomy

    check("占位名按形态判定（覆盖同类，而非枚举见过的名字）",
          taxonomy.is_placeholder_name("核心知识点")
          and taxonomy.is_placeholder_name("知识内容")
          and taxonomy.is_placeholder_name("要点")
          and taxonomy.is_placeholder_name("补充说明")
          and not taxonomy.is_placeholder_name("一维半无限深方势阱")
          and not taxonomy.is_placeholder_name("角向方程的求解"),
          "形态正则未按预期工作")
    check("辅助性内容词表判定",
          taxonomy.is_item_heading("例题 1")
          and taxonomy.is_item_heading("易错点")
          and not taxonomy.is_item_heading("一维谐振子"),
          "细碎标题判定异常")
    check("细粒度点词表（用于降级进 items）",
          bool(taxonomy.fine_grain_re().search("适用条件"))
          and "适用条件" in taxonomy.fine_suffix_marks(),
          "细粒度点词表异常")

    os.environ["CATALOG_ITEM_MARKS"] = ""
    try:
        from domain.notes.tasks.catalog import taxonomy as fresh
        import importlib

        importlib.reload(fresh)
        off = not fresh.is_item_heading("例题 1")
    finally:
        os.environ.pop("CATALOG_ITEM_MARKS", None)
        import importlib

        importlib.reload(taxonomy)
    check("词表可用 .env 关闭（CATALOG_ITEM_MARKS=）", off, "env 覆盖未生效")

    import domain.notes.tasks.catalog.prompts as prompts_mod
    importlib.reload(prompts_mod)
    prompt = prompts_mod.CATALOG_GENERATION_SYSTEM_PROMPT
    check("prompt 的类别说明与代码同源（无硬编码副本、无残留占位符）",
          "{item}" not in prompt and "{title}" not in prompt
          and taxonomy.item_marks()[0] in prompt,
          "prompt 词表未同源")


def test_checklist_graph_layers() -> None:
    """图谱分层与交互（零 LLM）：三层复合簇、边分型、前端标记、**不丢内容**。

    盯的是这次的真实状况：43 节点 / 0 边 / 43 孤立 / 力导向一次性铺满（用户看到的
    "太杂太乱、全是分离的知识点"）。修法：层次用复合簇表达 + 结构边就地推导（不依赖重跑）
    + 视图/过滤/搜索/就地展开 + 折叠只是"没画"（计数可见、随时可切全量）。
    """
    import collections

    from domain.notes.tasks.checklist.display import _graph_payload

    def card(index: int, name: str, chapter: str, topic: str, grade: str) -> dict:
        return {
            "id": f"kp_{index:03d}", "name": name, "chapter": chapter, "topic": topic,
            "session_priority": grade, "importance": "3",
            "key_facts": [f"{name}的要点"], "explain": f"{name}的定义与边界。",
            "prerequisites": [f"点{index - 1}"] if 1 < index < 5 else [],
            "related_points": [{"name": "点2", "relation": "used_with"}] if index == 1 else [],
        }

    cards = [
        card(1, "点1", "章一", "主题甲", "S"),
        card(2, "点2", "章一", "主题甲", "A"),
        card(3, "点3", "章一", "主题乙", "B"),
        card(4, "点4", "章二", "主题丙", "C"),
        card(5, "点5", "章三", "主题丁", "B"),
    ]
    nodes, edges = _graph_payload(cards)
    kinds = collections.Counter(n["kind"] for n in nodes)
    check("图谱三层：章 / 主题 / 知识点",
          kinds["chapter"] == 3 and kinds["topic"] == 4 and kinds["kp"] == len(cards),
          f"kinds={dict(kinds)}")
    kps = [n for n in nodes if n["kind"] == "kp"]
    check("每个知识点都挂在主题簇下（复合簇覆盖 100%）",
          all(n.get("parent") for n in kps)
          and all(str(n["parent"]).startswith("cluster-tp-") for n in kps),
          f"parents={[n.get('parent') for n in kps]}")
    check("孤立知识点被标 leaf（供折叠/低调显示，不删除）",
          any(n["tier"] == "leaf" for n in kps)
          and all(n["kind"] == "kp" for n in nodes if n.get("tier")),
          f"tiers={[n['tier'] for n in kps]}")
    check("簇节点带子节点计数（概览视图的标签来源）",
          all(n.get("count") for n in nodes if n["kind"] == "topic"),
          f"counts={[n.get('count') for n in nodes if n['kind'] == 'topic']}")
    types = collections.Counter(e["type"] for e in edges)
    check("边分型：语义边 + 结构边（结构边就地推导，老目录也有骨架）",
          types["prerequisite"] >= 1 and types["related"] >= 1
          and types["same_topic"] >= 1 and types["order"] >= 1,
          f"types={dict(types)}")
    check("度数/层级由程序算（供默认可见性与折叠）",
          all("degree" in n and n["tier"] in {"hub", "normal", "leaf"} for n in kps)
          and any(n["tier"] == "leaf" for n in kps),
          f"tiers={[n['tier'] for n in kps]}")
    check("节点带卡片锚点（侧栏可跳回清单）",
          all(n.get("kp_id") for n in kps), f"kp_ids={[n.get('kp_id') for n in kps]}")

    from domain.notes.tasks.checklist.display import build_checklist_html

    html = build_checklist_html({"course": "测试", "cards": cards}, has_teacher=False)
    for marker in ("lc-kg-views", "lc-kg-grades", "lc-kg-search", "lc-kg-count",
                   "lc-kg-structure", "lc-kg-state-v1", "breadthfirst", "在清单中定位"):
        check(f"图谱组件含 {marker}", marker in html, "缺少该标记")
    anchors = set(re.findall(r'id="ck-card-([^"]*)"', html))
    named = {str(c["id"]) for c in cards if str(c["name"]) in html}
    check("**不丢内容**：每张卡片都能定位（卡片锚点，或至少在导航表里可见）",
          {str(c["id"]) for c in cards} <= (anchors | named),
          f"锚点={sorted(anchors)} 导航表可见={sorted(named - anchors)}")
    check("渲染成卡片的（核心/重点/简要）全部带锚点",
          {str(c["id"]) for c in cards if str(c.get("session_priority")) in {"S", "A", "B"}}
          <= anchors,
          f"锚点={sorted(anchors)}")


async def test_checklist_batching() -> None:
    """D1/D2/D3（零 LLM）：切批并行、动态输出预算、字段预算按档位。

    盯的是这次的真实故障：43 张 S/A 卡一次请求 → 20k-36k tokens 远超单次上限 →
    截断 → 减半重试 → 串行两轮 3 分 14 秒。修法是"切批 + 并行 + 动态预算"，
    **不是**压缩卡片数量（覆盖是产品承诺，卡集合始终等于激活集合）。
    """
    import asyncio

    from domain.notes.tasks.checklist.steps import checklist_agent as agent_mod

    rows_s = [{"id": f"kp_{i:03d}", "session_priority": "S"} for i in range(43)]
    batches = agent_mod._chunk(rows_s, agent_mod.batch_size())
    check("D1 大目录切成多批（不再一次全量请求）",
          agent_mod.batch_size() >= 5 and len(batches) == -(-43 // agent_mod.batch_size()) and len(batches) > 1,
          f"batch_size={agent_mod.batch_size()} batches={len(batches)}")
    check("D1 每批容量按输出预算可控（S 档 ≤ 10 张）",
          all(len(b) <= 10 for b in batches), f"批大小={[len(b) for b in batches]}")

    budget_s = agent_mod._batch_token_budget([{"session_priority": "S"}] * 9)
    budget_a = agent_mod._batch_token_budget([{"session_priority": "A"}] * 9)
    budget_one = agent_mod._batch_token_budget([{"session_priority": "S"}])
    check("D2 动态输出预算：随批内档位/卡数变化，且有上下限保护",
          1200 <= budget_one <= budget_s <= 16000 and budget_a < budget_s,
          f"S9={budget_s} A9={budget_a} S1={budget_one}")

    # 并发：所有批同时发起（墙钟 ≈ 单批），而不是串行轮次
    started: list[int] = []

    class FakeClient:
        async def structured(self, *_a, **_k):
            started.append(len(started))
            await asyncio.sleep(0.2)
            raise RuntimeError("boom")  # 单批失败 → 该批交程序兜底

    class FakeAgent(agent_mod.ChecklistAgent):
        pass

    agent = FakeAgent(FakeClient())
    original_load = agent_mod.load_session
    original_brief = agent_mod.build_checklist_briefing
    agent_mod.load_session = lambda _ctx: (
        {"course": "c", "version": "1", "chapters": []},
        [{"id": f"kp_{i:03d}", "name": f"点{i}", "session_priority": "S"} for i in range(18)],
        "",
    )
    agent_mod.build_checklist_briefing = lambda *_a, **_k: "brief"
    try:
        started.clear()
        import time as _time

        t0 = _time.monotonic()
        await agent.run("ctx")
        elapsed = _time.monotonic() - t0
    finally:
        agent_mod.load_session = original_load
        agent_mod.build_checklist_briefing = original_brief
    check("D1 批次并行发起（墙钟 ≈ 单批，而非批数 × 单批）",
          len(started) >= 2 and elapsed < 0.2 * len(started),
          f"批数={len(started)} 用时={elapsed:.2f}s（串行需 {0.2 * max(1, len(started)):.2f}s）")


def test_catalog_relations_and_grade_spread() -> None:
    """P6 零 LLM 保底：关系回填让图谱有边、importance 不再塌成常量、分档不再全挤 S。

    这三者是一条因果链（关系空 → 结构分恒定 → importance 单值 → `_quantile_assign`
    同分并档吞档 → 43/43 全 S → 模型要写 43 张卡 → 截断重试 3 分钟），所以一条护栏一起盯。
    """
    import collections

    import domain.notes.tasks.catalog.gather as gather
    from domain.notes.tasks.checklist.select import _quantile_assign

    draft = {
        "course": "wuli",
        "chapters": [
            {
                "id": "ch_001",
                "name": "章一",
                "topics": [
                    {
                        "id": "tp_001",
                        "name": "主题一",
                        "knowledge_points": [
                            {"id": "kp_001", "name": "点一", "importance": "3",
                             "knowledge_items": ["a", "b", "c"], "knowledge_type": "formula"},
                            {"id": "kp_002", "name": "点二", "importance": "3",
                             "knowledge_items": ["a", "b", "c"], "knowledge_type": "concept"},
                        ],
                    },
                    {
                        "id": "tp_002",
                        "name": "主题二",
                        "knowledge_points": [
                            {"id": "kp_003", "name": "点三", "importance": "3",
                             "knowledge_items": ["a", "b", "c"], "knowledge_type": "concept"},
                            {"id": "kp_004", "name": "点四", "importance": "3",
                             "knowledge_items": ["a", "b", "c"], "knowledge_type": "method"},
                        ],
                    },
                ],
            }
        ],
    }
    original = gather.open_knowledge
    gather.open_knowledge = lambda user_id="": None  # 共现边拿不到也应保底前两类
    ctx = "【用户ID】u" + chr(10) + "【学科/课程】wuli" + chr(10)
    try:
        filled, stats = gather.backfill_catalog_relations(draft, ctx)
    finally:
        gather.open_knowledge = original
    kps = [k for ch in filled["chapters"] for tp in ch["topics"] for k in tp["knowledge_points"]]
    check("A 关系程序保底：同主题互连 + 章内主题链",
          stats["same_topic"] >= 2 and stats["topic_chain"] == 1
          and all(k.get("related_points") or k.get("prerequisites") for k in kps),
          f"stats={stats}")
    check("A 关系不产自指、条目带 origin=program",
          all(
              str(r.get("name")) != str(k.get("name"))
              for k in kps for r in (k.get("related_points") or [])
          )
          and all(
              r.get("origin") == "program"
              for k in kps for r in (k.get("related_points") or [])
          ),
          f"related={[k.get('related_points') for k in kps][:2]}")
    check("A 关系有上限（防膨胀）",
          all(len(k.get("related_points") or []) <= gather._RELATIONS_PER_KP
              and len(k.get("prerequisites") or []) <= gather._PREREQ_PER_KP for k in kps),
          f"counts={[len(k.get('related_points') or []) for k in kps]}")

    # B：importance 分布护栏（同分塌陷时按结构分微调，且不越既有边界）
    uniform = copy.deepcopy(filled)
    for chapter in uniform["chapters"]:
        for topic in chapter["topics"]:
            for kp in topic["knowledge_points"]:
                kp["importance"] = "3"
    gather.compute_catalog_signals(uniform)
    spread = {str(k.get("importance")) for ch in uniform["chapters"] for tp in ch["topics"]
              for k in tp["knowledge_points"]}
    check("B importance 不再塌成常量（分布护栏生效）",
          len(spread) >= 2 and all(int(v) >= 3 for v in spread),
          f"取值={sorted(spread)}（items≥3 的边界规则同时生效）")

    # C：分档防退化 —— 全员同分时不得全挤进 S 档
    rows = [{"id": f"kp_{i:03d}", "name": f"点{i}", "_score": 36, "importance": "3"}
            for i in range(43)]
    _quantile_assign(rows)
    dist = collections.Counter(str(r.get("session_priority")) for r in rows)
    check("C 全员同分也不再全进 S 档（同分并档受限）",
          dist.get("S", 0) < len(rows) * 0.4 and len(dist) >= 2,
          f"分布={dict(dist)}")
    check("C 档位分布指标可读（result.md 里的哨兵）",
          "核心" in __import__(
              "domain.notes.tasks.checklist.display", fromlist=["x"]
          ).grade_distribution_text(rows),
          "分布文本生成失败")


def test_catalog_content_check() -> None:
    """第三道校验：条目是否有依据（逐字/概述型/串门/编造），以及 monitor 摘要形态。"""
    from domain.notes.tasks.catalog.skeleton import (
        catalog_quality_report,
        parse_md_skeleton,
        verify_catalog_content,
    )

    skeleton = parse_md_skeleton(_CONTENT_MD, source="ocr_selftest.md")
    draft = {
        "chapters": [
            {
                "id": "ch_001",
                "name": "量子力学基础",
                "topics": [
                    {
                        "id": "tp_001",
                        "name": "一维半无限深方势阱",
                        "knowledge_points": [
                            {
                                "id": "kp_001",
                                "name": "一维半无限深方势阱",
                                "knowledge_items": [
                                    "分区求解",                                  # 本节逐字命中
                                    "梯度算子要随之改写",                          # 别节逐字命中（串门）
                                    "球坐标的度规不同",                            # 同上，凑够 2 条判节点级串门
                                    "由基态波函数可直接推出海森堡不确定关系的下界",     # 长条目全篇无依据
                                    "能量离散",                                  # 短标签，无法逐字核对
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    report = verify_catalog_content(draft, skeleton)
    check("item 数与分类计数一致",
          report["checked"] == 5
          and report["strong"] == 1 and report["labels"] == 1,
          f"checked={report['checked']} strong={report['strong']} labels={report['labels']}")
    check("整节串门被判出（多数条目更像另一节）",
          len(report["misplaced_nodes"]) == 1
          and "补充" in report["misplaced_nodes"][0]["belongs_to"]
          and report["misplaced_nodes"][0]["items"] == 2,
          f"misplaced={report['misplaced_nodes']}")
    check("长条目全篇无依据 → 存疑（短标签不误报）",
          len(report["unverified"]) == 1
          and "海森堡" in report["unverified"][0]["item"],
          f"unverified={report['unverified']}")
    quality = catalog_quality_report(skeleton, draft)
    metrics = quality["metrics"]
    check("monitor 摘要字段齐全（一行式验收）",
          {"coverage", "order_violations", "restored", "complemented",
           "misplaced_nodes", "unverified_items"} <= set(metrics),
          f"metrics={metrics}")
    check("体检不改动目录（只读）",
          draft["chapters"][0]["topics"][0]["knowledge_points"][0]["knowledge_items"][0]
          == "分区求解")


# ── P4：编号标题识别 + 补缺不越骨架 + 不再产占位名 ──────────────

def test_heading_number_rules() -> None:
    """不需要知识库：NFKC 会把 `③ …` 变成 `3 …`，这类"数字+空格"不能再当标题。"""
    from tools.knowledge.source_role import heading_level

    rejected = [
        "3 分子在两次碰撞间做匀速直线运动",          # ← 曾经被当成章级标题（正文列表项）
        "1 可不计分子本身的大小",
        "2 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略",
    ]
    check("数字 + 空格不再算标题（NFKC 伪标题被拦）",
          all(heading_level(line) is None for line in rejected),
          f"结果={[heading_level(x) for x in rejected]}")

    accepted = {
        "1. 幂级数解法": (1, "幂级数解法"),
        "1、幂级数解法": (1, "幂级数解法"),
        "1) 幂级数解法": (1, "幂级数解法"),
        "（1）幂级数解法": (1, "幂级数解法"),
        "1.2 球坐标": (2, "球坐标"),
        "第3章 氢原子": (1, "氢原子"),
        "## 概率密度角度分布": (2, "概率密度角度分布"),
    }
    got = {k: heading_level(k) for k in accepted}
    check("带标点/带点编号/章节的标题照常识别",
          got == accepted, f"结果={got}")
    check("句末带标点的编号行仍判正文",
          heading_level("3. 这是正文行。") is None)

    os.environ["HEADING_NUM_LOOSE"] = "1"
    loose = heading_level("3 分子在两次碰撞间做匀速直线运动")
    os.environ.pop("HEADING_NUM_LOOSE", None)
    check("HEADING_NUM_LOOSE=1 可回退旧行为", loose == (1, "分子在两次碰撞间做匀速直线运动"),
          f"loose={loose}")


def test_complement_respects_skeleton() -> None:
    """有骨架时补缺必须让位；无骨架时补缺也只能用真名，不得生产占位名。"""
    from pathlib import Path as _Path

    import domain.notes.tasks.catalog.gather as gather
    import domain.notes.tasks.catalog.skeleton as skeleton_mod

    scratch = _Path(__file__).resolve().parents[1] / "data" / "__selftest__" / "ocr" / "wuli"
    scratch.mkdir(parents=True, exist_ok=True)
    md = scratch / "ocr_selftest.md"
    md.write_text(_SKELETON_MD, encoding="utf-8")

    rows = [
        {  # 章级候选：旧行为会给它造"章 + 核心知识点 + 同名 KP"的空壳
            "source": md.name, "chapter": "分子运动模型", "topic": "", "heading": "分子运动模型",
            "heading_path_text": "分子运动模型", "page": "", "chunk_index": "0-0",
            "heading_score": "6", "heading_kind": "chapter", "content_tags": "",
            "contains_formula": "0", "role": "notes",
        },
        {  # 主题级候选：应补成"真名章 / 真名主题"，不引入占位名
            "source": md.name, "chapter": "速度分布", "topic": "麦克斯韦速率分布",
            "heading": "麦克斯韦速率分布", "heading_path_text": "速度分布 / 麦克斯韦速率分布",
            "page": "", "chunk_index": "1-0", "heading_score": "6", "heading_kind": "topic",
            "content_tags": "", "contains_formula": "0", "role": "notes",
        },
    ]
    ctx = "【用户ID】__selftest__\n【学科/课程】wuli\n"
    draft = {"chapters": [{"id": "ch_001", "name": "已有章",
                          "topics": [{"id": "tp_001", "name": "已有主题",
                                      "knowledge_points": [{"id": "kp_001", "name": "已有KP"}]}]}]}
    original_kb = gather.open_knowledge
    original_build = skeleton_mod.build_source_skeleton
    gather.open_knowledge = lambda user_id="": _FakeKB(rows)
    try:
        after = gather.complement_catalog_coverage(copy.deepcopy(draft), ctx)
        check("有骨架时补缺不改目录（骨架权威）",
              json.dumps(after, ensure_ascii=False, sort_keys=True)
              == json.dumps(draft, ensure_ascii=False, sort_keys=True),
              f"chapters={len(after.get('chapters') or [])}")
        check("骨架存在时不再补出骨架外章",
              [c.get("name") for c in after.get("chapters") or []] == ["已有章"],
              f"章={[c.get('name') for c in after.get('chapters') or []]}")

        # 打桩成"无骨架"，让旧的候选池补缺真正跑起来，验证它只用真名
        skeleton_mod.build_source_skeleton = lambda _ctx: {"topics": []}
        filled = gather.complement_catalog_coverage(copy.deepcopy(draft), ctx)
        names = [
            str(node.get("name"))
            for chapter in filled.get("chapters") or []
            for node in [chapter] + list(chapter.get("topics") or [])
            + [kp for tp in chapter.get("topics") or []
               for kp in tp.get("knowledge_points") or []]
        ]
        check("无骨架时补缺用真名（章级候选跳过，不造占位名）",
              "麦克斯韦速率分布" in names
              and "分子运动模型" not in names  # 章级候选要配同名主题 → 直接跳过
              and not any(n in {"核心知识点", "核心概念", "知识概要", "补充知识点", "其他"}
                          for n in names),
              f"names={names}")
    finally:
        gather.open_knowledge = original_kb
        skeleton_mod.build_source_skeleton = original_build
        md.unlink(missing_ok=True)
        for folder in (scratch, scratch.parent, scratch.parent.parent, scratch.parent.parent.parent):
            try:
                folder.rmdir()
            except OSError:
                pass

    # 还原侧同样不产占位名：骨架主题没有子标题时，交给结构修复器用真名回退补点
    from domain.notes.tasks.catalog.skeleton import parse_md_skeleton, restore_from_skeleton

    bare = parse_md_skeleton(
        "<!-- ocr-pages: 1 -->\n### 只有正文的一节\n\n这一节只有正文，没有任何子标题。\n",
        source="ocr_selftest.md",
    )
    restored, report = restore_from_skeleton({"chapters": [{"id": "ch_001", "name": "章",
                                                           "topics": []}]}, bare)
    names = [
        str(kp.get("name"))
        for ch in restored.get("chapters") or []
        for tp in ch.get("topics") or []
        for kp in tp.get("knowledge_points") or []
    ]
    check("还原不造占位名（留给修复器用真名补点）",
          report["restored_topics"] and "核心知识点" not in names,
          f"补齐={report['restored_topics']} names={names}")


# ── 图片 OCR：并发但不许乱序（笔记图片本身有先后）──────────────

def test_ocr_order() -> None:
    """不需要 Redis / OCR / 模型：并发识别后按 ``docs`` 顺序拼接，且跨页页眉不进重构输入。

    用不同延时的桩让"完成顺序"与"传入顺序"相反，验证仍按传入顺序输出
    （``ThreadPoolExecutor.map`` 而非 ``as_completed`` 的意义）；三页共用一个顶部页眉，
    验证跨页去噪把它标成 boilerplate 后不会被送进 LLM 重构。
    """
    from pathlib import Path as _Path

    import tools.ocr.layout as layout_mod
    import tools.ocr.reconstruct as recon_mod
    from app import tasks as tasks_mod

    delays = {"p1.jpg": 0.6, "p2.jpg": 0.05, "p3.jpg": 0.2}
    header = {"text": "华中科技大学", "conf": 0.9,
              "bbox": [[10, 10], [300, 10], [300, 40], [10, 40]]}

    def body_line(name: str) -> dict:
        return {"text": f"# {name}", "conf": 0.9,
                "bbox": [[10, 300], [300, 300], [300, 340], [10, 340]]}

    sent_to_llm: list[list[dict]] = []

    def fake_lines(path):
        name = _Path(path).name
        time.sleep(delays.get(name, 0))
        return [dict(header), body_line(name)]

    def fake_reconstruct(lines):
        sent_to_llm.append([dict(item) for item in lines])
        return "\n".join(str(item.get("text") or "") for item in lines)

    original = (layout_mod.ocr_image_lines, recon_mod.reconstruct_markdown, tasks_mod._input_file)
    try:
        layout_mod.ocr_image_lines = fake_lines
        recon_mod.reconstruct_markdown = fake_reconstruct
        tasks_mod._input_file = lambda user_id, kind, name: _Path(name)   # 免落盘
        out = tasks_mod._ocr_docs("u", ["p1.jpg", "p2.jpg", "p3.jpg"])
    finally:
        layout_mod.ocr_image_lines, recon_mod.reconstruct_markdown, tasks_mod._input_file = original

    got = [line[2:] for line in out.splitlines() if line.startswith("# ")]
    check("并发 OCR 按 docs 顺序拼接（最慢的第 1 张仍排最前）",
          got == ["p1.jpg", "p2.jpg", "p3.jpg"], f"顺序={got}")
    marked = [
        item
        for lines in sent_to_llm
        for item in lines
        if str(item.get("text")) == "华中科技大学"
    ]
    check("跨页页眉被标成 boilerplate（每页都出现 + 顶部边缘带）",
          bool(marked) and all(item.get("role_hint") == "boilerplate" for item in marked),
          f"标记数={len(marked)} role={[i.get('role_hint') for i in marked][:3]}")
    check("一次性正文行不被误标",
          all(
              str(item.get("text")) != f"# {name}" or item.get("role_hint") != "boilerplate"
              for lines in sent_to_llm
              for item in lines
              for name in ("p1.jpg", "p2.jpg", "p3.jpg")
          ))
    # 真实重构器会跳过 boilerplate 行（用自己的实现验证，不依赖桩）
    from tools.ocr.reconstruct import _fragments_to_text

    check("真实重构器跳过 boilerplate 行",
          "华中科技大学" not in _fragments_to_text(
              [{"text": "华中科技大学", "role_hint": "boilerplate"}, {"text": "# 正文"}]
          ))


# ── 页眉/页脚逐图自适应：印刷校名/地址/页号不得进正文 ─────────────

def _chrome_fixture(header: list[tuple[str, int, int]], body: list[tuple[str, int]],
                    footer: list[tuple[str, int]] | None = None) -> list[dict]:
    """按实测几何生成一页的行框：页面 2600×4000，正文行高 67 → 中位行高 67。

    header 为 (文本, 行高px, 顶边y)：真实照片里校名大字水印与小字块**纵向重叠**，
    故顶部各行用显式顶边（整簇压在本图上方 12% 内），不能按顺序累加排布。
    """
    rows: list[dict] = []
    for text, height, top in header:
        rows.append({"text": text, "bbox": [[250, top], [2350, top], [2350, top + height], [250, top + height]]})
    y = 450.0
    for text, height in body:
        rows.append({"text": text, "bbox": [[300, y], [2400, y], [2400, y + height], [300, y + height]]})
        y += height + 60
    foot = list(footer or [])
    y = 4000.0
    for text, height in reversed(foot):
        y -= height
        rows.append({"text": text, "bbox": [[250, y], [2350, y], [2350, y + height], [250, y + height]]})
        y -= 12
    return rows


def test_page_chrome() -> None:
    """不需要 OCR / 模型：页眉页脚按**本图自身中位行高**自适应判定。

    夹具数值取自真实笔记照片实测：某图页眉「科技大」行高 138px = 中位行高 67px 的
    2.07 倍、「華中」2.26 倍，而正文标题「算符」1.17 倍、正文 1.00 倍；页脚是印刷页号
    与「华中科技大学附属印刷厂」。固定坐标阈值抓不到这些（每张照片位置/字号都不同），
    故用本图中位行高当标尺。
    """
    from tools.ocr import layout as layout_mod
    from tools.ocr.layout import _infer_layout_hints, _mark_page_chrome
    from tools.ocr.reconstruct import _fragments_to_text

    body = [
        ("算符", 78),
        ("狄拉克符号", 67),
        ("[4>：右矢；<y1：左矢，称14>或<y为态矢，Y是一个标签，用于区分不同的量子态", 67),
    ] + [(f"正文第{i}行，讲厄米算符与对易关系，属于量子力学基础内容。", 67) for i in range(18)] + [
        ("基矢与本征方程", 67),
        ("能量本征方程：H14k>=Ek14k7，将14k>简记为1k>(为基矢)，量子数k标记系统所有量子数", 67),
    ]
    page15 = _chrome_fixture(
        header=[
            ("科技大", 138, 60),
            ("華中", 151, 70),
            ("明德早学水是创部", 32, 80),
            ("AND", 53, 125),
            ("YOFSCIENCE", 62, 190),
            ("HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY", 60, 260),
            ("Wuhan430074,Hubei,P.R.China 中·武汉 Tel:(027)8754", 54, 330),
        ],
        body=body,
        footer=[("1701572", 40), ("第", 50), ("页", 50), ("华中科技大学附属印刷厂", 60), ("69441921702325", 40)],
    )
    rows = _infer_layout_hints([dict(r) for r in page15], (2600, 4000))
    marked = _mark_page_chrome(rows)
    by_text = {str(r.get("text")): r for r in rows}
    dropped = [t for t, r in by_text.items() if r.get("role_hint") == "boilerplate" and r.get("chrome_zone")]
    check("页眉大字被逐图标定丢弃（校名残识别 科技大 / 華中）",
          {"科技大", "華中"} <= set(dropped), f"drop={dropped}")
    check("页眉英文与地址行一并丢弃",
          any("HUAZHONG" in t for t in dropped) and any("Tel" in t for t in dropped), f"drop={dropped}")
    check("页脚印刷页号与印刷厂名丢弃",
          {"第", "页", "华中科技大学附属印刷厂"} <= set(dropped), f"drop={dropped}")
    check("正文起点及其后内容不被误杀",
          all(by_text[t].get("role_hint") != "boilerplate" for t in ("算符", "狄拉克符号", "基矢与本征方程")),
          f"算符={by_text['算符'].get('role_hint')}")
    check("只丢页眉页脚，不碰正文",
          marked == 7 + 5 and len(rows) - marked == len(body), f"marked={marked} rows={len(rows)}")
    text = _fragments_to_text([dict(r) for r in rows])
    check("重构输入里不再出现页眉页脚残留",
          not any(token in text for token in ("科技大", "華中", "HUAZHONG", "Tel", "印刷厂", "P.R.China")),
          f"残留={[t for t in ('科技大', '華中', 'HUAZHONG', 'Tel', '印刷厂') if t in text]}")
    check("重构输入保留正文内容",
          all(token in text for token in ("算符", "基矢与本征方程", "能量本征方程")), f"len={len(text)}")

    # 另一张实测图：页眉 4 行，正文首行是「③角动量的对易式」
    page16 = _chrome_fixture(
        header=[
            ("華中科技大学", 151, 60),
            ("YOFSCIENCE", 62, 150),
            ("HUAZHONGUNIVERSITYOFSCIENCEANDTECHNOLOGY", 60, 230),
            ("Wuhan430074,Hubei,P.R.China 中·汉 Tel:（027)", 54, 300),
        ],
        body=[("③角动量的对易式", 67)] + [(f"对易关系第{i}式，[A,B]=AB-BA，属厄米算符章节。", 67) for i in range(20)],
        footer=[("第", 50), ("1701572", 40), ("华中科技大学附属印刷厂", 60), ("页", 50)],
    )
    rows16 = _infer_layout_hints([dict(r) for r in page16], (2600, 4000))
    marked16 = _mark_page_chrome(rows16)
    first16 = [str(r.get("text")) for r in rows16 if r.get("role_hint") != "boilerplate"][:2]
    check("页眉 4 行全丢且正文首行形态保留",
          marked16 == 4 + 4 and first16 and first16[0] == "③角动量的对易式", f"marked={marked16} first={first16}")

    # 反例一：没有页眉的页，第一行就是正文 → 一行都不许丢
    plain = _chrome_fixture(
        header=[],
        body=[("一维束缚态", 78), ("定态薛定谔方程与边界条件，本征能量取分立值。", 67)]
        + [(f"推导第{i}步，代入波函数并除以ψ（x）。", 67) for i in range(20)],
    )
    rows_plain = _infer_layout_hints([dict(r) for r in plain], (2600, 4000))
    check("无页眉的页：首行是正文 → 零丢弃", _mark_page_chrome(rows_plain) == 0)

    # 反例二：顶部有短行但无任何强特征（单字/极小字号）→ 宁可保留
    weak = _chrome_fixture(
        header=[("y", 30, 60), ("e", 30, 100)],
        body=[(f"正文第{i}行，讨论角动量与自旋的耦合。", 67) for i in range(22)],
    )
    rows_weak = _infer_layout_hints([dict(r) for r in weak], (2600, 4000))
    check("顶部短行无强特征 → 不丢（宁漏不误杀）", _mark_page_chrome(rows_weak) == 0)

    # 反向开关：线上发现误杀可一键回退
    os.environ["OCR_PAGE_CHROME"] = "0"
    switch_off = not layout_mod._page_chrome_enabled()
    os.environ.pop("OCR_PAGE_CHROME", None)
    check("OCR_PAGE_CHROME=0 可整体回退", switch_off and layout_mod._page_chrome_enabled())


# ── OCR 文本收尾：删模型自述的报错串，不动正常内容 ─────────────

def test_ocr_noise_strip() -> None:
    """不需要 OCR / 模型：渲染器报错串要删掉，正常内容与公式规范化不受影响。"""
    from tools.ocr.mathmd import normalize_markdown_math, strip_program_noise

    sample = (
        "²θL ParseError: KaTeX parse error: Expected '}', got 'EOF' at end of input: "
        "∂^{2 角向方程：sinθ(sinθr8) 80 )+5m{$"
    )
    out = normalize_markdown_math(sample)
    check("模型抄进正文的 KaTeX 报错被删除",
          "ParseError" not in out and "KaTeX" not in out and out.startswith("²θL"),
          f"结果={out!r}")

    out = normalize_markdown_math("（r）的推导\n\nParseError: KaTeX parse error: Undefined control sequence: frac\n\n见下页")
    check("整行是报错时整行删除且不留多余空行",
          "ParseError" not in out and "见下页" in out and "\n\n\n" not in out,
          f"结果={out!r}")

    out = normalize_markdown_math("Missing or unrecognized delimiter for \\right 后续内容保留")
    check("delimiter 报错被删且不吞后续正文",
          "unrecognized delimiter" not in out and "后续内容保留" in out, f"结果={out!r}")

    for text in ("本页公式用 KaTeX 渲染，定界用 $...$ 与 $$...$$。",
                 "示例：ParseError: unexpected token 表示解析失败。",
                 "# 标题\n\n正文一行，没有报错。"):
        check(f"不误删正常内容：{text[:14]}…", normalize_markdown_math(text) == text)

    check("定界符修复逻辑不受影响", normalize_markdown_math("行内 $a+b$ 与误写的 $c$$").startswith("行内 $a+b$"))
    check("strip_program_noise 可单独调用", strip_program_noise(sample).startswith("²θL"))


# ── 知识目录：顺序必须跟随原文（用户可见的语义）────────────────

def test_catalog_order() -> None:
    """不需要 Redis / 模型：目录章节/主题/KP 按原文位置排，未知位置排最后。"""
    from domain.notes.tasks.catalog.prompts import CATALOG_GENERATION_SYSTEM_PROMPT
    from domain.notes.tasks.catalog.steps.catalog_agent import _reorder_by_source_order

    position = {
        "表象变换与矩阵力学": 5,
        "厄米算符本征值与本征态的特性": 40,
        "守恒量与能级简并度": 80,
        "厄米算符本征值的实数性": 41,
    }
    draft = {
        "chapters": [
            {"name": "厄米算符本征值与本征态的特性", "topics": [
                {"name": "厄米算符本征值的实数性", "knowledge_points": [
                    {"name": "定理:厄米算符的平均值为实数"},
                    {"name": "厄米算符本征值的实数性"}]}]},
            {"name": "历史遗留章节", "topics": [
                {"name": "老知识点", "knowledge_points": [{"name": "老知识点"}]}]},
            {"name": "表象变换与矩阵力学", "topics": [
                {"name": "表象间的转化", "knowledge_points": [{"name": "表象间的转化"}]}]},
            {"name": "守恒量与能级简并度", "topics": [
                {"name": "守恒量", "knowledge_points": [{"name": "守恒量"}]}]},
        ]
    }
    out = _reorder_by_source_order(draft, position)
    chapters = [c["name"] for c in out["chapters"]]
    check("目录章节按原文位置排序",
          chapters == ["表象变换与矩阵力学", "厄米算符本征值与本征态的特性",
                       "守恒量与能级简并度", "历史遗留章节"],
          f"chapters={chapters}")
    points = [p["name"] for p in out["chapters"][1]["topics"][0]["knowledge_points"]]
    check("同主题内 KP 按原文位置排序",
          points == ["厄米算符本征值的实数性", "定理:厄米算符的平均值为实数"],
          f"points={points}")
    check("位置表为空时不改顺序", _reorder_by_source_order(draft, {}) == draft)
    check("提示词含顺序跟随原文的硬约束",
          "顺序跟随原文" in CATALOG_GENERATION_SYSTEM_PROMPT
          and "不得按重要性" in CATALOG_GENERATION_SYSTEM_PROMPT)

    from domain.notes.tasks.catalog.gather import _position_key
    keys = [(10, 2), (9, 5), (10, 1)]
    order = sorted(keys)
    check("位置键按页码优先比较", order == [(9, 5), (10, 1), (10, 2)], f"{order}")
    check("位置键解析不出页码时排最后",
          _position_key({"page": ""}) > _position_key({"page": "9"}))


def test_heading_level_normalize() -> None:
    """OCR 跨页标题层级归一（R1 同名同级别 / R2「（续）」容器）：只重写 `#`，正文不动。

    背景：级号是逐页按版面定的（页顶/居中/字高），合并后同一逻辑层会漂移
    （章标题在一页是 `#`、另一页是 `###`），骨架按"树深度"分层就会把主题当章，
    下游再补占位主题 `核心知识点`。这里把归一的契约钉住。
    """
    from tools.ocr.heading_levels import normalize_heading_levels

    # 真实形态（服务器合并稿的形态）：章/主题同级 + 「（续）」跨页 + 章节内的子标题；
    # 末尾补一个顶层章，保证文件是"三级文件"（span≥3）——与真实合并稿一致。
    raw = "\n".join([
        "### 一维束缚态",
        "正文一",
        "### 一维半无限深方势阱",
        "正文二",
        "## 一维束缚态（续）",
        "正文三",
        "## 一维谐振子",
        "正文四",
        "### 角向方程",
        "正文五",
        "## 一维束缚态（续）",
        "正文六",
        "### 分离变量法求解",
        "正文七",
        "# 氢原子",
        "正文八",
        "## 概率密度角度分布",
        "正文九",
        "### 径向分布函数",
        "正文十",
    ])
    fixed, stats = normalize_heading_levels(raw)
    rows = fixed.splitlines()

    def level_of(name: str) -> int:
        for row in rows:
            hit = re.match(r"^(#{1,6})\s+(.*)$", row)
            if hit and hit.group(2).strip() == name:
                return len(hit.group(1))
        return 0

    chapter = level_of("一维束缚态")
    cont = level_of("一维束缚态（续）")
    check("R1：同名与「（续）」统一级号", chapter == cont and chapter > 0,
          f"章={chapter} 续={cont}")
    check("R2：续写区间内的同级标题降为子级",
          level_of("一维半无限深方势阱") > chapter
          and level_of("一维谐振子") > chapter
          and level_of("分离变量法求解") > chapter,
          f"势阱={level_of('一维半无限深方势阱')} 谐振子={level_of('一维谐振子')} "
          f"分离变量={level_of('分离变量法求解')} 章={chapter}")
    check("R2：容器内部的子标题比容器再深一级",
          level_of("角向方程") > level_of("一维谐振子"),
          f"角向方程={level_of('角向方程')} 谐振子={level_of('一维谐振子')}")

    # 不变量：正文一字不动、标题不增不减、幂等
    body_before = [r for r in raw.splitlines() if not r.startswith("#")]
    body_after = [r for r in rows if not r.startswith("#")]
    check("归一不动正文", body_before == body_after)
    check("归一不增删标题",
          sum(1 for r in raw.splitlines() if r.startswith("#")) ==
          sum(1 for r in rows if r.startswith("#")))
    again, _ = normalize_heading_levels(fixed)
    check("归一幂等（跑两遍结果一致）", again == fixed)
    check("级号落在 1..6",
          all(1 <= len(re.match(r"^(#{1,6})", r).group(1)) <= 6
              for r in rows if r.startswith("#")))
    check("统计回报：同名 1 处、续写区间 1 处",
          stats["unified"] == 1 and stats["spans"] == 1, f"{stats}")

    # 归一之后骨架应把「一维束缚态」认成一章，其余为它的主题
    from domain.notes.tasks.catalog.skeleton import parse_md_skeleton

    sk = parse_md_skeleton(fixed, source="selftest.md")
    chapters = {ch.get("name"): [t.get("name") for t in ch.get("topics") or []]
                for ch in sk.get("chapters") or []}
    check("归一后：一维束缚态成章、假章消失",
          set(chapters) == {"一维束缚态", "氢原子"}
          and "一维半无限深方势阱" not in chapters
          and "一维谐振子" not in chapters,
          f"chapters={sorted(chapters)}")
    check("归一后：主题挂回该章",
          {"一维半无限深方势阱", "一维谐振子", "分离变量法求解"} <= set(chapters.get("一维束缚态") or []),
          f"topics={chapters.get('一维束缚态')}")

    # 无标题 / 单标题：原样返回，不做任何改动
    for text in ("", "只有正文。", "# 唯一标题"):
        same, _ = normalize_heading_levels(text)
        check(f"无层可归一时原样返回({text[:6] or '空'})", same == text)


def test_knowledge_user_isolation() -> None:
    """知识库/目录按用户隔离：空 user 直接报错，不得凭空建出无主目录。

    背景：``persist_dir_for_user("")`` 曾静默回退 ``data/knowledge/chromadb``，
    catalog 生成时把 briefing 当上下文（解析出空 user）就触发了它——chromadb 只要
    构造客户端就建目录，于是 data/ 下凭空多出无主空库。这里把"必须按用户"钉成契约。
    """
    from pathlib import Path

    from domain.notes.tasks.catalog.store import catalog_dir_for, load_catalog
    from tools.knowledge.cite import open_knowledge
    from tools.knowledge.config import (
        DEFAULT_PERSIST_DIR,
        PROJECT_ROOT,
        persist_dir_for_user,
    )

    repo = Path(PROJECT_ROOT)
    knowledge_dir = repo / "data" / "knowledge"
    had_knowledge = knowledge_dir.exists()

    def raises(fn, *args, **kwargs) -> bool:
        try:
            fn(*args, **kwargs)
        except Exception:
            return True
        return False

    check("空 user_id 的知识库目录解析被拒绝", raises(persist_dir_for_user, ""))
    check("空 user_id 的知识目录解析被拒绝", raises(catalog_dir_for, ""))
    check("空 user_id 读知识目录被拒绝", raises(load_catalog, "", "wuli"))
    # open_knowledge 自带 try/except：按空 user 开库会抛错并被它兜成 None（降级为"无知识库"），
    # 关键是**不建无主库**（下面统一校验 data/knowledge 是否新增）
    check("open_knowledge 空 user 降级为 None", open_knowledge(user_id="") is None)

    want = str(repo / "data" / "__selftest__" / "knowledge" / "chromadb")
    check("有 user 时知识库落 data/{user}/knowledge/chromadb",
          persist_dir_for_user("__selftest__") == want,
          persist_dir_for_user("__selftest__"))
    check("有 user 时知识目录落 data/{user}/knowledge/catalogs",
          catalog_dir_for("__selftest__").as_posix().endswith(
              "data/__selftest__/knowledge/catalogs"),
          catalog_dir_for("__selftest__").as_posix())

    # 单租户开关：显式配置环境变量时才允许统一库（否则上面已经报错）
    os.environ["KNOWLEDGE_PERSIST_DIR"] = DEFAULT_PERSIST_DIR
    try:
        check("显式配置 KNOWLEDGE_PERSIST_DIR 后允许统一库",
              persist_dir_for_user("") == DEFAULT_PERSIST_DIR)
    finally:
        os.environ.pop("KNOWLEDGE_PERSIST_DIR", None)

    # 回归：把当初的触发路径（briefing 当上下文）放回去，也不该再建无主目录。
    # 这里直接造一个"没有【用户ID】、只有学科"的 briefing 形态字符串，等价于当初的
    # build_catalog_briefing 输出；用真实 build_catalog_briefing 会按 __selftest__ 建库目录。
    from domain.notes.tasks.catalog.steps.catalog_agent import _restore_from_skeleton

    briefing_like = "【任务】生成或增量更新课程知识目录，不要写复习建议。\n【学科/课程】wuli\n"
    _restore_from_skeleton({"chapters": []}, briefing_like)
    check("骨架还原传错上下文也不再建 data/knowledge",
          had_knowledge == knowledge_dir.exists(), str(knowledge_dir))


async def main() -> int:
    test_routes()
    test_async_response_shape()
    test_ocr_order()
    test_page_chrome()
    test_ingest_position_axis()
    test_catalog_order_and_coverage()
    test_metadata_source_skeleton()
    test_skeleton_parse_and_contract()
    test_skeleton_restore_and_order()
    test_catalog_content_check()
    test_catalog_relations_and_grade_spread()
    await test_checklist_batching()
    test_checklist_graph_layers()
    test_catalog_taxonomy()
    test_heading_number_rules()
    test_complement_respects_skeleton()
    test_ocr_noise_strip()
    test_catalog_order()
    test_heading_level_normalize()
    test_knowledge_user_isolation()
    print()
    store = job_store()
    db = store.redis.connection_pool.connection_kwargs.get("db")
    if db == 0:
        print("拒绝在 0 号库运行队列自测（那里是真实任务数据）；请改用独立 DB，例如 5。")
        return 2
    print(f"自测目标 Redis：{os.environ['REDIS_URL']}（结束后清空该库）\n")
    await test_queue(store)
    print()
    await test_executor(store)
    store.redis.flushdb()
    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "，".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
