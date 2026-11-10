# 拆分自原大文件，保留：test_tc09_schema_and_text_keys_validation, test_tc03_notes_parser_and_auxiliary_pack, test_actions_auxiliary_pack_isolated_from_minutes…

"""多源文本融合会议纪要单元测试 (Multi-Source Texts Minutes).

覆盖 TC-01 至 TC-10:
- TC-01: 向下兼容纯语音 (仅 transcript)
- TC-02: 单项包含关键点 (transcript + keypoints)
- TC-03: 单项包含笔记含箭头与无箭头 (transcript + notes)
- TC-04: 单项包含视觉信息 (transcript + vision_info)
- TC-05: 多源全开 (四者俱全)
- TC-06: 与议题纪要 docs 共存
- TC-07: 英文多语种适配 (lang='en')
- TC-08: Supervisor 审查准则验证与上下文注入
- TC-09: Schema 协议层检验 (vision_info 校验与非法 key 拦截)
- TC-10: 议题纪要 + 多源辅助的 system prompt 组装
"""

from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import ValidationError
from app.schemas import TEXT_KEYS, TaskRequest
from app.tasks import (
    _collect_texts,
    _pack_actions_auxiliary,
    _pack_minutes_auxiliary,
    _parse_notes_items,
    _prepare,
)
from domains.meeting.models import Minutes
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    build_minutes_supervisor_prompt,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from tests.support.builders import (
    AGENDA_BASE as _AGENDA_BASE,
    KEYPOINTS_TAG as _KEYPOINTS_TAG,
    NOTES_TAG as _NOTES_TAG,
    VISION_TAG as _VISION_TAG,
    agenda_context as _agenda_context,
    normal_context as _normal_context,
)

pytestmark = pytest.mark.integration

async def _capture_system_prompt(
    shared_context: str, *, lang: str = "zh", view: str = "objective"
) -> str:
    captured: dict[str, str] = {}

    class FakeClient:
        async def structured(self, system, *args, **kwargs):
            captured["system"] = system
            return Minutes()

    agent = MinutesGenerationAgent(FakeClient())
    await agent.run(shared_context, view=view, lang=lang)
    return captured["system"]

def test_tc09_schema_and_text_keys_validation():
    """TC-09: 验证 TEXT_KEYS 包含 5 个字段，支持 vision_info / actions_text，拦截未知 key。"""
    assert "transcript" in TEXT_KEYS
    assert "keypoints" in TEXT_KEYS
    assert "notes" in TEXT_KEYS
    assert "vision_info" in TEXT_KEYS
    assert "actions_text" in TEXT_KEYS
    assert len(TEXT_KEYS) == 5

    # 合法 5 字段解析
    req = TaskRequest(
        texts={
            "transcript": "Hello world",
            "keypoints": "Key metric 46%",
            "notes": "Quote -> Comment",
            "vision_info": "OCR text from dashboard",
            "actions_text": "EPC需提供合同确认函",
        }
    )
    assert req.texts["vision_info"] == "OCR text from dashboard"
    assert req.texts["actions_text"] == "EPC需提供合同确认函"

    # 未知 key 抛出 ValidationError
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(texts={"transcript": "test", "illegal_field": "bad"})
    assert "texts 只支持" in str(exc_info.value)


def test_tc03_notes_parser_and_auxiliary_pack():
    """TC-03 辅助解析: 验证 notes 箭头切分容错性与多源辅助打包。"""
    notes_raw = """
    那8月份的这边的话是广州，珠海这边是增加了7个。 ->真的假的？
    流程审批量同比增长46% -> 扯淡呢
    下半年需重点做好去库存工作
    """
    items = _parse_notes_items(notes_raw)
    assert len(items) == 3
    # 箭头前后空格容错
    assert items[0]["quote"] == "那8月份的这边的话是广州，珠海这边是增加了7个。"
    assert items[0]["comment"] == "真的假的？"

    assert items[1]["quote"] == "流程审批量同比增长46%"
    assert items[1]["comment"] == "扯淡呢"

    # 无箭头行整行作为备注
    assert items[2]["quote"] == ""
    assert items[2]["comment"] == "下半年需重点做好去库存工作"

    # 打包测试
    packed = _pack_minutes_auxiliary(
        keypoints="重点指标达成 95%",
        notes=notes_raw,
        vision_info="系统架构图：Auth -> Gateway -> Service",
    )
    assert "【用户核心关键点】\n重点指标达成 95%" in packed
    assert "【用户划线原话与笔记】" in packed
    assert "- 原话：\"那8月份的这边的话是广州，珠海这边是增加了7个。\" | 备注：真的假的？" in packed
    assert "- 笔记：下半年需重点做好去库存工作" in packed
    assert "【视觉信息参考(OCR)】\n系统架构图：Auth -> Gateway -> Service" in packed


