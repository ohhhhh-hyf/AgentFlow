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

_runner = TaskRunner(root=ROOT)


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
    """获取指定用户的 knowledge 知识库学科列表（直接查询 SQLite metadata）。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return {"user_id": "", "subjects": []}

    import sqlite3
    import json
    import re
    from tools.memory.store import safe_id
    uid_safe = safe_id(user_id)

    subjects_dict: dict[str, int] = {}

    # 1. 直接查询 data/{user_id}/knowledge 下的 SQLite 数据库
    candidates = [
        ROOT / "data" / uid_safe / "knowledge" / "chromadb" / "chroma.sqlite3",
        ROOT / "data" / uid_safe / "knowledge" / "chroma.sqlite3",
        ROOT / "data" / user_id / "knowledge" / "chromadb" / "chroma.sqlite3",
        ROOT / "data" / user_id / "knowledge" / "chroma.sqlite3",
    ]
    for db_path in candidates:
        if db_path.is_file():
            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT string_value, COUNT(*) FROM embedding_metadata "
                        "WHERE key='subject' AND string_value IS NOT NULL "
                        "GROUP BY string_value"
                    ).fetchall()
                    for sub, count in rows:
                        sub_str = str(sub).strip()
                        if sub_str and sub_str.lower() not in ("knowledge", "default", "none", "", "undefined"):
                            clean_s = SUBJECT_DISPLAY_MAP.get(sub_str.lower(), sub_str)
                            subjects_dict[clean_s] = subjects_dict.get(clean_s, 0) + count
                finally:
                    conn.close()
            except Exception:
                pass
            break

    # 2. 从 catalogs 目录扫描已生成的大纲
    catalogs_dir = ROOT / "data" / uid_safe / "knowledge" / "catalogs"
    if catalogs_dir.is_dir():
        for f in catalogs_dir.glob("*.json"):
            if f.stem.endswith("_meta") or f.name.startswith("."):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                course = (data.get("course") or data.get("subject") or "").strip()
                if course:
                    clean_c = SUBJECT_DISPLAY_MAP.get(course.lower(), course)
                    if clean_c not in subjects_dict:
                        subjects_dict[clean_c] = 1
                else:
                    raw_stem = re.sub(r"_[a-f0-9]{8}$", "", f.stem)
                    clean_stem = SUBJECT_DISPLAY_MAP.get(raw_stem.lower(), raw_stem)
                    if clean_stem.lower() not in ("knowledge", "default", "none", ""):
                        if clean_stem not in subjects_dict:
                            subjects_dict[clean_stem] = 1
            except Exception:
                pass

    subjects = [
        {"name": name, "count": count}
        for name, count in sorted(subjects_dict.items(), key=lambda x: x[0])
    ]

    return {
        "user_id": user_id,
        "subjects": subjects,
    }



@app.get("/api/user/{user_id}/sessions")
async def api_user_sessions(user_id: str) -> dict:
    """获取用户的所有历史会话列表（保留第一条原始问题供前端多行截断展示）。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return {"user_id": "", "sessions": []}

    from chat.store import chat_dir, load_history
    u_chat = chat_dir(ROOT, user_id)
    sessions = []
    if u_chat.is_dir():
        for s_dir in u_chat.iterdir():
            if s_dir.is_dir() and not s_dir.name.startswith("."):
                h_path = s_dir / "history.jsonl"
                history = load_history(h_path)
                first_q = ""
                for msg in history:
                    if msg.get("role") == "user":
                        first_q = (msg.get("content") or "").strip()
                        if first_q:
                            break
                title = first_q or "新会话"
                mtime = h_path.stat().st_mtime if h_path.exists() else s_dir.stat().st_mtime
                sessions.append({
                    "session_id": s_dir.name,
                    "title": title,
                    "updated_at": int(mtime * 1000),
                    "message_count": len(history)
                })
    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"user_id": user_id, "sessions": sessions}


