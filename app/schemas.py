"""API 请求/响应模型。

texts 为对象，三个固定 key：transcript / keypoints / notes，
值均为字符串（多段用 \n 拼接）。出现未知 key 返回 422。
老师重点不在 texts 里传：通过 docs 传 .txt 文件名（data/{user_id}/docs/ 下），
catalog / checklist 会读取其内容作为「老师重点」。
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

TEXT_KEYS = ("transcript", "keypoints", "notes")


class Extra(BaseModel):
    """任务差异参数。template/profile 为空字符串表示使用默认（不套模板/客观视角）。"""

    template: str = ""
    profile: str = ""
    project: str = ""
    subject: str = ""
    style: str = ""
    memory: bool = False


class TaskRequest(BaseModel):
    """通用请求体。domain/task 由 URL 路径表达，请求体不再携带。
    texts 为 {三类 key: 文本内容} 对象；docs 为文件名列表
    （.json 为 catalog 目录文件；catalog/checklist 的 .txt 为老师重点文件；其余按扩展名分派）。

    兼容：历史客户端若仍发送 domain/task 会被 pydantic 静默忽略，不再做一致性校验。
    """

    texts: dict[str, str] = Field(default_factory=dict)
    docs: list[str] = Field(default_factory=list)
    extra: Extra = Field(default_factory=Extra)
    # 任务时间（会议开始或转录完成时刻），可为空；非空时写入会议记忆并在溯源卡片展示
    time: str = ""

    @field_validator("texts")
    @classmethod
    def _check_text_keys(cls, value: dict) -> dict:
        unknown = sorted(set(value or {}) - set(TEXT_KEYS))
        if unknown:
            raise ValueError(f"texts 只支持 {TEXT_KEYS}，未知 key：{unknown}")
        return {k: v for k, v in (value or {}).items() if isinstance(v, str)}


class Monitor(BaseModel):
    """任务监控字段：token 消耗 / 缓存命中 / 耗时（秒）。"""

    token_usage: int = 0
    cache_hit: int = 0
    cost_time: float = 0.0


class ResponseData(BaseModel):
    """任务产物：text 为 md 文本；file_name 为产物文件名（catalog 返回目录文件名，
    有 HTML 产物返回 {task}.html，仅文本产物返回 result.md，无产物为空串）。"""

    text: Optional[str] = None
    file_name: str = ""


class TaskResponse(BaseModel):
    """通用返回。monitor 为监控字段；data.text 为 Markdown 文本，data.file_name 为文件名。"""

    code: int = 0
    request_id: str = ""
    message: str = "success"
    monitor: Monitor = Field(default_factory=Monitor)
    data: ResponseData = Field(default_factory=ResponseData)


__all__ = ["Extra", "Monitor", "ResponseData", "TEXT_KEYS", "TaskRequest", "TaskResponse"]