def test_actions_auxiliary_pack_isolated_from_minutes():
    """actions_text 只进入 actions 辅助块，不能被 minutes auxiliary 消费。"""
    packed = _pack_actions_auxiliary(
        actions_text="EPC需提供合同确认函",
        keypoints="重点指标达成 95%",
        notes="原话 -> 备注",
        vision_info="OCR 参数表",
    )
    assert "【用户标记待办原文】\nEPC需提供合同确认函" in packed
    assert "【用户核心关键点】" in packed
    assert "【用户划线原话与笔记】" in packed
    assert "【视觉信息参考(OCR)】" in packed

    minutes_aux = _pack_minutes_auxiliary("重点指标达成 95%", "原话 -> 备注", "OCR 参数表")
    assert "【用户标记待办原文】" not in minutes_aux


def test_tc01_downward_compatibility_pure_voice():
    """TC-01: 向下兼容纯语音 (仅 transcript，辅助项全空)。"""
    req = TaskRequest(texts={"transcript": "今天开会讨论下周发布计划。"})
    t, k, n, v, a = _collect_texts(req)
    assert t == "今天开会讨论下周发布计划。"
    assert k == "" and n == "" and v == "" and a == ""

    aux = _pack_minutes_auxiliary(k, n, v)
    assert aux == ""


@pytest.mark.anyio
async def test_tc01_agent_prompt_pure_voice():
    """TC-01: 验证纯语音输入时，Prompt 中绝不包含任何辅助规则块。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "会议纪要",
        "executive_summary": ["会议讨论了业务。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = "【会议原文】\n讨论了下周工作排期。\n\n会议理解：\n{}"
    await agent.run(shared_context, view="objective", lang="zh")

    sys_prompt = mock_client.structured.call_args[0][0]
    assert "## 用户关键点参考" not in sys_prompt
    assert "## 用户笔记参考" not in sys_prompt
    assert "## 视觉信息参考 (OCR)" not in sys_prompt


@pytest.mark.anyio
async def test_tc02_agent_prompt_only_keypoints():
    """TC-02: 单项包含关键点 (仅 keypoints)。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "会议纪要",
        "executive_summary": ["会议讨论了业务。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = (
        "【会议原文】\n讨论了指标。\n\n"
        "════════════════════════════════════════\n"
        "【用户核心关键点】\n流程审批量同比增长46%，超时率下降0.38%\n\n"
        "会议理解：\n{}"
    )
    await agent.run(shared_context, view="objective", lang="zh")

    sys_prompt = mock_client.structured.call_args[0][0]
    assert "## 用户关键点参考" in sys_prompt
    assert "事实尽量靠拢" in sys_prompt
    assert "保持数据一致" in sys_prompt
    assert "## 用户笔记参考" not in sys_prompt
    assert "## 视觉信息参考 (OCR)" not in sys_prompt


@pytest.mark.anyio
async def test_tc03_agent_prompt_only_notes():
    """TC-03: 单项包含笔记 (仅 notes)。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "会议纪要",
        "executive_summary": ["会议讨论了业务。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = (
        "【会议原文】\n讨论了广州珠海项目。\n\n"
        "════════════════════════════════════════\n"
        "【用户划线原话与笔记】\n- 原话：\"广州珠海增加7个\" | 备注：真的假的？\n\n"
        "会议理解：\n{}"
    )
    await agent.run(shared_context, view="objective", lang="zh")

    sys_prompt = mock_client.structured.call_args[0][0]
    assert "## 用户笔记参考" in sys_prompt
    assert "结合原话事实" in sys_prompt
    assert "个人批注不入文" in sys_prompt
    assert "## 用户关键点参考" not in sys_prompt
    assert "## 视觉信息参考 (OCR)" not in sys_prompt


@pytest.mark.anyio
async def test_tc04_agent_prompt_only_vision():
    """TC-04: 单项包含视觉信息 (仅 vision_info)。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "会议纪要",
        "executive_summary": ["会议讨论了业务。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = (
        "【会议原文】\n讨论了架构。\n\n"
        "════════════════════════════════════════\n"
        "【视觉信息参考(OCR)】\nAPI Gateway v2.4 吞吐量 15000 QPS\n\n"
        "会议理解：\n{}"
    )
    await agent.run(shared_context, view="objective", lang="zh")

    sys_prompt = mock_client.structured.call_args[0][0]
    assert "## 视觉信息参考 (OCR)" in sys_prompt
    assert "补充具体数据" in sys_prompt
    assert "不脱离研讨发散" in sys_prompt
    assert "## 用户关键点参考" not in sys_prompt
    assert "## 用户笔记参考" not in sys_prompt


