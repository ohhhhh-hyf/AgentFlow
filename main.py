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
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

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


class AgentRequestBody(BaseModel):
    """通用请求体契约 (完全兼容老脚本与新标准)."""

    task: str = Field(default="minutes", description="任务类型: minutes (纪要) 或 actions (待办)")
    transcript: str = Field(default="", description="会议原文文本或打标实录")
    template: str = Field(default="", description="模板 ID (留空自动触发智能分类判定)")
    docs: list[str] = Field(default_factory=list, description="相关文档或议程图片路径列表")
    texts: dict[str, Any] = Field(default_factory=dict, description="辅助参考文本 (keypoints, notes, vision)")
    extra: dict[str, Any] = Field(default_factory=dict, description="扩展参数 (可含 template, time, texts 等)")
    lang: str = Field(default="zh", description="语言代码: zh (中文) 或 en (英文)")
    user_id: str = Field(default="", description="用户 ID (可选，优先从 Header X-User-Id 读取)")
    request_id: str = Field(default="", description="请求 ID (可选，优先从 Header X-Request-Id 读取)")
    time: str = Field(default="", description="会议起始时间 (待办任务用于 Calendar 推导)")


def _resolve_ids(
    body: AgentRequestBody,
    x_user_id: Optional[str],
    x_request_id: Optional[str],
) -> tuple[str, str]:
    """统一解析用户 ID 与全局唯一请求跟踪 ID."""
    user_id = (x_user_id or body.user_id or "default").strip()
    if not user_id:
        user_id = "default"

    req_id = (x_request_id or body.request_id or "").strip()
    if not req_id:
        req_id = uuid.uuid4().hex

    return user_id, req_id


def _resolve_transcript(body: AgentRequestBody) -> str:
    """容错提取原文: 兼容顶层 transcript 与老脚本嵌套的 texts.transcript / extra.transcript."""
    if body.transcript and body.transcript.strip():
        return body.transcript.strip()
    if isinstance(body.texts, dict) and body.texts.get("transcript"):
        return str(body.texts["transcript"]).strip()
    if isinstance(body.extra, dict) and body.extra.get("transcript"):
        return str(body.extra["transcript"]).strip()
    return ""


@app.get("/")
@app.get("/health")
async def health_check():
    """健康检查探针."""
    return {"status": "ok", "service": "meeting-agent", "version": "1.0.0"}


@app.post("/api/agent/v1/stream")
async def stream_agent_endpoint(
    body: AgentRequestBody,
    response: Response,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
):
    """纪要端到端流式直出接口 (NDJSON 事件流)."""
    transcript_val = _resolve_transcript(body)
    if not transcript_val and not body.docs:
        raise HTTPException(status_code=400, detail="transcript 或 docs 不能同时为空")

    user_id, req_id = _resolve_ids(body, x_user_id, x_request_id)
    response.headers["X-Request-Id"] = req_id

    # 整合 texts 参数（body.texts 与 body.extra.texts 容错合并）
    merged_texts = dict(body.texts)
    if isinstance(body.extra.get("texts"), dict):
        merged_texts.update(body.extra["texts"])

    # 优先使用顶级 template，缺失则从 extra 取
    template_id = body.template or str(body.extra.get("template") or "")

    async def _event_generator():
        async for line in stream_minutes_agent(
            transcript=transcript_val,
            template_id=template_id,
            docs=body.docs,
            texts=merged_texts,
            extra=body.extra,
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
    body: AgentRequestBody,
    response: Response,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
):
    """同步阻塞式 Agent 接口 (待办抽取任务 或 同步纪要生成)."""
    transcript_val = _resolve_transcript(body)
    if not transcript_val and not body.docs:
        raise HTTPException(status_code=400, detail="transcript 或 docs 不能同时为空")

    user_id, req_id = _resolve_ids(body, x_user_id, x_request_id)
    response.headers["X-Request-Id"] = req_id

    task_type = (body.task or "minutes").strip().lower()

    # 1. 待办任务分支 (actions)
    if task_type == "actions":
        merged_texts = dict(body.texts)
        if isinstance(body.extra.get("texts"), dict):
            merged_texts.update(body.extra["texts"])

        meeting_time = (body.time or str(body.extra.get("time") or "")).strip()

        result = await extract_actions_agent(
            transcript=transcript_val,
            meeting_start_time=meeting_time,
            texts=merged_texts,
            extra=body.extra,
            user_id=user_id,
            request_id=req_id,
        )
        return JSONResponse(content=result, headers={"X-Request-Id": req_id})

    # 2. 同步纪要任务分支 (minutes)
    template_id = body.template or str(body.extra.get("template") or "")
    merged_texts = dict(body.texts)
    if isinstance(body.extra.get("texts"), dict):
        merged_texts.update(body.extra["texts"])

    markdown_text, last_done = await generate_minutes(
        transcript=transcript_val,
        template_id=template_id,
        docs=body.docs,
        texts=merged_texts,
        extra=body.extra,
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
            "text": markdown_text,  # 同时兼容读取 content 或 text 的客户端
            "file_name": "minutes.md",
        },
        "monitor": last_done.get("monitor", {}),
    }
    return JSONResponse(content=resp_payload, headers={"X-Request-Id": req_id})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
