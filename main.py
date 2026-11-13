"""统一 FastAPI 生产级入口 (零历史包袱，双核心端点):
1. POST /api/agent/v1/stream: 纪要任务 NDJSON 流式事件直出 (TTFT < 2s);
2. POST /api/agent/v1: 待办任务/同步纪要阻塞式返回标准 JSON;
3. 严格遵循用户级目录物理隔离落盘 (data/{user_id}/output/{request_id}/);
4. 纪要仅产出 minutes.md，待办仅产出 actions.json;
5. 外挂非侵入式 LoggingMiddleware 与双文件轮转日志系统 (logs/service.log + logs/diag.log)。
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from infra.telemetry import setup_logging, unify_uvicorn_loggers
from infra.telemetry.middleware import LoggingMiddleware
from tasks.actions.agent import extract_actions_agent
from tasks.minutes.agent import generate_minutes, stream_minutes_agent

# 初始化全局隔离式日志系统 (控制台 + service.log + diag.log)
setup_logging()
unify_uvicorn_loggers()
logger = logging.getLogger("meeting_agent_service")

app = FastAPI(
    title="Meeting Agent Service",
    description="自包含、零旧依赖的现代极简会议智能体服务",
    version="1.0.0",
)

# 注册非侵入式流量日志中间件
app.add_middleware(LoggingMiddleware)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEXT_KEYS = ("transcript", "keypoints", "notes", "vision_info", "actions_text")


class Extra(BaseModel):
    """任务差异参数（严格对齐根项目）."""

    template: str = Field(default="", description="模板 ID（如 general_minutes，留空自动智能分类）")
    time: str = Field(default="", description="会议起始时间（如 2026/11/13 14:00，待办用于 Calendar 推导）")
    agenda_plan: Optional[Union[dict[str, Any], str]] = Field(
        default=None, description="结构化议程字典或 JSON 字符串"
    )

    @field_validator("agenda_plan", mode="before")
    @classmethod
    def _validate_agenda_plan(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            try:
                import json

                parsed = json.loads(v_str)
                if not isinstance(parsed, dict):
                    raise ValueError("agenda_plan JSON string must parse to a dictionary")
                return parsed
            except Exception as err:
                raise ValueError(f"Invalid JSON string for agenda_plan: {err}") from err
        if isinstance(v, dict):
            return v
        raise ValueError("agenda_plan must be a dictionary or a JSON string")


class TaskRequest(BaseModel):
    """统一严格请求体契约（严格对齐根项目，彻底移除 domain，严格固定 texts 与 extra）."""

    task: str = Field(default="minutes", description="任务类型: minutes (纪要) 或 actions (待办)")
    texts: dict[str, str] = Field(
        default_factory=dict,
        description="文本内容容器，固定包含: transcript, keypoints, notes, vision_info, actions_text",
    )
    docs: list[str] = Field(
        default_factory=list,
        description="物理材料文件名列表（存放于 data/{user_id}/docs/ 下）",
    )
    extra: Extra = Field(default_factory=Extra, description="任务参数（template, time, agenda_plan）")
    lang: str = Field(default="zh", description="语种代码: zh (中文) 或 en (英文)")

    @field_validator("lang")
    @classmethod
    def _validate_lang(cls, value: str) -> str:
        v = (value or "zh").strip().lower()
        if v in {"en", "english"}:
            return "en"
        if v in {"zh", "ch", "cn", "chinese"}:
            return "zh"
        raise ValueError(f"lang 仅支持 'zh' 或 'en'，收到未知取值：{value}")

    @field_validator("texts")
    @classmethod
    def _check_text_keys(cls, value: dict) -> dict:
        unknown = sorted(set(value or {}) - set(TEXT_KEYS))
        if unknown:
            raise ValueError(f"texts 只支持 {TEXT_KEYS}，收到未知 key：{unknown}")
        return {k: str(v) for k, v in (value or {}).items() if v is not None}


def _resolve_ids(
    x_user_id: Optional[str],
    x_request_id: Optional[str],
) -> tuple[str, str]:
    """统一解析用户 ID 与全局唯一请求跟踪 ID (严格遵从 HTTP Header)."""
    user_id = (x_user_id or "default").strip()
    if not user_id:
        user_id = "default"

    req_id = (x_request_id or "").strip()
    if not req_id:
        req_id = uuid.uuid4().hex

    return user_id, req_id


@app.get("/")
@app.get("/health")
async def health_check():
    """健康检查探针."""
    return {"status": "ok", "service": "meeting-agent", "version": "1.0.0"}


@app.post("/api/agent/v1/stream")
async def stream_agent_endpoint(
    body: TaskRequest,
    response: Response,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
):
    """纪要端到端流式直出接口 (NDJSON 事件流)."""
    transcript_val = (body.texts.get("transcript") or "").strip()
    if not transcript_val and not body.docs:
        raise HTTPException(status_code=400, detail="texts.transcript 与 docs 不能同时为空")

    user_id, req_id = _resolve_ids(x_user_id, x_request_id)
    response.headers["X-Request-Id"] = req_id

    extra_dict = {
        "template": body.extra.template,
        "time": body.extra.time,
        "agenda_plan": body.extra.agenda_plan,
    }

    async def _event_generator():
        async for line in stream_minutes_agent(
            transcript=transcript_val,
            template_id=body.extra.template,
            docs=body.docs,
            texts=body.texts,
            extra=extra_dict,
            user_id=user_id,
            request_id=req_id,
            lang=body.lang,
        ):
            yield line

    return StreamingResponse(
        _event_generator(),
        media_type="application/x-ndjson",
        headers={"X-Request-Id": req_id},
    )


@app.post("/api/agent/v1")
async def sync_agent_endpoint(
    body: TaskRequest,
    response: Response,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
):
    """同步阻塞式 Agent 接口 (待办抽取任务 或 同步纪要生成)."""
    transcript_val = (body.texts.get("transcript") or "").strip()
    user_id, req_id = _resolve_ids(x_user_id, x_request_id)
    response.headers["X-Request-Id"] = req_id

    task_type = (body.task or "minutes").strip().lower()

    # 1. 待办任务分支 (actions)
    if task_type == "actions":
        if not transcript_val:
            raise HTTPException(status_code=400, detail="texts.transcript 不能为空")

        meeting_time = (body.extra.time or "").strip()

        result = await extract_actions_agent(
            transcript=transcript_val,
            meeting_start_time=meeting_time,
            texts=body.texts,
            extra={"time": meeting_time},
            user_id=user_id,
            request_id=req_id,
        )
        return JSONResponse(content=result, headers={"X-Request-Id": req_id})

    # 2. 同步纪要任务分支 (minutes)
    if not transcript_val and not body.docs:
        raise HTTPException(status_code=400, detail="texts.transcript 与 docs 不能同时为空")

    extra_dict = {
        "template": body.extra.template,
        "time": body.extra.time,
        "agenda_plan": body.extra.agenda_plan,
    }

    markdown_text, last_done = await generate_minutes(
        transcript=transcript_val,
        template_id=body.extra.template,
        docs=body.docs,
        texts=body.texts,
        extra=extra_dict,
        user_id=user_id,
        request_id=req_id,
        lang=body.lang,
    )

    resp_payload = {
        "code": last_done.get("code", 0),
        "message": last_done.get("message", "success"),
        "request_id": req_id,
        "data": {
            "content": markdown_text,
            "text": markdown_text,
            "file_name": "minutes.md",
        },
        "monitor": last_done.get("monitor", {}),
    }
    return JSONResponse(content=resp_payload, headers={"X-Request-Id": req_id})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