@pytest.mark.anyio
async def test_tc05_agent_prompt_all_sources():
    """TC-05: 多源全开 (四者俱全)。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "会议纪要",
        "executive_summary": ["会议讨论了业务。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = (
        "【会议原文】\n讨论了各项业务。\n\n"
        "════════════════════════════════════════\n"
        "【用户核心关键点】\n指标A提升30%\n\n"
        "【用户划线原话与笔记】\n- 原话：\"上线时间定在周五\" | 备注：确认发布窗口\n\n"
        "【视觉信息参考(OCR)】\n服务器CPU使用率峰值82%\n\n"
        "会议理解：\n{}"
    )
    await agent.run(shared_context, view="objective", lang="zh")

    sys_prompt = mock_client.structured.call_args[0][0]
    assert "## 用户关键点参考" in sys_prompt
    assert "## 用户笔记参考" in sys_prompt
    assert "## 视觉信息参考 (OCR)" in sys_prompt


@pytest.mark.anyio
async def test_tc07_english_adaptation_with_all_sources():
    """TC-07: 英文多语种适配 (lang='en' 时四者俱全，外层头尾语言红线包裹)。"""
    mock_client = MagicMock()
    dummy_minutes = MagicMock(spec=Minutes)
    dummy_minutes.model_dump.return_value = {
        "headline": "Meeting Minutes",
        "executive_summary": ["Team reviewed progress."],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)
    shared_context = (
        "输出语种要求：英文（English）\n\n"
        "【会议原文】\nTeam discussed sprint items.\n\n"
        "════════════════════════════════════════\n"
        "【用户核心关键点】\nLatency reduced by 15%\n\n"
        "【用户划线原话与笔记】\n- 原话：\"Deploy on Friday\" | 备注：check window\n\n"
        "【视觉信息参考(OCR)】\nQPS: 12000\n\n"
        "会议理解：\n{}"
    )
    await agent.run(shared_context, view="objective", lang="en")

    sys_prompt = mock_client.structured.call_args[0][0]
    # 头部英文人设
    assert "【核心人设与交付目标】" in sys_prompt
    assert "你是专职的【英文（English）】会议纪要草稿 Agent" in sys_prompt
    # 包含辅助规则
    assert "## 用户关键点参考" in sys_prompt
    assert "## 用户笔记参考" in sys_prompt
    assert "## 视觉信息参考 (OCR)" in sys_prompt
    # 尾部语言红线
    assert "## 语言红线" in sys_prompt
    assert "所有字段必须严格使用【英文（English）】输出" in sys_prompt


@pytest.mark.anyio
async def test_agenda_aux_block_present():
    """议题纪要 + 任一辅助标签 -> system prompt 含议程边界 block。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(_KEYPOINTS_TAG), view="agenda_objective"
    )
    assert AGENDA_AUX_PROMPT_BLOCK in sys_prompt
    assert "【议程骨架优先】" in sys_prompt


@pytest.mark.anyio
async def test_agenda_aux_block_absent_without_aux():
    """议题纪要 + 无辅助标签 -> system prompt 等于议程生成 prompt。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(), view="agenda_objective"
    )
    assert sys_prompt == MINUTES_AGENDA_GENERATION_PROMPT
    assert "【议程骨架优先】" not in sys_prompt


@pytest.mark.anyio
async def test_agenda_aux_block_absent_for_normal():
    """普通 minutes + 辅助字段 -> 不追加议程边界 block。"""
    sys_prompt = await _capture_system_prompt(_normal_context(_KEYPOINTS_TAG))
    assert "【议程骨架优先】" not in sys_prompt
    assert "## 用户关键点参考" in sys_prompt
    assert sys_prompt.startswith(MINUTES_OBJECTIVE_GENERATION_PROMPT)


@pytest.mark.anyio
async def test_agenda_aux_block_before_shared():
    """议程边界 block 必须位于三块共享字段规则之前。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(_KEYPOINTS_TAG, _NOTES_TAG, _VISION_TAG),
        view="agenda_objective",
    )
    assert sys_prompt.index("【议程骨架优先】") < sys_prompt.index("## 用户关键点参考")
    assert sys_prompt.index("## 用户关键点参考") < sys_prompt.index("## 用户笔记参考")
    assert sys_prompt.index("## 用户笔记参考") < sys_prompt.index("## 视觉信息参考 (OCR)")


