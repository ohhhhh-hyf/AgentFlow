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
    """从来源字符串提取可用于匹配回答的标记。

    只认「文件名」与「标题」这类可唯一指向来源的片段——
    不把日期当标记（日期太泛，AI 回答里出现同一天日期不代表引用了该档案）。
    """
    import re

    marks: list[str] = []
    # 文件名（含扩展名与去扩展名）——知识库来源
    for part in re.findall(r"[\w\u4e00-\u9fa5.\-]+\.(?:txt|md|docx|pptx|pdf)", source):
        if part not in marks:
            marks.append(part)
        stem = part.rsplit(".", 1)[0]
        if stem and stem not in marks:
            marks.append(stem)
    # 标题片段（会议记忆格式：{标题} · 第N场（{日期} 记录），取第一个 · 段）
    segments = [s.strip().strip("[]") for s in source.split("·")]
    if len(segments) >= 2:
        title = segments[0]
        if len(title) >= 4 and not re.fullmatch(r"[\d\s:\-]+", title):
            if title not in marks:
                marks.append(title)
    return marks


def _strip_citation_markers(text: str) -> str:
    """去掉回答正文里的引用序号标注（[1]、据[1]、[1][2]）与 Markdown 强调符号。

    引用序号是**纯数字**（如 [1]、[2]），与数学闭区间（[0,1]、[-1,1] 含逗号）
    可精确区分，不会误删。匹配逻辑仍用带序号的原文（referenced_sources），
    这里只做展示层清洗。

    Markdown：``**x**`` → ``x``、`` `x` `` → ``x``、行首 ``#`` 标题符号去掉；
    单个 ``*``（数学乘号 a*b）与 ``**`` 不成对出现（如 2**3）不受影响。
    """
    text = re.sub(r"据\s*\[\d+\]", "", text or "")       # 据[1] / 据 [1]
    text = re.sub(r"\[\d+\]", "", text)                   # 残留 [1] [2]（含 [1][2] 连写）
    text = re.sub(r"（\s*）|\(\s*\)", "", text)           # 清掉被删后遗留的空括号
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)          # **粗体** → 粗体
    text = re.sub(r"`([^`]+)`", r"\1", text)               # `代码` → 代码
    text = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]*", "", text)   # 行首 # 标题符号
    return text.strip()


def referenced_sources(docs: list[dict], answer: str) -> list[str]:
    """只保留「回答中实际引用了」的来源（避免检索命中但未使用的噪声出处）。

    匹配分两路，任一命中即亮：
    1. 序号回指：回答里出现 ``[i]``（对应【检索到的资料】的第 i 条）→ 直接亮该条
       （资料块格式 ``[1]（资料 · 文件名）…``，prompt 要求按「据[1]」标注）
    2. 原文兜底：回答复述了文件名 / 标题原文 → 亮（_source_marks 提取的标记）
    """
    if not docs or not answer:
        return []
    used: list[str] = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        idx = int(m.group(1))
        if 1 <= idx <= len(docs):
            src = str((docs[idx - 1].get("source") or "")).strip()
            if src and src not in used:
                used.append(src)
    all_sources = [str(d.get("source") or "") for d in docs if d.get("source")]
    for s in all_sources:
        if s not in used and any(m and m in answer for m in _source_marks(s)):
            used.append(s)
    return used


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

        # 用户画像档案：保证 data/{uid}/profile/{uid}.json 存在（含 user_id）
        try:
            from .profile import ensure_profile

            ensure_profile(PROJECT_ROOT, user_id)
        except Exception:  # noqa: BLE001 - 画像落盘失败不阻断会话
            logger.warning("用户画像初始化失败", exc_info=True)

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

        # 检索门控：规则短路（寒暄零成本）→ LLM 门控 → 按需检索（省成本、不主动翻旧账）
        from .gate import decide

        gate = await decide(question, self.client, self._history)
        docs: list[dict[str, Any]] = []
        if gate.need_knowledge or gate.need_memory:
            docs = gather(
                question,
                self.user_id,
                self.subject,
                top_k=self.top_k,
                need_knowledge=gate.need_knowledge,
                need_memory=gate.need_memory,
            )
        context = build_context(docs)

        # 历史 + 已知用户信息 + 用户画像 → user 消息（client.text 仅 system+user 两段）
        head = ""
        if self._facts:
            bits = [f"{k}={v}" for k, v in sorted(self._facts.items())]
            head += f"【已知用户信息】{ '；'.join(bits) }\n\n"
        try:
            from .profile import resolve_user_profile

            profile = resolve_user_profile(PROJECT_ROOT, self.user_id)
            if profile:
                bits: list[str] = []
                for key in ("name", "role"):
                    value = str(profile.get(key) or "").strip()
                    if value:
                        bits.append(f"{key}={value}")
                traits = profile.get("traits")
                if isinstance(traits, dict):
                    for key, value in traits.items():
                        value = str(value or "").strip()
                        if value:
                            bits.append(f"{key}={value}")
                if bits:
                    head += "【用户画像】" + "；".join(bits) + "\n\n"
        except Exception:  # noqa: BLE001 - 画像读取失败不阻断提问
            logger.warning("读取用户画像失败", exc_info=True)
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

        # 只展示回答实际引用了的来源（避免自我介绍等场景显示检索噪声出处）
        used_sources = referenced_sources(docs, answer)
        # 展示层：去掉正文里的引用序号（匹配已用带序号的 answer 完成）
        display_answer = _strip_citation_markers(answer)

        self._push("user", question)
        self._push("assistant", display_answer)

        # 用户画像：每轮问答后从对话提取姓名/角色/偏好，更新 data/{uid}/profile/{uid}.json
        try:
            from .profile import update_profile_from_chat

            await update_profile_from_chat(
                PROJECT_ROOT, self.user_id, self.client, self._history
            )
        except Exception:  # noqa: BLE001 - 画像更新失败不阻断回答
            logger.warning("用户画像更新失败", exc_info=True)

        return {
            "answer": display_answer,
            "sources": used_sources,
            "retrieved": bool(docs),
        }
