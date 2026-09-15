"""AgentFlow 自测：接口清单守卫 + 异步任务队列机制（队列 / 租约 / 回收 / 重试 / 停机）。

不调用模型、不联网（执行体用桩替换），秒级跑完::

    python -m app.selftest

安全约定：队列部分**只在独立 DB 上运行**，默认 5 号库，绝不动 0 号库里的真实任务数据；
可用 ``AGENTFLOW_SELFTEST_REDIS_URL`` 覆盖（DB 不能是 0）。接口清单守卫不需要 Redis。

端到端的 HTTP 链路（提交 / 状态 / 结果 / 事件流）请用 minutes_async_*.py 四个脚本验证。
"""
from __future__ import annotations

import asyncio
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


# ── 图片 OCR：并发但不许乱序（笔记图片本身有先后）──────────────

def test_ocr_order() -> None:
    """不需要 Redis / OCR / 模型：并发识别后必须按 ``docs`` 顺序拼接。

    用不同延时的桩让"完成顺序"与"传入顺序"相反，验证仍按传入顺序输出
    （用 ``ThreadPoolExecutor.map`` 而非 ``as_completed`` 的意义所在）。
    """
    from pathlib import Path as _Path

    import tools.ocr as ocr_mod
    from app import tasks as tasks_mod

    delays = {"p1.jpg": 0.6, "p2.jpg": 0.05, "p3.jpg": 0.2}
    had_ocr = hasattr(ocr_mod, "ocr_image_to_markdown")
    original_ocr = getattr(ocr_mod, "ocr_image_to_markdown", None)
    original_input = tasks_mod._input_file
    try:
        def fake_ocr(path):
            name = _Path(path).name
            time.sleep(delays.get(name, 0))
            return f"# {name}"

        ocr_mod.ocr_image_to_markdown = fake_ocr
        tasks_mod._input_file = lambda user_id, kind, name: _Path(name)   # 免落盘
        out = tasks_mod._ocr_docs("u", ["p1.jpg", "p2.jpg", "p3.jpg"])
    finally:
        tasks_mod._input_file = original_input
        if had_ocr:
            ocr_mod.ocr_image_to_markdown = original_ocr
        else:
            delattr(ocr_mod, "ocr_image_to_markdown")

    got = [line[2:] for line in out.splitlines() if line.startswith("# ")]
    check("并发 OCR 按 docs 顺序拼接（最慢的第 1 张仍排最前）",
          got == ["p1.jpg", "p2.jpg", "p3.jpg"], f"顺序={got}")


async def main() -> int:
    test_routes()
    test_async_response_shape()
    test_ocr_order()
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
