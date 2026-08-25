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

from Intent import parse

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

# 启动时加载项目根目录 .env 到环境变量（如 OCR_ENGINE=rapidocr、LLM 配置等）
def _load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        return
    import os
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'\"")

_load_env_file(ROOT / ".env")

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


# 常见英文/拼音学科名映射为人类易读展示名
SUBJECT_DISPLAY_MAP = {
    "math": "数学",
    "physics": "物理",
    "chemistry": "化学",
    "english": "英语",
    "chinese": "语文",
    "cs": "计算机",
    "computer": "计算机",
    "biology": "生物",
    "geography": "地理",
    "history": "历史",
    "politics": "政治",
}


@app.get("/api/user/{user_id}/context")
async def api_user_context(user_id: str) -> dict:
    """获取指定用户的知识库学科列表、会议项目列表与记忆概览。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return {"user_id": "", "subjects": [], "projects": []}

    import json
    import re
    from tools.memory.store import safe_id
    uid_safe = safe_id(user_id)
    user_dir = ROOT / "data" / uid_safe

    subjects_dict: dict[str, int] = {}

    # 1. 从 ChromaDB 向量库扫描真实 chunk 的 subject 元数据（避免暴露内部集合名 knowledge 或 c_hash）
    chroma_dir = user_dir / "knowledge" / "chromadb"
    if chroma_dir.is_dir():
        try:
            from tools.knowledge.config import KnowledgeToolConfig
            from tools.knowledge.vector_store import VectorStore
            cfg = KnowledgeToolConfig(persist_dir=str(chroma_dir))
            store = VectorStore(cfg=cfg)
            for c in store.client.list_collections():
                if c.count() == 0:
                    continue
                try:
                    res = c.get(include=["metadatas"])
                    for m in (res.get("metadatas") or []):
                        if m and m.get("subject"):
                            s = str(m.get("subject")).strip()
                            if s and s.lower() not in ("knowledge", "default", "none", "", "undefined"):
                                clean_s = SUBJECT_DISPLAY_MAP.get(s.lower(), s)
                                subjects_dict[clean_s] = subjects_dict.get(clean_s, 0) + 1
                except Exception:
                    pass
        except Exception:
            pass

    # 2. 从 catalogs 目录扫描已生成的大纲与课程名
    catalogs_dir = user_dir / "knowledge" / "catalogs"
    if catalogs_dir.is_dir():
        for f in catalogs_dir.glob("*.json"):
            if f.stem.endswith("_meta") or f.name.startswith("."):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                course = (data.get("course") or data.get("subject") or "").strip()
                if course:
                    clean_c = SUBJECT_DISPLAY_MAP.get(course.lower(), course)
                    if not any(k in clean_c for k in subjects_dict):
                        subjects_dict[clean_c] = subjects_dict.get(clean_c, 0) + 1
                else:
                    # 去除内部哈希后缀（例如 math_7e676e9e -> math -> 数学）
                    raw_stem = re.sub(r"_[a-f0-9]{8}$", "", f.stem)
                    clean_stem = SUBJECT_DISPLAY_MAP.get(raw_stem.lower(), raw_stem)
                    if clean_stem.lower() not in ("knowledge", "default", "none", ""):
                        if clean_stem not in subjects_dict:
                            subjects_dict[clean_stem] = 1
            except Exception:
                pass

    # 3. 扫描会议记忆项目
    projects_set = set()
    meeting_mem_dir = user_dir / "memory" / "meeting"
    if meeting_mem_dir.is_dir():
        for item in meeting_mem_dir.iterdir():
            p_name = item.stem
            if p_name and not p_name.startswith("."):
                projects_set.add(p_name)

    subjects = [
        {"name": name, "count": count}
        for name, count in sorted(subjects_dict.items(), key=lambda x: x[0])
    ]
    projects = sorted(projects_set)

    return {
        "user_id": user_id,
        "subjects": subjects,
        "projects": projects,
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
    session_id = str((payload or {}).get("session_id") or "")
    try:
        from chat.chat import ChatSession

        session = ChatSession(
            user_id=user_id,
            subject=subject,
            session_id=session_id or None,  # 前端传同一 session_id → 会话历史连续
        )
        result = await session.ask(question)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"对话失败：{exc}")
    return {
        "answer": str((result or {}).get("answer") or ""),
        "sources": (result or {}).get("sources") or [],
        "retrieved": bool((result or {}).get("retrieved")),
        "session_id": session.session_id,
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
