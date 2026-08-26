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

    from chat.profile import ensure_profile
    user_prof = ensure_profile(ROOT, uid_safe)

    return {
        "user_id": user_id,
        "subjects": subjects,
        "profile": {
            "user_id": user_id,
            "name": user_prof.get("name") or "",
            "role": user_prof.get("role") or "客观全员",
            "base_template": user_prof.get("base_template") or "object",
            "template_label": user_prof.get("template_label") or "客观 · 客观全员",
            "traits": user_prof.get("traits") or {},
        },
    }


@app.post("/api/user/{user_id}/profile")
async def api_update_user_profile(user_id: str, body: dict) -> dict:
    """显式更新用户的职业/视角画像及个性化偏好 traits。"""
    user_id = (user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="用户 ID 不能为空")
    role = str(body.get("role") or body.get("template") or body.get("base_template") or "").strip()
    traits = body.get("traits")
    name = str(body.get("name") or "").strip()
    from chat.profile import update_user_profile_data
    updated = update_user_profile_data(ROOT, user_id, role=role, traits=traits, name=name)
    return {"ok": True, "profile": updated}


TEMPLATE_MAPPING_INFO = {
    "general_minutes.md": {"title": "通用纪要", "scenario": "日常"},
    "team_meeting.md": {"title": "团队例会", "scenario": "会议"},
    "project_progress.md": {"title": "项目进度会", "scenario": "会议"},
    "decision_review.md": {"title": "决策评审会", "scenario": "会议"},
    "workshop_session.md": {"title": "工作研讨会", "scenario": "会议"},
    "retrospective_session.md": {"title": "总结复盘会", "scenario": "会议"},
    "exchange_forum.md": {"title": "沟通交流会", "scenario": "会议"},
    "class_transcript.md": {"title": "课堂记录", "scenario": "学习"},
    "special_lecture.md": {"title": "专题讲座", "scenario": "学习"},
    "group_seminar.md": {"title": "小组讨论", "scenario": "学习"},
    "knowledge_memo.md": {"title": "知识笔记", "scenario": "学习"},
    "debate_forum.md": {"title": "辩论会", "scenario": "学习"},
    "research_dialogue.md": {"title": "调研访谈", "scenario": "访谈"},
    "interview_transcript.md": {"title": "采访记录", "scenario": "访谈"},
    "hiring_report.md": {"title": "面试报告", "scenario": "面试"},
    "interview_debrief.md": {"title": "面试复盘", "scenario": "面试"},
    "clinical_advisory.md": {"title": "就医咨询", "scenario": "医疗"},
    "psychological_session.md": {"title": "心理咨询", "scenario": "医疗"},
    "legal_advisory.md": {"title": "法律咨询", "scenario": "法律"},
    "court_transcript.md": {"title": "庭审记录", "scenario": "法律"},
    "contract_vetting.md": {"title": "合同审核", "scenario": "法律"},
    "media_briefing.md": {"title": "新闻发布", "scenario": "发布"},
    "product_launch.md": {"title": "产品发布", "scenario": "发布"},
    "government_bulletin.md": {"title": "政府报告", "scenario": "发布"},
    "media_qa_session.md": {"title": "媒体问答", "scenario": "发布"},
    "personal_memo.md": {"title": "个人备忘", "scenario": "日常"},
    "conversation_transcript.md": {"title": "对话记录", "scenario": "日常"},
    "site_visit_tour.md": {"title": "参观游览", "scenario": "日常"},
    "home_school_liaison.md": {"title": "家校沟通", "scenario": "日常"},
}


