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


async def main() -> int:
    test_routes()
    test_async_response_shape()
    test_ocr_order()
    test_page_chrome()
    test_ocr_noise_strip()
    test_catalog_order()
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
