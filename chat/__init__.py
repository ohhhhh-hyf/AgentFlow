# -*- coding: utf-8 -*-
"""chat —— 知识库/记忆多源检索问答。

用户可在会话中连续提问：检索「资料知识库」（tools.knowledge，按 user+subject）
与「会议记忆」（tools.memory，按 user 跨项目）两路来源，统一上下文后由 LLM
回答并标注出处。终端版入口见 ``chat.cli``（``python -m chat.cli``）。

设计约束：
- 纯检索聚合 + 多轮问答，不引入任务线编排；供 CLI / 未来 web 复用
- 检索失败一律降级（不中断会话）；无命中按问题类型分流（见 prompts）
"""
from __future__ import annotations

from .chat import ChatSession

__all__ = ["ChatSession"]
