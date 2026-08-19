# -*- coding: utf-8 -*-
"""ChatSession：多轮问答会话（检索聚合 + 历史 + LLM 回答 + 会话持久化）。

- 会话数据按用户顶层隔离：``data/{user_id}/chat/sessions/{session_id}/``
- 会话历史与「已知用户信息」（我是谁）落盘，重启后可恢复
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from llm_client import LLMClient

from .prompts import CHAT_SYSTEM_PROMPT, build_user_message
from .sources import build_context, gather
from .store import (
    append_turn,
    facts_path,
    history_path,
    load_facts,
    load_history,
    save_facts,
    session_dir,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_NAME_RE = re.compile(r"(?:我是|我叫)\s*(?!什么|谁|啥|怎么|哪|名字)([\u4e00-\u9fa5A-Za-z]{2,12})")
_ROLE_RE = re.compile(
    r"(?:我是做|我从事|我的职业是|是一名|是一位|是个|是一个)\s*"
    r"(?!什么|谁|啥|怎么|哪)([\u4e00-\u9fa5A-Za-z]{2,12})"
)


def _extract_facts(text: str, current: dict[str, Any]) -> dict[str, Any]:
    """从用户消息提取「我是谁」信息（只追加新字段，不覆盖已有）。"""
    out = dict(current)
    m = _NAME_RE.search(text or "")
    if m and not out.get("name"):
        out["name"] = m.group(1)
    m = _ROLE_RE.search(text or "")
    if m and not out.get("role"):
        out["role"] = m.group(1)
    return out


def _source_marks(source: str) -> list[str]:
    """从来源字符串提取可用于匹配回答的标记（文件名 / 日期 / 标题片段）。"""
    import re

    marks: list[str] = []
    # 文件名（含扩展名与去扩展名）
    for part in re.findall(r"[\w\u4e00-\u9fa5.\-]+\.(?:txt|md|docx|pptx|pdf)", source):
        if part not in marks:
            marks.append(part)
        stem = part.rsplit(".", 1)[0]
        if stem and stem not in marks:
            marks.append(stem)
    # 日期（会议记忆 · 2026-08-19 · 标题）
    m = re.search(r"\d{4}-\d{2}-\d{2}", source)
    if m and m.group(0) not in marks:
        marks.append(m.group(0))
    # 标题片段（· 分隔的 4+ 字中文段）
    for seg in source.split("·"):
        seg = seg.strip()
        if len(seg) >= 4 and seg not in marks:
            marks.append(seg)
    return marks


def referenced_sources(sources: list[str], answer: str) -> list[str]:
    """只保留「回答中实际引用了」的来源（避免检索命中但未使用的噪声出处）。"""
    if not sources or not answer:
        return []
    return [s for s in sources if any(m and m in answer for m in _source_marks(s))]


class ChatSession:
    """一次会话：维护对话历史，每次提问先多源检索再回答。

    用法（终端/未来 web 共用）::

        session = ChatSession(user_id="1", subject="math", session_id="abc")
        result = await session.ask("两个重要极限是什么")
        # result = {"answer": str, "sources": [str, ...], "retrieved": bool}
    """

    def __init__(
        self,
        user_id: str,
        subject: str = "",
        *,
        session_id: str | None = None,
        client: LLMClient | None = None,
        history_limit: int = 8,
        top_k: int = 5,
    ) -> None:
        self.user_id = user_id
        self.subject = subject or ""
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.client = client or LLMClient()
        self.history_limit = max(2, int(history_limit))
        self.top_k = top_k

        # 持久化（data/{uid}/chat/sessions/{sid}/）
        self._sdir = session_dir(PROJECT_ROOT, user_id, self.session_id)
        self._history_path = history_path(PROJECT_ROOT, user_id, self.session_id)
        self._facts_path = facts_path(PROJECT_ROOT, user_id, self.session_id)

        # 恢复已有会话（跨进程重启）
        self._history = load_history(self._history_path)
        self._facts = load_facts(self._facts_path)

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def facts(self) -> dict[str, Any]:
        """会话内已知用户信息（我是谁）。"""
        return dict(self._facts)

    def _push(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        append_turn(self._history_path, role, content)
        if len(self._history) > self.history_limit * 2:
            self._history = self._history[-self.history_limit * 2:]

    async def ask(self, question: str) -> dict[str, Any]:
        """提问：检索 → 带历史与已知用户信息回答 → 落盘。"""
        question = (question or "").strip()
        if not question:
            return {"answer": "", "sources": [], "retrieved": False}

        # 提取「我是谁」并落盘
        new_facts = _extract_facts(question, self._facts)
        if new_facts != self._facts:
            self._facts = new_facts
            save_facts(self._facts_path, new_facts)

        docs = gather(question, self.user_id, self.subject, top_k=self.top_k)
        context = build_context(docs)

        # 历史 + 已知用户信息 → user 消息（client.text 仅 system+user 两段）
        head = ""
        if self._facts:
            bits = [f"{k}={v}" for k, v in sorted(self._facts.items())]
            head += f"【已知用户信息】{ '；'.join(bits) }\n\n"
        if self._history:
            turns = [
                f"{'用户' if m['role'] == 'user' else '助手'}：{m['content']}"
                for m in self._history[-6:]
            ]
            head += "【对话历史】\n" + "\n".join(turns) + "\n\n"

        user_msg = build_user_message(question, context)
        if head:
            user_msg = head + user_msg

        answer = await self.client.text(
            CHAT_SYSTEM_PROMPT,
            user_msg,
            temperature=0.3,
            label="chat/ask",
        )
        answer = (answer or "").strip()

        self._push("user", question)
        self._push("assistant", answer)

        # 只展示回答实际引用了的来源（避免自我介绍等场景显示检索噪声出处）
        all_sources = [str(d.get("source") or "") for d in docs if d.get("source")]
        used_sources = referenced_sources(all_sources, answer)
        return {
            "answer": answer,
            "sources": used_sources,
            "retrieved": bool(docs),
        }
