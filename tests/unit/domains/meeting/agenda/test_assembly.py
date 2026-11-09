"""会议议程输入准备与参数兼容性测试。"""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from app.schemas import Extra, TaskRequest
from app.tasks import _prepare
from domains.meeting.tasks.agenda_minutes.agenda_parser import AgendaPlan


def test_agenda_minutes_input_assembly() -> None:
    """验证 agenda_minutes 支持 extra.agenda_plan 结构化快捷通道（Dict 与 JSON 字符串）。"""
    plan_data = {
        "theme": "技术例会",
        "agenda_items": [
            {"seq": "01", "title": "大模型发布", "presenters": ["张三"]},
            {"seq": "02", "title": "算法压测", "presenters": ["李四"]},
        ],
    }

    # 1. 验证 Extra 模型解析 Dict
    e1 = Extra(agenda_plan=plan_data)
    assert isinstance(e1.agenda_plan, dict)
    assert e1.agenda_plan["theme"] == "技术例会"

    # 2. 验证 Extra 模型解析 JSON 字符串
    json_str = json.dumps(plan_data)
    e2 = Extra(agenda_plan=json_str)
    assert isinstance(e2.agenda_plan, dict)
    assert len(e2.agenda_plan["agenda_items"]) == 2

    # 3. 验证畸形 JSON 抛出 ValidationError
    with pytest.raises(ValidationError):
        Extra(agenda_plan="invalid json string {")

    # 4. 验证 _prepare 提取 extra.agenda_plan 并生成强类型 AgendaPlan
    req = TaskRequest(
        texts={"transcript": "发言者1：大家早上好，开始今天的会议。"},
        extra=Extra(agenda_plan=plan_data),
    )
    prep = _prepare("meeting", "agenda_minutes", req, "u123")
    assert prep.line == "agenda_minutes"
    plan_obj = prep.extra_line_inputs.get("agenda_plan")
    assert isinstance(plan_obj, AgendaPlan)
    assert len(plan_obj.items) == 2
    assert plan_obj.items[0].title == "大模型发布"
    assert plan_obj.items[0].presenters == ["张三"]


def test_minutes_agenda_plan_fast_track_without_docs() -> None:
    """验证 minutes 任务通过 extra.agenda_plan 快捷通道直接注入，无需 docs 即可激活议题增强。"""
    plan_data = {
        "theme": "架构委员会",
        "agenda_items": [
            {"seq": "01", "title": "微服务拆分", "presenters": ["王五"]},
        ],
    }
    req = TaskRequest(
        texts={"transcript": "王五 10:00: 我们关于微服务拆分方案达成了一致。"},
        extra=Extra(agenda_plan=plan_data),
    )
    prep = _prepare("meeting", "minutes", req, "u123")
    assert prep.line == "minutes"
    assert "agenda_plan" in prep.extra_line_inputs
    plan_obj = prep.extra_line_inputs["agenda_plan"]
    assert isinstance(plan_obj, AgendaPlan)
    assert plan_obj.items[0].title == "微服务拆分"
    assert prep.template_mode == "agenda"


def test_agenda_plan_priority_over_docs(tmp_path, monkeypatch) -> None:
    """验证当同时提供 extra.agenda_plan 与 docs 时，快捷通道 agenda_plan 优先生效。"""
    doc_path = tmp_path / "legacy_agenda.txt"
    doc_path.write_text("1. 旧文档议题 汇报人：赵六", encoding="utf-8")
    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)

    plan_data = {
        "theme": "VLM直传高精议程",
        "agenda_items": [
            {"seq": "01", "title": "VLM议题A", "presenters": ["孙七"]},
        ],
    }
    req = TaskRequest(
        texts={"transcript": "孙七 10:00: 我们开始讨论 VLM议题A。"},
        docs=["legacy_agenda.txt"],
        extra=Extra(agenda_plan=plan_data),
    )
    prep = _prepare("meeting", "agenda_minutes", req, "u123")
    plan_obj = prep.extra_line_inputs.get("agenda_plan")
    assert isinstance(plan_obj, AgendaPlan)
    assert plan_obj.items[0].title == "VLM议题A"


