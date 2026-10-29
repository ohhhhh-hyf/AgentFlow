"""议题纪要 v1 边界：personal×agenda 拒绝、agenda 去个人化、记忆迁移止血。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.schemas import TaskRequest
from app.tasks import ApiError, _prepare
from core.execution.hard_execution import (
    enforce_minutes_draft,
    is_agenda_enhanced_mode,
)
from core.runner.profiles import resolve_profile_mode
from domains.meeting.agenda_engine import ValidAgendaItem
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.agenda_minutes.alignment_engine import DiscussionBlock
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
)
from domains.meeting.views import (
    AgendaPersonalUnsupported,
    VIEW_AGENDA_OBJECTIVE,
    resolve_minutes_view,
)


def _agenda_item() -> ValidAgendaItem:
    return ValidAgendaItem(
        seq="1",
        title="自研芯片二期量产",
        presenters=["张三"],
        start_index=0,
        end_index=1,
        matched_blocks=[
            DiscussionBlock(
                speaker="张三", timestamp="10:00", content="芯片良率达标", index=0
            )
        ],
    )


def _agenda_state(*, user: dict, objective_perspective: bool = False) -> dict:
    item = _agenda_item()
    return {
        "transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%",
        "tagged_transcript": (
            "【现场审定的有效议题清单】：\n"
            "1. 议题：自研芯片二期量产（汇报人：张三）\n\n"
            "════════════════════════════════════════\n"
            "【议题 01：自研芯片二期量产】\n"
            "张三 10:00: 芯片良率达标"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [item],
        "user": user,
        "objective_perspective": objective_perspective,
        "meeting_understanding": {},
        "perspective_profile": {"personal_summary": "本人负责芯片量产"},
        "user_hits_block": "【本用户命中】\n- 张三：芯片良率",
        "user_radar_block": "【重点关注雷达】\n- 张三",
        "line_extra": {
            "agenda_text": "1. 自研芯片二期量产 汇报人：张三",
            "minutes_auxiliary": "【用户核心关键点】\n良率91.5%",
        },
        "templates": {"minutes": "# 通用纪要\n## [全文摘要]\n[占位]"},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "",
                    "executive_summary": [],
                    "key_decisions": [],
                    "personally_relevant_points": [],
                    "risks_and_blockers": [],
                    "unresolved_questions": [],
                    "history_comparison": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }


def _normal_personal_state() -> dict:
    return {
        "transcript": "张三 10:00: 讨论常规事项",
        "user": {"name": "张三"},
        "objective_perspective": False,
        "has_valid_agenda": False,
        "meeting_understanding": {
            "meeting_brief": "常规简报",
            "meeting_purpose": "同步进展",
            "session_segments": [
                {
                    "segment_title": "进展同步",
                    "context_and_reasoning": "张三同步进展",
                    "key_facts": ["完成联调"],
                }
            ],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "perspective_profile": {"personal_summary": "本人负责联调"},
        "user_hits_block": "【本用户命中】\n- 张三：联调",
        "user_radar_block": "【重点关注雷达】\n- 张三",
        "line_extra": {},
        "templates": {"minutes": "# 个人视角纪要\n## [会议概况]\n[占位]"},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "",
                    "executive_summary": [],
                    "key_decisions": [],
                    "personally_relevant_points": [],
                    "risks_and_blockers": [],
                    "unresolved_questions": [],
                    "history_comparison": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }


# ── 1. view 裁决 ─────────────────────────────────────────────


def test_resolve_profile_mode() -> None:
    assert resolve_profile_mode({}) == "objective"
    assert resolve_profile_mode({"perspective": "objective"}) == "objective"
    assert resolve_profile_mode({"name": "张三"}) == "personal"
    assert (
        resolve_profile_mode(
            {"name": "开发人员", "persona_type": "role_template"}
        )
        == "role_template"
    )


def test_resolve_minutes_view_matrix() -> None:
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="personal")
        == "personal"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="objective")
        == "objective"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="role_template")
        == "role_template"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=True, profile_mode="objective")
        == VIEW_AGENDA_OBJECTIVE
    )
    assert (
        resolve_minutes_view(has_valid_agenda=True, profile_mode="role_template")
        == VIEW_AGENDA_OBJECTIVE
    )
    with pytest.raises(AgendaPersonalUnsupported):
        resolve_minutes_view(has_valid_agenda=True, profile_mode="personal")


# ── 2. API 入口门禁 ─────────────────────────────────────────


def _prepare_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三", encoding="utf-8")
    user_path = tmp_path / "user.json"
    user_path.write_text(json.dumps({"name": "张三"}), encoding="utf-8")

    root = Path(__file__).resolve().parents[3]
    developer_path = root / "resources" / "profiles" / "developer.json"
    object_path = root / "resources" / "profiles" / "object.json"

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)

    def fake_profile_file(domain: str, profile_value: str, user_id: str = "") -> Path:
        value = (profile_value or "").strip().lower()
        if value == "user":
            return user_path
        if value == "developer":
            return developer_path
        return object_path

    monkeypatch.setattr("app.tasks._profile_file", fake_profile_file)


def _minutes_req(profile: str) -> TaskRequest:
    return TaskRequest(
        texts={"transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%"},
        docs=["agenda.txt"],
        extra={"profile": profile},
    )


def test_personal_agenda_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    with pytest.raises(ApiError) as exc:
        _prepare("meeting", "minutes", _minutes_req("user"), "u_test_personal")
    assert exc.value.status == 400
    assert "个人视角暂不支持议题增强模式" in exc.value.message


def test_role_template_agenda_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    prep = _prepare("meeting", "minutes", _minutes_req("developer"), "u_test_role")
    assert prep.minutes_view == VIEW_AGENDA_OBJECTIVE
    assert prep.prepare_warning
    assert prep.profile_file.name == "object.json"
    text = prep.templates["minutes"].read_text(encoding="utf-8")
    assert "以现场审定的有效议题清单为主线展开" in text


def test_prepare_objective_agenda_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    prep = _prepare("meeting", "minutes", _minutes_req(""), "u_test_objective")
    assert prep.minutes_view == VIEW_AGENDA_OBJECTIVE
    assert prep.prepare_warning == ""
    text = prep.templates["minutes"].read_text(encoding="utf-8")
    assert "以现场审定的有效议题清单为主线展开" in text


def test_prepare_run_rejects_personal_agenda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import _runner_args
    from core.runner.runner import prepare_run

    _prepare_fixture(tmp_path, monkeypatch)
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 讨论常规事项"},
        extra={"profile": "user"},
    )
    p = _prepare("meeting", "minutes", req, "u_test_run_personal")
    p.extra_line_inputs["agenda_text"] = "1. 自研芯片二期量产 汇报人：张三"
    with pytest.raises(ValueError, match="个人视角暂不支持议题增强模式"):
        asyncio.run(prepare_run(p.ctx, **_runner_args(p)))


def test_prepare_run_forces_role_template_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import _runner_args
    from core.runner.runner import prepare_run

    _prepare_fixture(tmp_path, monkeypatch)
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 讨论常规事项"},
        extra={"profile": "developer"},
    )
    p = _prepare("meeting", "minutes", req, "u_test_run_role")
    p.extra_line_inputs["agenda_text"] = "1. 自研芯片二期量产 汇报人：张三"
    prep = asyncio.run(prepare_run(p.ctx, **_runner_args(p)))
    user_data = (
        prep.user.model_dump()
        if hasattr(prep.user, "model_dump")
        else dict(prep.user)
    )
    assert user_data["perspective"] == "objective"


def test_stream_personal_agenda_returns_error_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import iter_task_events

    _prepare_fixture(tmp_path, monkeypatch)

    async def _collect():
        return [
            event
            async for event in iter_task_events(
                "meeting",
                "minutes",
                _minutes_req("user"),
                user_id="u_test_stream_personal",
                request_id="req_test_stream_personal",
            )
        ]

    events = asyncio.run(_collect())
    assert events
    assert events[0]["type"] == "error"
    assert events[0]["code"] == 400
    assert "个人视角暂不支持议题增强模式" in events[0]["message"]


# ── 3. 编排层上下文去个人/角色化 ─────────────────────────────


def test_agenda_agent_context_has_no_personal_blocks() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    context = nodes._line_shared_context(state, "minutes")
    assert "议题模式：agenda_enhanced" in context
    assert "视角模式：objective" in context
    assert "用户画像" not in context
    assert "用户视角模型" not in context
    assert "【本用户命中】" not in context
    assert "【重点关注雷达】" not in context
    assert "会议理解" not in context
    assert "会议原文" in context


def test_normal_personal_context_is_4_plus_9_only() -> None:
    """Step 6：个人单线草稿上下文只给 4+9，不再注入画像/命中/雷达。"""
    nodes = _Nodes()
    context = nodes._line_shared_context(_normal_personal_state(), "minutes")
    assert context.startswith("会议理解：")
    assert "meeting_brief" in context
    assert "session_segments" in context
    assert "meeting_purpose" not in context
    assert "用户视角模型：" in context
    assert "用户画像" not in context
    assert "【本用户命中】" not in context
    assert "【重点关注雷达】" not in context


def test_agenda_supervisor_context_has_no_personal_blocks() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    context = nodes._supervisor_context(state, "minutes")
    assert "议题模式：agenda_enhanced" in context
    assert "用户画像" not in context
    assert "用户视角模型" not in context
    assert "【本用户命中】" not in context
    assert "【重点关注雷达】" not in context


def test_agenda_supervisor_aux_rule() -> None:
    """议程 supervisor 规则必须禁止辅助材料改变议题骨架。"""
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "### 辅助材料与议程骨架" in prompt
    assert "辅助材料不得成为新增、删除、改名、重排议题或改变议题归属的依据" in prompt
    assert "指出来自哪条辅助材料、应回到哪个议题" in prompt


def test_agenda_supervisor_skeleton_revise_rule() -> None:
    """决策指南必须包含议程骨架违规判定，且 .replace() 只命中一次。"""
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "议程骨架违规判定" in prompt
    assert "优先 revise" in prompt
    assert "返工点须具体到议题" in prompt
    assert prompt.count("议程骨架违规判定") == 1


def test_agenda_supervisor_skeleton_rule_not_in_normal() -> None:
    """普通 objective/personal supervisor prompt 不得被议程规则污染。"""
    for prompt in (
        MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
        MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    ):
        assert "议程骨架违规判定" not in prompt
        assert "### 辅助材料与议程骨架" not in prompt


def test_agenda_supervisor_context_checklist() -> None:
    """议程 supervisor context 必须带法定议题清单，且位于议题标记之后。"""
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    context = nodes._supervisor_context(state, "minutes")
    assert "【现场审定的有效议题清单】" in context
    assert "1. 议题：自研芯片二期量产（汇报人：张三）" in context
    assert context.index("议题模式：agenda_enhanced") < context.index(
        "【现场审定的有效议题清单】"
    )


def test_agenda_supervisor_checklist_after_marker() -> None:
    """15 个议题时，议题标记仍在前 20 行，清单不破坏议程模式识别。

    15 个议题已足以在“清单被误放到标记之前”时把标记挤出前 20 行
    （表头 3 行 + 空行 + 清单 16 行 + 空行 = 标记到第 22 行），
    同时又贴近真实会议的议题规模。
    """
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    state["valid_agendas"] = [
        ValidAgendaItem(seq=str(i), title=f"议题{i}", presenters=["张三"])
        for i in range(1, 16)
    ]
    context = nodes._supervisor_context(state, "minutes")
    marker_line = next(
        (
            i + 1
            for i, line in enumerate(context.splitlines())
            if line.strip() == "议题模式：agenda_enhanced"
        ),
        None,
    )
    assert marker_line is not None and marker_line <= 20
    assert is_agenda_enhanced_mode(context) is True
    assert "【现场审定的有效议题清单】" in context
    assert context.index("议题模式：agenda_enhanced") < context.index(
        "【现场审定的有效议题清单】"
    )
    assert "1. 议题：议题1（汇报人：张三）" in context
    assert "15. 议题：议题15（汇报人：张三）" in context


def test_normal_supervisor_context_has_no_personal_hit_radar() -> None:
    """Step 8：个人审核上下文保留送审稿 + 原文摘录，去掉命中/雷达/旧视角。"""
    nodes = _Nodes()
    context = nodes._supervisor_context(_normal_personal_state(), "minutes")
    assert "【现场审定的有效议题清单】" not in context
    assert "议题模式：agenda_enhanced" not in context
    assert "纪要草稿：" in context
    assert "原文（最高事实来源）：" in context
    assert "【本用户命中】" not in context
    assert "【重点关注雷达】" not in context
    assert "用户画像" not in context
    assert "用户视角模型" not in context


def test_supervisor_source_pack_include_profile_flag() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    without = nodes._supervisor_source_pack(
        state, "minutes", include_profile=False
    )
    assert "用户画像" not in without
    assert "用户视角模型" not in without
    with_profile = nodes._supervisor_source_pack(
        state, "minutes", include_profile=True
    )
    assert "用户画像" in with_profile
    assert "用户视角模型" in with_profile


def test_agenda_render_context_has_no_personal_blocks() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    context = nodes._render_context(state, "minutes")
    assert "现场审定的有效议题清单" in context
    assert "用户画像" not in context
    assert "已审核用户视角" not in context
    assert "【本用户命中】" not in context
    assert "【重点关注雷达】" not in context


def test_agenda_post_render_hook_skips_personal_normalization() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    rendered = "## 结论定调\n- **事项名称**：具体决议与指标要求\n"
    state["lines"]["minutes"]["rendered"] = rendered
    nodes._post_render_hook(state, "minutes")
    assert state["lines"]["minutes"]["rendered"] == rendered


def test_agenda_titles_are_objective() -> None:
    nodes = _Nodes()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    assert nodes._compute_title(state) == "客观会议纪要"
    assert nodes._line_title(state, "minutes") == "客观会议纪要"


def test_agenda_skips_perspective_for_single_line() -> None:
    nodes = _Nodes()
    called: list[dict] = []

    class FakePerspectiveAgent:
        async def run(self, *args, **kwargs):
            called.append(kwargs)
            return {"personal_summary": "should not run"}

    nodes.perspective_modeling_agent = FakePerspectiveAgent()
    state = _agenda_state(
        user={"name": "开发人员", "persona_type": "role_template"}
    )
    result = asyncio.run(nodes._make_perspective_node(["minutes"])(state))
    from domains.shared.perspective import EMPTY_PERSPECTIVE_MODELING

    assert result["perspective_profile"] == EMPTY_PERSPECTIVE_MODELING
    assert result["user_hits_block"] == ""
    assert result["user_radar_block"] == ""
    assert called == []


# ── 4. 记忆迁移止血 ─────────────────────────────────────────


def test_agenda_purge_is_skipped() -> None:
    draft = {
        "headline": "测试纪要",
        "executive_summary": [],
        "key_decisions": [
            "统一采用方案A作为网关鉴权方案，并补充灰度回滚机制",
            "前端渲染采用虚拟列表方案",
        ],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }
    out = enforce_minutes_draft(
        draft,
        {},
        is_agenda=True,
        memory_texts=["统一采用方案A作为网关鉴权方案"],
        transcript="【议题 01：网关鉴权】\n张三：方案A通过",
    )
    assert out["key_decisions"] == draft["key_decisions"]
    assert not any("往期沿革" in item for item in out["history_comparison"])


def test_normal_minutes_purge_unchanged() -> None:
    draft = {
        "headline": "测试纪要",
        "executive_summary": [],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }
    understanding = {
        "meeting_purpose": "测试",
        "decisions": ["往期决策"],
    }
    out = enforce_minutes_draft(
        draft,
        understanding,
        mode="objective",
        is_agenda=False,
        memory_texts=["往期决策"],
        transcript="本场没有这句话",
    )
    assert out["key_decisions"] == []
    assert any("往期沿革" in item for item in out["history_comparison"])


def test_minutes_agent_uses_explicit_source_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domains.meeting.models_generated import Minutes
    from domains.meeting.tasks.minutes.steps import minutes_agent as mod

    captured: dict = {}

    def fake_enforce(raw, understanding, **kwargs):
        captured.update(kwargs)
        return {
            "headline": "",
            "executive_summary": [],
            "key_decisions": [],
            "personally_relevant_points": [],
            "risks_and_blockers": [],
            "unresolved_questions": [],
            "history_comparison": [],
        }

    class FakeClient:
        async def structured(self, *args, **kwargs):
            return Minutes(headline="")

    monkeypatch.setattr(mod, "enforce_minutes_draft", fake_enforce)
    agent = mod.MinutesGenerationAgent(FakeClient())
    shared = (
        "视角模式：objective\n\n"
        "会议理解：\n{}\n\n"
        "会议原文：\n清单\n\n"
        "════════\n议题正文"
    )
    asyncio.run(
        agent.run(
            shared,
            view="objective",
            source_transcript="完整 tagged transcript",
        )
    )
    assert captured["transcript"] == "完整 tagged transcript"

    captured.clear()
    asyncio.run(agent.run(shared, view="objective"))
    assert captured["transcript"] != "完整 tagged transcript"
    assert "议题正文" not in captured["transcript"]
