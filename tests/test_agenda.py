"""阶段三议程解析与对齐纯算法自测 (零旧代码依赖)."""
import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from tasks.minutes.agenda import (
    clean_presenter_names,
    parse_agenda_text,
    ensure_agenda_plan,
    process_agenda_for_minutes,
    probe_valid_agendas,
)


def test_clean_presenter_names():
    """测试汇报人人名清洗 (工号、前缀、空格拆分)."""
    raw1 = "汇报人: 张三 00585440"
    assert clean_presenter_names(raw1) == ["张三"]

    raw2 = "李四 00939670; 王五"
    assert clean_presenter_names(raw2) == ["李四", "王五"]

    raw3 = "Presenter: Alice Chen"
    assert clean_presenter_names(raw3) == ["Alice Chen"]


def test_parse_markdown_table_agenda():
    """测试 Markdown 管道表格解析."""
    table = """
| 序号 | 议题全称 | 汇报人 | 时长 |
| --- | --- | --- | --- |
| 1 | 核心交易链路重构方案 | 张三 008899 | 30min |
| 2 | 跨机房容灾部署规划 | 李四 | 20min |
    """.strip()

    plan = parse_agenda_text(table)
    assert len(plan.items) == 2
    assert plan.items[0].seq == "01"
    assert plan.items[0].title == "核心交易链路重构方案"
    assert plan.items[0].presenters == ["张三"]
    assert plan.items[1].seq == "02"
    assert plan.items[1].title == "跨机房容灾部署规划"
    assert plan.items[1].presenters == ["李四"]


def test_parse_list_agenda():
    """测试列表格式议程解析."""
    text_list = """
1. 用户增长策略与渠道分析 汇报人：王海
2. 运营成本精细化管控 汇报人：刘芳 001234
    """.strip()

    plan = parse_agenda_text(text_list)
    assert len(plan.items) == 2
    assert plan.items[0].title == "用户增长策略与渠道分析"
    assert plan.items[0].presenters == ["王海"]
    assert plan.items[1].title == "运营成本精细化管控"
    assert plan.items[1].presenters == ["刘芳"]


def test_ensure_agenda_plan_from_vlm_dict():
    """测试从 VLM 视觉返回的字典格式解析."""
    vlm_dict = {
        "theme": "2026架构研讨会",
        "attendees": ["张三", "李四"],
        "agenda_items": [
            {"seq": "01", "title": "微服务治理演进", "presenters": ["赵工"]},
            {"seq": "02", "title": "茶歇合影留念", "presenters": []},
        ],
    }
    plan = ensure_agenda_plan(vlm_dict)
    assert plan.meta.theme == "2026架构研讨会"
    assert len(plan.items) == 2
    assert plan.items[0].title == "微服务治理演进"


def test_agenda_alignment_and_ceremonial_filtering():
    """测试真实文本对齐与仪式性环节过滤."""
    agenda_table = """
| 序号 | 议题名称 | 汇报人 |
| --- | --- | --- |
| 1 | 核心交易链路重构方案 | 张三 |
| 2 | 合影留念 | |
| 3 | 跨机房容灾部署规划 | 李四 |
    """.strip()

    transcript = """
主持人 09:00:00
大家早上好，欢迎参加本次架构评审会，今天我们有两个核心议题需要讨论。

张三 09:05:00
我来汇报一下核心交易链路重构方案。我们重构的主要目标是将延迟降低 50%，采用新的异步消息机制，预计三周内完成灰度。

主持人 09:40:00
好，辛苦张工。接下来大家合个影，大家看镜头！

李四 09:45:00
下面由我汇报跨机房容灾部署规划。我们计划在华东和华北建立双活机房，网络延迟控制在 15ms 以内，确保数据强一致性。

主持人 10:15:00
感谢李工，今天两位汇报的方案全部拍板通过，请大家按照排期推进，散会！
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_table)
    assert res.has_valid_agenda is True
    # 验证仪式项“合影留念”被过滤，只有 2 个实质议题
    assert len(res.valid_agendas) == 2
    assert res.valid_agendas[0].title == "核心交易链路重构方案"
    assert res.valid_agendas[1].title == "跨机房容灾部署规划"

    # 验证打标文本结构
    tagged = res.tagged_transcript
    assert "【现场审定的有效议题清单】" in tagged
    assert "【会议开场背景与主线脉络】" in tagged
    assert "【议题 1：核心交易链路重构方案】" in tagged
    assert "【议题 2：跨机房容灾部署规划】" in tagged
    assert "【会末收尾与全场定调】" in tagged


def test_empty_or_no_match_fallback():
    """测试无议程或未匹配时平滑降级."""
    transcript = "大家随便聊聊天气和周末去哪玩。"
    res = process_agenda_for_minutes(transcript, "")
    assert res.has_valid_agenda is False
    assert res.valid_agendas == []
    assert res.tagged_transcript == transcript

    probed = probe_valid_agendas(transcript, "")
    assert probed == []
