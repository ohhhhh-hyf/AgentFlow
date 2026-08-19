# -*- coding: utf-8 -*-
"""LLM 桩测：用 FakeClient 隔离 LLM，测 agent 的后处理逻辑（merge/归一化/组装）。

不调用真实 LLM / 外部 API；FakeClient 返回预置响应，验证"我的代码"（后处理）
在给定 LLM 输出下行为正确。
"""
from __future__ import annotations

import pytest

from domain.notes.tasks.catalog.steps.catalog_agent import CatalogAgent
from domain.notes.models_generated import Catalog
from domain.notes.tasks.catalog.store import load_catalog, save_catalog
from tools.template_router import fill_placeholder_template


class FakeClient:
    """模拟 LLMClient：structured/text 返回预置数据。"""

    def __init__(self, draft=None, text_payload="{}"):
        self._draft = draft
        self._text = text_payload
        self.structured_calls = []
        self.text_calls = []

    async def structured(self, *args, **kwargs):
        self.structured_calls.append(kwargs.get("label", ""))
        return self._draft

    async def text(self, *args, **kwargs):
        self.text_calls.append(kwargs.get("label", ""))
        return self._text


def _stub_ctx(subject: str = "build_a") -> str:
    return f"【学科/课程】{subject}\n【用户ID】stub_user\n"


@pytest.fixture(autouse=True)
def _no_kb(monkeypatch):
    """隔离知识库：briefing 不读 chroma，专注测 agent 后处理。"""
    monkeypatch.setattr(
        "domain.notes.tasks.catalog.gather.open_knowledge",
        lambda user_id="": None,
    )


@pytest.fixture(autouse=True)
def _tmp_catalog_dir(monkeypatch, tmp_path):
    """目录读写走临时目录，不污染 data/（catalog 按 user 路由到 PROJECT_ROOT）。"""
    from domain.notes.tasks.catalog import store

    monkeypatch.setattr(store, "PROJECT_ROOT", tmp_path)


class TestCatalogAgentStub:
    @pytest.mark.asyncio
    async def test_首次build_后处理分配确定性ID与归一化(self):
        draft = Catalog.validate({
            "course": "课程",
            "version": "1",
            "mode": "build",
            "chapters": [{
                "name": "章一",
                "topics": [{
                    "name": "主题一",
                    "knowledge_points": [{
                        "name": "知识点一",
                        "knowledge_type": "概念",  # 中文枚举，归一化应转 concept
                        "importance": "9",          # 越界，钳制到 5
                    }],
                }],
            }],
            "unmatched_content": [], "uncertain_nodes": [],
            "added_chapters": [], "added_topics": [], "added_knowledge_points": [],
            "updated_knowledge_points": [], "merged_nodes": [],
        })
        agent = CatalogAgent(FakeClient(draft))
        out = await agent.run(_stub_ctx())
        ch = out.chapters[0]
        kp = ch["topics"][0]["knowledge_points"][0]
        assert ch["id"].startswith("ch_"), "merge 应分配确定性章节 ID"
        assert kp["id"].startswith("kp_"), "merge 应分配确定性 KP ID"
        assert kp["knowledge_type"] == "concept", "中文枚举应被归一化"
        assert kp["importance"] == "5", "越界数值应钳制"
        assert out.mode == "build"

    @pytest.mark.asyncio
    async def test_增量_unchanged占位保留旧内容(self):
        # 预置已有目录（stub collection）
        existing = {
            "course": "课程", "version": "2", "mode": "build",
            "chapters": [{
                "id": "ch_001", "name": "旧章", "change_type": "unchanged",
                "topics": [{
                    "id": "tp_001", "name": "旧主题", "change_type": "unchanged",
                    "knowledge_points": [{
                        "id": "kp_001", "name": "旧知识点",
                        "knowledge_type": "concept", "importance": "5",
                        "practice_type": ["证明"],
                    }],
                }],
            }],
            "added_chapters": [], "added_topics": [], "added_knowledge_points": [],
            "updated_knowledge_points": [], "merged_nodes": [],
            "unmatched_content": [], "uncertain_nodes": [],
        }
        save_catalog("stub_user__incr_b", existing)

        # LLM 返回增量 draft：旧章占位 + 新章
        draft = Catalog.validate({
            "course": "课程", "version": "3", "mode": "incremental_update",
            "chapters": [
                {"id": "ch_001", "change_type": "unchanged"},  # 占位
                {"id": "ch_002", "name": "新章", "change_type": "added",
                 "topics": [{
                     "id": "tp_002", "name": "新主题", "change_type": "added",
                     "knowledge_points": [{
                         "id": "kp_002", "name": "新知识点",
                         "knowledge_type": "method", "importance": "4",
                     }],
                 }]},
            ],
            "unmatched_content": [], "uncertain_nodes": [],
            "added_chapters": [], "added_topics": [], "added_knowledge_points": [],
            "updated_knowledge_points": [], "merged_nodes": [],
        })
        agent = CatalogAgent(FakeClient(draft))
        out = await agent.run(_stub_ctx("incr_b"))
        by_id = {c["id"]: c for c in out.chapters}
        assert by_id["ch_001"]["name"] == "旧章", "占位节点必须保留旧章节内容"
        kp = by_id["ch_001"]["topics"][0]["knowledge_points"][0]
        assert kp["name"] == "旧知识点" and kp["practice_type"] == ["证明"], "旧 KP 细节不能丢"
        assert by_id["ch_002"]["change_type"] == "added", "新章应为 added"

    @pytest.mark.asyncio
    async def test_agent_label_正确上报(self):
        draft = Catalog.validate({
            "course": "课程", "version": "1", "mode": "build",
            "chapters": [], "unmatched_content": [], "uncertain_nodes": [],
            "added_chapters": [], "added_topics": [], "added_knowledge_points": [],
            "updated_knowledge_points": [], "merged_nodes": [],
        })
        client = FakeClient(draft)
        agent = CatalogAgent(client)
        await agent.run(_stub_ctx())
        assert client.structured_calls == ["catalog/agent"], client.structured_calls


class TestFillPlaceholderTemplateStub:
    @pytest.mark.asyncio
    async def test_字段JSON_程序拼装正文(self):
        """LLM 只出字段 JSON，fill 程序化组装：值进入正文、无残留占位符。"""
        client = FakeClient(text_payload='{"fields": {"纪要正文占位": "会议讨论了项目进度与风险"}}')
        template = "【纪要】\n[纪要正文占位，约200字]"
        out = await fill_placeholder_template(client, "上下文", template)
        assert out, "fill 应返回组装结果"
        assert "会议讨论了项目进度与风险" in out
        assert "[" not in out, "组装后不应残留占位符"
        assert client.text_calls, "应调用一次 LLM 填充"

    @pytest.mark.asyncio
    async def test_非占位符模板_返回None(self):
        client = FakeClient(text_payload='{"fields": {}}')
        out = await fill_placeholder_template(client, "上下文", "自然语言描述模板，没有占位符")
        assert out is None, "非 placeholder 模板应返回 None"
