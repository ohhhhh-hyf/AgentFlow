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
from app.tasks import _collect_texts, _pack_minutes_auxiliary, _parse_notes_items, _prepare
from domains.meeting.models import Minutes
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    KEYPOINTS_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    NOTES_PROMPT_BLOCK,
    VISION_PROMPT_BLOCK,
    _SUPERVISOR_COMMON_BASE,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent


def test_tc09_schema_and_text_keys_validation():
    """TC-09: 验证 TEXT_KEYS 包含 4 个字段，支持 vision_info，拦截未知 key。"""
    assert "transcript" in TEXT_KEYS
    assert "keypoints" in TEXT_KEYS
    assert "notes" in TEXT_KEYS
    assert "vision_info" in TEXT_KEYS
    assert len(TEXT_KEYS) == 4

    # 合法 4 字段解析
    req = TaskRequest(
        texts={
            "transcript": "Hello world",
            "keypoints": "Key metric 46%",
            "notes": "Quote -> Comment",
            "vision_info": "OCR text from dashboard",
        }
    )
    assert req.texts["vision_info"] == "OCR text from dashboard"

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


def test_tc01_downward_compatibility_pure_voice():
    """TC-01: 向下兼容纯语音 (仅 transcript，辅助项全空)。"""
    req = TaskRequest(texts={"transcript": "今天开会讨论下周发布计划。"})
    t, k, n, v = _collect_texts(req)
    assert t == "今天开会讨论下周发布计划。"
    assert k == "" and n == "" and v == ""

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


def test_tc08_supervisor_prompt_and_rules():
    """TC-08: Supervisor 审查准则验证 (批注拦截、数据专名一致)。"""
    assert "多源辅助参考审查（输入含对应标签时生效）" in _SUPERVISOR_COMMON_BASE
    assert "拦截主观批注：【用户划线原话与笔记】中的个人批注与主观吐槽严禁进入正文" in _SUPERVISOR_COMMON_BASE
    assert "数据专名一致：正文引用的【用户核心关键点】与【视觉信息参考(OCR)】" in _SUPERVISOR_COMMON_BASE
    assert "泄露【用户划线原话与笔记】中的批注或主观吐槽" in _SUPERVISOR_COMMON_BASE


def test_tc06_prepare_line_extra_minutes_auxiliary():
    """TC-06: 验证 _prepare 函数能正确为 minutes 任务组装 minutes_auxiliary。"""
    req = TaskRequest(
        texts={
            "transcript": "今天开会讨论下周发布计划。",
            "keypoints": "流程审批量同比增长46%",
            "notes": "广州珠海增加7个 -> 真的假的？",
            "vision_info": "吞吐量 15000 QPS",
        }
    )
    prep = _prepare("meeting", "minutes", req, user_id="test_user")
    assert prep.line == "minutes"
    assert "minutes_auxiliary" in prep.extra_line_inputs
    aux = prep.extra_line_inputs["minutes_auxiliary"]
    assert "【用户核心关键点】\n流程审批量同比增长46%" in aux
    assert "【用户划线原话与笔记】\n- 原话：\"广州珠海增加7个\" | 备注：真的假的？" in aux
    assert "【视觉信息参考(OCR)】\n吞吐量 15000 QPS" in aux


def test_tc06_orchestrator_context_injection():
    """TC-06: 验证 orchestrator 编排层将 minutes_auxiliary 分别注入 shared_context 与 supervisor_context。"""
    from domains.meeting.orchestrator import _Nodes

    nodes = _Nodes.__new__(_Nodes)
    nodes._supervisor_source_pack = lambda state, ln: "【原文依据切片】"
    nodes._length_budget_line = lambda state, ln, **kwargs: ""
    nodes._revision_instruction = lambda state, ln: ""
    nodes._meeting_pack = lambda state, ln: {}
    nodes._mode_label = lambda state: "objective"

    state = {
        "transcript": "会议原文内容...",
        "lines": {"minutes": {"draft": {"headline": "测试纪要", "executive_summary": []}}},
        "line_extra": {
            "minutes_auxiliary": "【用户核心关键点】\n指标A提升30%\n\n【视觉信息参考(OCR)】\nQPS: 12000"
        },
        "objective_perspective": True,
        "templates": {},
    }

    # 1. 验证草稿 Agent 上下文挂载
    shared_ctx = nodes._line_shared_context(state, "minutes")
    assert "【用户核心关键点】\n指标A提升30%" in shared_ctx
    assert "【视觉信息参考(OCR)】\nQPS: 12000" in shared_ctx

    # 2. 验证 Supervisor 审核上下文挂载
    sup_ctx = nodes._supervisor_context(state, "minutes")
    assert "【用户核心关键点】\n指标A提升30%" in sup_ctx
    assert "【视觉信息参考(OCR)】\nQPS: 12000" in sup_ctx


