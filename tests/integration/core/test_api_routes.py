"""异步任务 API 路由集成测试。"""
from __future__ import annotations

import time
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.api.main import app


class _FakeJobStore:
    def __init__(self):
        self.jobs = {}
        self.events = {}
        self.payloads = {}
        self.queue = []
        self._next_id = 1000

    def ping(self):
        pass

    def new_job_id(self):
        self._next_id += 1
        return f"job_{self._next_id}"

    def create_job(self, *, job_id, request_id, user_id, domain, task):
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
        self.jobs[job_id] = payload
        self.events[job_id] = [{"type": "queued", "job_id": job_id, "request_id": request_id, "ts": now}]
        return payload

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def update_job(self, job_id, **fields):
        if job_id in self.jobs:
            self.jobs[job_id].update(fields)

    def append_event(self, job_id, event):
        ev = dict(event or {})
        ev.setdefault("ts", time.time())
        self.events.setdefault(job_id, []).append(ev)

    def events_since(self, job_id, cursor):
        return self.events.get(job_id, [])[cursor:]

    def set_payload(self, job_id, payload):
        self.payloads[job_id] = payload

    def get_payload(self, job_id):
        return self.payloads.get(job_id)

    def enqueue(self, job_id):
        self.queue.append(job_id)


def test_async_api_routes() -> None:
    """验证统一异步接口 /api/agent/v1/async（提交、状态、流式、结果）及历史 /api/v1/tasks 兼容。"""
    fake_store = _FakeJobStore()
    with patch("app.api.routes.tasks.job_store", return_value=fake_store), patch("app.api.routes.tasks.run_mode", return_value="queue"):
        client = TestClient(app)

        # 1. POST /api/agent/v1/async
        payload = {
            "domain": "meeting",
            "task": "minutes",
            "texts": {"transcript": "周宁：复盘开发进展。"},
            "memory": True,
            "extra": {"time": "2026-09-01"},
        }
        res_post = client.post("/api/agent/v1/async", json=payload, headers={"X-User-Id": "u_test", "X-Request-Id": "req_async_1"})
        assert res_post.status_code == 200
        data_post = res_post.json()
        job_id = data_post.get("job_id", "")
        assert bool(job_id)
        assert data_post.get("status") == "queued"
        assert job_id in fake_store.queue

        # 2. GET /api/agent/v1/async/{job_id} 状态轮询
        res_status = client.get(f"/api/agent/v1/async/{job_id}")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert data_status.get("text") is None
        assert data_status.get("job_id") == job_id

        # 3. GET /api/agent/v1/async/{job_id}/result (未完成时返回快照)
        res_res_queued = client.get(f"/api/agent/v1/async/{job_id}/result")
        assert res_res_queued.status_code == 200
        assert res_res_queued.json().get("text") is None

        # 模拟任务完成
        fake_store.update_job(
            job_id,
            status="succeeded",
            message="success",
            result={"data": {"text": "# 纪要内容", "file_name": "minutes.html"}, "monitor": {"token_usage": 120, "cost_time": 1.5}},
        )
        fake_store.append_event(job_id, {"type": "done", "job_id": job_id, "data": {"text": "# 纪要内容", "file_name": "minutes.html"}})

        # 4. GET /api/agent/v1/async/{job_id}/result (完成后返回正文与文件名)
        res_res_done = client.get(f"/api/agent/v1/async/{job_id}/result")
        assert res_res_done.status_code == 200
        data_res_done = res_res_done.json()
        assert data_res_done.get("text") == "# 纪要内容"
        assert data_res_done.get("file_name") == "minutes.html"

        # 5. GET /api/agent/v1/async/{job_id}/stream 事件流
        res_stream = client.get(f"/api/agent/v1/async/{job_id}/stream?cursor=0")
        assert res_stream.status_code == 200
        assert "queued" in res_stream.text and "done" in res_stream.text

        # 6. 兼容老路径 /api/v1/tasks
        res_leg_post = client.post("/api/v1/tasks", json=payload, headers={"X-User-Id": "u_test"})
        assert res_leg_post.status_code == 200
        leg_job_id = res_leg_post.json().get("job_id", "")
        res_leg_get = client.get(f"/api/v1/tasks/{leg_job_id}")
        assert res_leg_get.status_code == 200
        res_leg_res = client.get(f"/api/v1/tasks/{leg_job_id}/result")
        assert res_leg_res.status_code == 200

        # 7. 不存在 job_id 返回 404
        res_404 = client.get("/api/agent/v1/async/nonexistent_job_12345")
        assert res_404.status_code == 404
        assert res_404.json().get("code") == 404