@pytest.mark.anyio
async def test_agenda_keypoints_only():
    """议题纪要 + 只传 keypoints -> 只追加 keypoints 共享规则。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(_KEYPOINTS_TAG), view="agenda_objective"
    )
    assert "【议程骨架优先】" in sys_prompt
    assert "## 用户关键点参考" in sys_prompt
    assert "## 用户笔记参考" not in sys_prompt
    assert "## 视觉信息参考 (OCR)" not in sys_prompt


@pytest.mark.anyio
async def test_shared_aux_blocks_once():
    """议程边界 block 与三块共享规则各出现一次，不重复追加。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(_KEYPOINTS_TAG, _NOTES_TAG, _VISION_TAG),
        view="agenda_objective",
    )
    assert sys_prompt.count("【议程骨架优先】") == 1
    assert sys_prompt.count("## 用户关键点参考") == 1
    assert sys_prompt.count("## 用户笔记参考") == 1
    assert sys_prompt.count("## 视觉信息参考 (OCR)") == 1


@pytest.mark.anyio
async def test_agenda_aux_blocks_survive_english_wrapper():
    """lang=en 的英文 wrapper 只剥离首段人设，不丢议程/共享 block。"""
    sys_prompt = await _capture_system_prompt(
        _agenda_context(_KEYPOINTS_TAG),
        lang="en",
        view="agenda_objective",
    )
    assert "【核心人设与交付目标】" in sys_prompt
    assert "【议程骨架优先】" in sys_prompt
    assert "## 用户关键点参考" in sys_prompt


@pytest.mark.anyio
async def test_minutes_objective_self_contained_prompt_content():
    """验证客观普通纪要基底 Prompt 自包含且彻底去除二传手依赖。"""
    from domains.meeting.tasks.minutes.prompts import MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 1. 彻底去除旧二传手字样
    assert "【会议理解】" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "以会议理解为事实骨架" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "搬运整合字段" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "以理解层" not in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 2. 包含正向 4 句话研讨提炼规范
    assert "根据会议实际研讨的事项数量与讨论深度自然分项" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "围绕业务主线就事论事展开" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "原文中提及的具体技术指标、系统名称、版本号、对比数据与排期节点等量化信息" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "客观呈现研讨中的不同观点、质询考量及拉通共识" in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 3. 包含落地行动与分工安排大白话规范
    assert "清晰交代责任归属（明确到具体人名或团队）、具体执行任务或交付物、以及完成时限或时间节点" in MINUTES_OBJECTIVE_GENERATION_PROMPT


@pytest.mark.anyio
async def test_minutes_normal_aux_block_present():
    """普通客观纪要 + 辅助材料 -> system prompt 挂载通用辅助规约与共享规则。"""
    sys_prompt = await _capture_system_prompt(
        _normal_context(_KEYPOINTS_TAG, _NOTES_TAG),
        view="objective",
        lang="zh",
    )
    assert "## 辅助材料使用规约" in sys_prompt
    assert "【原文事实优先】" in sys_prompt
    assert "【辅助参考定位】" in sys_prompt
    assert "【议程骨架优先】" not in sys_prompt
    assert "## 用户关键点参考" in sys_prompt
    assert "## 用户笔记参考" in sys_prompt
    assert "## 视觉信息参考 (OCR)" not in sys_prompt


@pytest.mark.anyio
async def test_minutes_normal_aux_blocks_survive_english_wrapper():
    """普通客观纪要英文模式 -> 英文人设包裹 + 4大语言红线 + 辅助材料规约完整保留。"""
    sys_prompt = await _capture_system_prompt(
        _normal_context(_KEYPOINTS_TAG),
        view="objective",
        lang="en",
    )
    # 头部英文人设
    assert "【核心人设与交付目标】" in sys_prompt
    assert "你是专职的【英文（English）】会议纪要草稿 Agent" in sys_prompt
    # 保留辅助规约
    assert "【原文事实优先】" in sys_prompt
    assert "## 用户关键点参考" in sys_prompt
    # 尾部语言红线
    assert "## 语言红线" in sys_prompt
    assert "所有字段必须严格使用【英文（English）】输出" in sys_prompt
    assert "[Owner] Action + Deliverable + Deadline" in sys_prompt