def test_normal_minutes_aux_unchanged():
    """普通 minutes：aux 照常注入，但不出现议程标记或议程清单。"""
    # 1. _prepare：无 docs -> 只有 minutes_auxiliary，没有 agenda_text
    req = TaskRequest(
        texts={
            "transcript": "今天开会讨论下周发布计划。",
            "keypoints": "流程审批量同比增长46%",
            "notes": "广州珠海增加7个 -> 真的假的？",
            "vision_info": "吞吐量 15000 QPS",
        }
    )
    prep = _prepare("meeting", "minutes", req, user_id="test_user")
    assert "minutes_auxiliary" in prep.extra_line_inputs
    assert "agenda_text" not in prep.extra_line_inputs

    # 2. _line_shared_context：aux 照常出现，但不出现议程标记/清单
    from domains.meeting.orchestrator import _Nodes

    nodes = _Nodes()
    state = {
        "transcript": "今天开会讨论下周发布计划。",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {
            "meeting_brief": "常规简报",
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "line_extra": {
            "minutes_auxiliary": (
                "【用户核心关键点】\n流程审批量同比增长46%\n\n"
                "【用户划线原话与笔记】\n- 原话：\"广州珠海增加7个\" | 备注：真的假的？\n\n"
                "【视觉信息参考(OCR)】\n吞吐量 15000 QPS"
            )
        },
    }
    context = nodes._line_shared_context(state, "minutes")
    assert "【用户核心关键点】\n流程审批量同比增长46%" in context
    assert "【用户划线原话与笔记】" in context
    assert "【视觉信息参考(OCR)】\n吞吐量 15000 QPS" in context
    assert "议题模式：agenda_enhanced" not in context
    assert "【现场审定的有效议题清单】" not in context


# ── TC-10：议题纪要 + 多源辅助的 system prompt 组装 ──────────────────────────

_AGENDA_BASE = (
    "议题模式：agenda_enhanced\n"
    "视角模式：objective\n\n"
    "【会议原文】\n讨论了指标。\n\n"
)
_KEYPOINTS_TAG = "【用户核心关键点】\n流程审批量同比增长46%"
_NOTES_TAG = (
    "【用户划线原话与笔记】\n"
    "- 原话：\"上线时间定在周五\" | 备注：确认发布窗口"
)
_VISION_TAG = "【视觉信息参考(OCR)】\n服务器CPU使用率峰值82%"


def _agenda_context(*tags: str) -> str:
    parts = [_AGENDA_BASE.rstrip(), "会议理解：\n{}"]
    if tags:
        parts.insert(
            1,
            "════════════════════════════════════════\n" + "\n\n".join(tags),
        )
    return "\n\n".join(parts)


def _normal_context(*tags: str) -> str:
    parts = ["视角模式：objective\n\n【会议原文】\n讨论了指标。", "会议理解：\n{}"]
    if tags:
        parts.insert(
            1,
            "════════════════════════════════════════\n" + "\n\n".join(tags),
        )
    return "\n\n".join(parts)


async def _capture_system_prompt(
    shared_context: str, *, lang: str = "zh", view: str = "objective"
) -> str:
    captured: dict[str, str] = {}

    class FakeClient:
        async def structured(self, system, *args, **kwargs):
            captured["system"] = system
            return Minutes(headline="测试标题")

    agent = MinutesGenerationAgent(FakeClient())
    await agent.run(shared_context, view=view, lang=lang)
    return captured["system"]


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
