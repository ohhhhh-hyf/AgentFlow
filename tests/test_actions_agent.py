"""阶段五单元自测：Calendar 绝对时间解析、待办提取 Agent 与时间回填集成。"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from infra.calendar.enrich import enrich_actions_deadlines
from infra.calendar.fast_path import try_fast_extract
from infra.calendar.tool import resolve_deadline
from tasks.actions.agent import (
    build_actions_user_message,
    extract_actions_agent,
    normalize_action_item,
)
from tasks.actions.prompts import (
    ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
    build_actions_system_prompt,
)


def test_calendar_fast_path_and_tool():
    """测试 Fast-Path 规则匹配与确定性日历工具计算。"""
    # 锚点：2026-10-30 10:00:00 (周五)
    anchor = "2026-10-30 10:00:00"

    # 1. 明天18:00
    ir_tomorrow = try_fast_extract(0, "明天18:00")
    assert ir_tomorrow is not None
    assert ir_tomorrow.status == "resolved"
    res_tomorrow = resolve_deadline(anchor, ir_tomorrow)
    assert res_tomorrow.deadline == "2026/10/31 18:00"
    assert res_tomorrow.kind == "datetime"

    # 2. 下周五
    ir_next_fri = try_fast_extract(1, "下周五")
    assert ir_next_fri is not None
    assert ir_next_fri.status == "resolved"
    res_next_fri = resolve_deadline(anchor, ir_next_fri)
    assert res_next_fri.deadline == "2026/11/06"
    assert res_next_fri.kind == "date"

    # 3. 本月底
    ir_month_end = try_fast_extract(2, "本月底")
    assert ir_month_end is not None
    assert ir_month_end.status == "resolved"
    res_month_end = resolve_deadline(anchor, ir_month_end)
    assert res_month_end.deadline == "2026/10/31"

    # 4. 尽快 (无明确时间)
    ir_asap = try_fast_extract(3, "尽快处理")
    assert ir_asap is not None
    assert ir_asap.status == "none"
    res_asap = resolve_deadline(anchor, ir_asap)
    assert res_asap.deadline is None


def test_enrich_actions_deadlines_batch():
    """测试待办事项 1:1 绝对时间批量回填。"""
    actions = [
        {"title": "任务1", "deadline": "明天18:00"},
        {"title": "任务2", "deadline": "下周五"},
        {"title": "任务3", "deadline": "尽快"},
        {"title": "任务4", "deadline": None},
    ]

    async def _test():
        res = await enrich_actions_deadlines(
            actions=actions,
            meeting_start_time="2026-10-30 10:00:00",
            use_fast_path=True,
        )
        assert len(res) == 4

        # 任务1：明天18:00
        assert res[0]["deadline_raw"] == "明天18:00"
        assert res[0]["deadline_display"] == "2026/10/31 18:00"
        assert res[0]["deadline"] == "2026-10-31T18:00:00"

        # 任务2：下周五
        assert res[1]["deadline_raw"] == "下周五"
        assert res[1]["deadline_display"] == "2026/11/06"
        assert res[1]["deadline"] == "2026-11-06T18:00:00"

        # 任务3：尽快 -> None
        assert res[2]["deadline_raw"] == "尽快"
        assert res[2]["deadline"] is None

        # 任务4：None -> None
        assert res[3]["deadline_raw"] is None
        assert res[3]["deadline"] is None

    asyncio.run(_test())


def test_normalize_action_item():
    """测试 7 字段规范化与无责任人条目过滤。"""
    # 正常完整项
    valid_raw = {
        "title": "架构压测",
        "item": "组织核心链路压测",
        "owner": "张三",
        "deadline": "下周五",
        "collaborators": ["李四", "王五"],
        "acceptance_criteria": "TPS > 5000",
        "dependency": "部署完成",
    }
    norm = normalize_action_item(valid_raw)
    assert norm is not None
    assert norm["title"] == "架构压测"
    assert norm["owner"] == "张三"
    assert norm["collaborators"] == ["李四", "王五"]

    # 缺少责任人 -> 严格过滤为 None
    invalid_no_owner = {
        "title": "泛泛讨论",
        "item": "大家要重视安全",
        "owner": None,
    }
    assert normalize_action_item(invalid_no_owner) is None

    # 事项正文为空 -> 过滤
    invalid_no_item = {
        "title": "空任务",
        "item": "",
        "owner": "张三",
    }
    assert normalize_action_item(invalid_no_item) is None


def test_build_actions_user_message_and_prompt():
    """测试待办 User Message 与 System Prompt 多源辅助块组装。"""
    texts = {
        "actions_text": "张三提到下周五前完成方案",
        "keypoints": "核心重点保障系统不崩",
        "notes": "划线：李四承诺明天给反馈",
        "vision": "架构拓扑图显示支持5000TPS",
    }
    msg = build_actions_user_message("会议讨论...", texts=texts)
    assert "【会议原文】" in msg
    assert "【用户标记待办原文】" in msg
    assert "【用户核心关键点】" in msg
    assert "【用户划线原话与笔记】" in msg
    assert "【视觉信息参考(OCR)】" in msg

    prompt = build_actions_system_prompt(msg)
    assert "用户标记待办原文参考" in prompt
    assert "用户关键点参考" in prompt
    assert "用户划线原话与笔记参考" in prompt
    assert "视觉信息参考(OCR)" in prompt


def test_extract_actions_agent_mock_dual_states(tmp_path: Path):
    """测试 Actions Agent 双态分支流程：
    态 A：传时间 -> 调 Calendar，产出并落盘 actions + actions_update
    态 B：不传时间 -> 跳过 Calendar，产出并落盘 actions (无 actions_update)
    """
    mock_llm_response = {
        "actions": [
            {
                "title": "支付链路压测",
                "item": "组织开展核心交易链路基准压测，输出性能评估报告",
                "owner": "张三",
                "deadline": "明天18:00",
                "collaborators": ["李四"],
                "acceptance_criteria": "TPS 突破 5000",
                "dependency": None,
            },
            {
                "title": "营销预算审批",
                "item": "提交 Q4 华东投放预算申请流程",
                "owner": "王五",
                "deadline": "下周五",
                "collaborators": [],
                "acceptance_criteria": "完成财务线上签批",
                "dependency": "方案评审通过",
            },
            {
                "title": "无效项无责任人",
                "item": "大家要多沟通",
                "owner": None,
            },
        ]
    }

    mock_client = MagicMock()
    mock_client.chat_json = AsyncMock(return_value=mock_llm_response)

    async def _test():
        # ── 1. 态 A：提供了会议时间 ─────────────────────────────────────────
        out_file_a = tmp_path / "user1" / "output" / "req1" / "actions.json"
        res_a = await extract_actions_agent(
            transcript="会议讨论实录...",
            meeting_start_time="2026-10-30 10:00:00",
            user_id="user1",
            request_id="req1",
            output_path=out_file_a,
            llm_client=mock_client,
        )

        assert res_a["code"] == 0
        assert res_a["message"] == "success"
        assert res_a["request_id"] == "req1"
        assert "actions" in res_a
        assert "actions_update" in res_a
        assert len(res_a["actions"]) == 2
        assert len(res_a["actions_update"]) == 2

        # 原始 actions 字段保留原话
        assert res_a["actions"][0]["deadline"] == "明天18:00"
        # actions_update 回填了绝对时间
        assert res_a["actions_update"][0]["deadline_display"] == "2026/10/31 18:00"
        assert res_a["actions_update"][0]["deadline"] == "2026-10-31T18:00:00"

        # 验证 data.text 返回平铺待办且 file_name 对齐
        assert res_a["data"]["file_name"] == "actions_update.json"
        assert isinstance(res_a["data"]["text"], list)
        assert res_a["data"]["text"] == res_a["actions_update"]

        # 验证落盘文件：actions.json 与 actions_update.json 均为纯平铺数组
        assert out_file_a.is_file()
        disk_data_a = json.loads(out_file_a.read_text(encoding="utf-8"))
        assert isinstance(disk_data_a, list)
        assert len(disk_data_a) == 2

        out_file_update_a = out_file_a.parent / "actions_update.json"
        assert out_file_update_a.is_file()
        disk_update_a = json.loads(out_file_update_a.read_text(encoding="utf-8"))
        assert isinstance(disk_update_a, list)
        assert len(disk_update_a) == 2
        assert disk_update_a[0]["deadline_display"] == "2026/10/31 18:00"

        # ── 2. 态 B：未提供会议时间（完全跳过 Calendar） ──────────────────
        out_file_b = tmp_path / "user2" / "output" / "req2" / "actions.json"
        res_b = await extract_actions_agent(
            transcript="会议讨论实录...",
            meeting_start_time="",  # 空串
            extra={},
            user_id="user2",
            request_id="req2",
            output_path=out_file_b,
            llm_client=mock_client,
        )

        assert res_b["code"] == 0
        assert res_b["message"] == "success"
        assert res_b["request_id"] == "req2"
        assert "actions" in res_b
        assert "actions_update" not in res_b
        assert res_b["monitor"]["calendar_executed"] is False
        assert len(res_b["actions"]) == 2

        # 验证 data.text 返回平铺待办且 file_name 对齐
        assert res_b["data"]["file_name"] == "actions.json"
        assert isinstance(res_b["data"]["text"], list)
        assert res_b["data"]["text"] == res_b["actions"]

        # 验证落盘文件：仅生成 actions.json 纯平铺数组，不生成 actions_update.json
        assert out_file_b.is_file()
        disk_data_b = json.loads(out_file_b.read_text(encoding="utf-8"))
        assert isinstance(disk_data_b, list)
        assert len(disk_data_b) == 2

        out_file_update_b = out_file_b.parent / "actions_update.json"
        assert not out_file_update_b.is_file()

    asyncio.run(_test())