@app.get("/api/templates/{task}")
async def api_get_templates(task: str) -> dict:
    """获取指定任务的内置样例模板列表。"""
    domain = "notes" if task in {"library", "catalog", "checklist", "quiz", "knowledge_graph"} else "meeting"
    tpl_dir = ROOT / "samples" / domain / f"{task}_template"
    if not tpl_dir.is_dir():
        tpl_dir = ROOT / "samples" / domain / "template"

    templates = []
    if tpl_dir.is_dir():
        for f in sorted(tpl_dir.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
                info = TEMPLATE_MAPPING_INFO.get(f.name, {})
                title = info.get("title") or f.stem
                scenario = info.get("scenario") or "通用"
                templates.append({
                    "filename": f.name,
                    "title": title,
                    "scenario": scenario,
                    "display_name": f"{title}（{scenario}）" if scenario else title,
                    "content": content,
                })
            except Exception:
                pass

    # 按场景和标题排序，default_template 为空（默认不使用模板，原始标准纪要输出）
    templates.sort(key=lambda x: (x["scenario"], x["title"]))
    return {"task": task, "default_template": "", "templates": templates}


def _build_fallback_placeholder_template(description: str, task: str, domain: str) -> str:
    """智能解析自然语言需求，生成结构化 Markdown 占位符骨架。"""
    title = "# [文档标题 / 会议主题]"
    sections = []

    # 基础信息
    if any(k in description for k in ["基本", "信息", "时间", "地点", "人员", "参会"]) or task == "minutes_generation":
        sections.append("## 一、基本信息\n- 会议主题：[会议主题说明]\n- 会议时间：[会议召开日期与具体时间]\n- 会议地点/形式：[会议室或线上会议链接]\n- 参会人员：[参会人员名单及部门职务]\n- 主持人/记录人：[主持人与纪要记录人]")

    # 发言要点/核心讨论
    if any(k in description for k in ["发言", "要点", "讨论", "内容", "汇报", "纪要"]) or task == "minutes_generation":
        sections.append("## 二、核心议题与发言要点\n- [按参会人员或重点议题，提炼核心发言观点、业务讨论过程及关键数据]")

    # 风险预警
    if any(k in description for k in ["风险", "预警", "隐患", "问题", "阻碍"]) or task == "risk":
        sections.append("## 三、主要风险与应对方案\n- [梳理会议讨论中识别出的技术、业务或进度风险及对应防范措施]")

    # 待办/行动项
    if any(k in description for k in ["待办", "行动", "计划", "下一步", "安排", "任务", "todo"]) or task == "action_items":
        sections.append("## 四、待办事项与行动计划 (Action Items)\n| 序号 | 待办事项 | 负责人 | 截止时间 | 交付成果 |\n| :--- | :--- | :--- | :--- | :--- |\n| 1 | [待办任务具体描述] | [指定负责人] | [完成时间节点] | [产出成果或验收标准] |")

    if not sections:
        sections.append("## 一、核心概述\n- [背景目标与总体结论说明]")
        sections.append("## 二、关键要点分解\n- [按结构拆解的核心内容与详细阐述]")
        sections.append("## 三、下一步行动与结论\n- [结论总结与后续跟进安排]")

    return title + "\n\n" + "\n\n".join(sections)


@app.post("/api/template/compile")
async def api_compile_template(payload: dict) -> dict:
    """自然语言描述编译为占位符模板。"""
    description = str((payload or {}).get("description") or "").strip()
    task = str((payload or {}).get("task") or "minutes_generation").strip()
    domain = "notes" if task in {"library", "catalog", "checklist", "quiz", "knowledge_graph"} else "meeting"
    if not description:
        raise HTTPException(status_code=400, detail="description 不能为空")

    from tools.template_router import (
        maybe_compile_natural_template,
        check_compile_fidelity,
        detect_template_kind,
        LINE_SCHEMA_HINTS,
    )

    schema_hint = LINE_SCHEMA_HINTS.get(task, "")
    compiled = ""

    try:
        from client import LLMClient
        client = LLMClient()
        compiled = await maybe_compile_natural_template(
            description,
            domain=domain,
            line_name=task,
            schema_hint=schema_hint,
            client=client,
        )
    except Exception:
        compiled = ""

    if not compiled or detect_template_kind(compiled) != "placeholder":
        compiled = _build_fallback_placeholder_template(description, task, domain)

    issues = check_compile_fidelity(description, compiled)
    return {
        "task": task,
        "description": description,
        "compiled": compiled,
        "issues": issues,
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
    if user_id and session_id and not (payload or {}).get("hide_history"):
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