@app.get("/api/user/{user_id}/sessions/{session_id}")
async def api_user_session_detail(user_id: str, session_id: str) -> dict:
    """获取指定会话的历史消息详情。"""
    from chat.store import history_path, load_history, facts_path, load_facts
    h_path = history_path(ROOT, user_id, session_id)
    f_path = facts_path(ROOT, user_id, session_id)
    history = load_history(h_path)
    facts = load_facts(f_path)
    return {
        "user_id": user_id,
        "session_id": session_id,
        "history": history,
        "facts": facts,
    }


@app.delete("/api/user/{user_id}/sessions/{session_id}")
async def api_delete_session(user_id: str, session_id: str) -> dict:
    """删除指定历史会话。"""
    import shutil
    from chat.store import session_dir
    s_dir = session_dir(ROOT, user_id, session_id)
    if s_dir.is_dir():
        shutil.rmtree(s_dir, ignore_errors=True)
    return {"ok": True, "session_id": session_id}


@app.post("/api/user/{user_id}/sessions/{session_id}/message")
async def api_save_session_message(user_id: str, session_id: str, payload: dict) -> dict:
    """即时保存单条会话消息（确保第一句原始输入立即落盘为会话标题）。"""
    role = str((payload or {}).get("role") or "user").strip()
    content = str((payload or {}).get("content") or "").strip()
    if user_id and session_id and content:
        try:
            from chat.store import history_path, append_turn, load_history
            h_p = history_path(ROOT, user_id, session_id)
            history = load_history(h_p)
            # 避免相邻重复保存
            if not history or not (history[-1].get("role") == role and history[-1].get("content") == content):
                append_turn(h_p, role, content)
        except Exception:
            pass
    return {"ok": True}



@app.get("/api/user/{user_id}/outputs")
async def api_user_outputs(user_id: str) -> dict:
    """获取产物云盘历史所有生成交付物。"""
    user_id = (user_id or "").strip()
    out_root = ROOT / "output"
    files = []
    TASK_NAME_MAP = {
        "minutes_generation": "会议纪要",
        "checklist": "考点清单",
        "catalog": "知识大纲",
        "quiz": "自测试卷",
        "mindmap": "思维导图",
        "action_items": "行动待办",
        "risk": "风险分析",
        "multi_styles": "多风格改写",
        "knowledge_graph": "知识图谱",
        "ocr": "笔记识别",
        "library": "资料入库",
    }
    if out_root.is_dir():
        for p in out_root.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                ext = p.suffix.lower().lstrip(".")
                if ext in ("html", "md", "json", "txt", "pdf", "png", "jpg"):
                    stat = p.stat()
                    parent_name = p.parent.name
                    task_title = TASK_NAME_MAP.get(parent_name, parent_name if parent_name != "output" else "成果产物")
                    rel_path = str(p.relative_to(out_root)).replace("\\", "/")
                    files.append({
                        "name": p.name,
                        "rel_path": rel_path,
                        "ext": ext,
                        "task_type": task_title,
                        "size": stat.st_size,
                        "updated_at": int(stat.st_mtime * 1000),
                    })
    files.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"user_id": user_id, "outputs": files}


@app.get("/api/outputs/file/{path:path}")
async def api_get_output_file(path: str):
    """读取或下载产物云盘中的文件。"""
    out_root = ROOT / "output"
    target = (out_root / path).resolve()
    if not target.is_file() or not str(target).startswith(str(out_root.resolve())):
        raise HTTPException(status_code=404, detail="产物文件不存在")
    from fastapi.responses import FileResponse
    return FileResponse(target, filename=target.name)


@app.post("/api/intent")
async def api_intent(payload: dict) -> dict:
    text = str((payload or {}).get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    user_id = str((payload or {}).get("user_id") or "").strip()
    session_id = str((payload or {}).get("session_id") or "").strip()

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
    if user_id and session_id:
        try:
            from chat.store import history_path, append_turn, load_history
            h_p = history_path(ROOT, user_id, session_id)
            history = load_history(h_p)
            if not history or not (history[-1].get("role") == "user" and history[-1].get("content") == text):
                append_turn(h_p, "user", text)
            if data.get("explanation"):
                append_turn(h_p, "assistant", data["explanation"])
        except Exception:
            pass
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
