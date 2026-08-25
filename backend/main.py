# -*- coding: utf-8 -*-
"""backend —— AgentFlow 后端服务（FastAPI）。

把现有能力（意图识别 / 任务执行 / 对话）暴露成 HTTP API：
- POST /api/intent         一句话 → Plan（missing 驱动前端"请上传"）
- POST /api/tasks          按 plan 执行（multipart：plan JSON + 上传文件）
- GET  /api/tasks/{id}     任务状态轮询（长任务如目录/复习清单）
- GET  /api/tasks/{id}/output/{name}  产物下载
- POST /api/chat           对话（复用 chat.ChatAgent）
- GET  /api/health

启动：python -m backend.main（或 uvicorn backend.main:app）
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Windows 下 uvicorn 把 stdout 接到管道，runner 的中文日志 flush 会 OSError 22；
# 统一重配 utf-8，保证任务执行时日志/print 不炸。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from intent_agent import parse

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

from .executor import TaskRunner  # noqa: E402

app = FastAPI(title="AgentFlow Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_runner = TaskRunner(root=ROOT, uploads_dir=UPLOADS)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "agentflow-backend"}


@app.get("/api/perspectives")
async def api_perspectives() -> dict:
    """minutes_generation 可选视角：客观全员 + 公共职业模板（label 列表）。"""
    from tools.core.profiles import SHARED_PROFILE_DIR, SHARED_ROLE_DIR, list_profile_entries

    entries = list_profile_entries(SHARED_PROFILE_DIR) + list_profile_entries(SHARED_ROLE_DIR)
    return {
        "perspectives": [
            {"label": e["label"], "kind": e["kind"], "filename": e["filename"]}
            for e in entries
        ]
    }


@app.post("/api/intent")
async def api_intent(payload: dict) -> dict:
    text = str((payload or {}).get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    def _parse() -> dict:
        # parse() 内部用 asyncio.run，不能在 FastAPI 事件循环里直接调，放线程
        return parse(
            text,
            ctx_params={
                "user_id": str((payload or {}).get("user_id") or ""),
                "subject": str((payload or {}).get("subject") or ""),
                "project": str((payload or {}).get("project") or ""),
            },
        ).to_dict()

    data = await asyncio.to_thread(_parse)
    if not data["plan"]:
        raise HTTPException(status_code=422, detail=data.get("explanation") or "未能识别出任务")
    return data


@app.post("/api/tasks")
async def api_tasks(
    plan_json: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    try:
        plan = json.loads(plan_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"plan_json 不是合法 JSON：{exc}")
    if not isinstance(plan, dict) or not isinstance(plan.get("plan"), list):
        raise HTTPException(status_code=400, detail="plan 结构错误：需要 {plan: [...]}")

    task_id = _runner.submit(plan, files)
    return {"task_id": task_id, "status": "running"}


@app.get("/api/tasks/{task_id}")
async def api_task_status(task_id: str) -> dict:
    state = _runner.state(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return state


@app.get("/api/tasks/{task_id}/output/{name}")
async def api_task_output(task_id: str, name: str) -> FileResponse:
    path = _runner.output_path(task_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"产物不存在：{name}")
    return FileResponse(path)


@app.post("/api/chat")
async def api_chat(payload: dict) -> dict:
    question = str((payload or {}).get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")
    user_id = str((payload or {}).get("user_id") or "1")
    subject = str((payload or {}).get("subject") or "")
    try:
        from chat.chat import ChatSession

        session = ChatSession(user_id=user_id, subject=subject)
        result = await session.ask(question)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"对话失败：{exc}")
    return {
        "answer": str((result or {}).get("answer") or ""),
        "sources": (result or {}).get("sources") or [],
        "retrieved": bool((result or {}).get("retrieved")),
        "user_id": user_id,
        "subject": subject,
    }


# 前端页面由后端直接托管：访问 http://127.0.0.1:8000 即 front/index.html
# 必须放在所有 /api/* 路由之后注册，否则 mount 的 catch-all 会先匹配 /api/* 并返回 405
try:
    from fastapi.staticfiles import StaticFiles

    _front = ROOT / "front"
    if _front.is_dir():
        app.mount("/", StaticFiles(directory=str(_front), html=True), name="front")
except Exception:  # noqa: BLE001
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
