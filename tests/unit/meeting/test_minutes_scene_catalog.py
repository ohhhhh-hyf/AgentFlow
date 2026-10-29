"""Stage 1：场景目录、候选集、Prompt 组装与指南同步。"""
from __future__ import annotations

import re
from pathlib import Path

from domains.meeting.tasks.minutes.steps.scene_catalog import (
    AGENDA_CANDIDATE_IDS,
    NORMAL_CANDIDATE_IDS,
    SCENE_BY_ID,
    SCENE_CATALOG,
    SYSTEM_PROMPT_TEMPLATE,
    TEMPLATE_CLASSIFIER_PROMPT_VERSION,
    build_candidate_block,
    build_system_prompt,
    build_user_message,
    candidate_ids_for_mode,
)

_GUIDE = Path(__file__).resolve().parents[3] / "MINUTES_SCENE_AGENT_PROMPT_GUIDE.md"


def _guide_text() -> str:
    return _GUIDE.read_text(encoding="utf-8")


def _guide_block(heading: str) -> str:
    text = _guide_text()
    start = text.index(heading)
    match = re.search(r"```text\n(.*?)```", text[start:], re.S)
    assert match, f"指南中未找到代码块：{heading}"
    return match.group(1).strip()


def test_catalog_counts_and_uniqueness() -> None:
    assert len(SCENE_CATALOG) == 29
    assert len(NORMAL_CANDIDATE_IDS) == 29
    assert len(AGENDA_CANDIDATE_IDS) == 20
    assert len(SCENE_BY_ID) == 29
    assert len(set(NORMAL_CANDIDATE_IDS)) == 29
    assert set(AGENDA_CANDIDATE_IDS) <= set(NORMAL_CANDIDATE_IDS)
    assert sum(1 for entry in SCENE_CATALOG if entry.has_agenda) == 20


def test_candidate_selection_by_mode() -> None:
    assert candidate_ids_for_mode("normal") == NORMAL_CANDIDATE_IDS
    assert candidate_ids_for_mode("agenda") == AGENDA_CANDIDATE_IDS
    assert candidate_ids_for_mode("") == NORMAL_CANDIDATE_IDS
    assert candidate_ids_for_mode("unknown") == NORMAL_CANDIDATE_IDS


def test_catalog_matches_guide_tables() -> None:
    rows = re.findall(
        r"^\| `([a-z_]+)` \| ([^|]+) \| (.+) \|$", _guide_text(), re.M
    )
    assert len(rows) == 29
    guide = {id_: (name.strip(), desc.strip()) for id_, name, desc in rows}
    assert set(guide) == set(SCENE_BY_ID)
    for entry in SCENE_CATALOG:
        assert guide[entry.id] == (entry.name, entry.description)


def test_candidate_blocks_match_guide() -> None:
    normal_block = _guide_block("### 3. 候选场景块（29 条，可直接拼入 prompt）")
    agenda_block = _guide_block("### 3. 候选场景块（20 条，可直接拼入 prompt）")
    assert normal_block == build_candidate_block(NORMAL_CANDIDATE_IDS)
    assert agenda_block == build_candidate_block(AGENDA_CANDIDATE_IDS)


def test_system_prompt_template_matches_guide() -> None:
    guide_prompt = _guide_block("## 四、共用 System Prompt")
    assert guide_prompt == SYSTEM_PROMPT_TEMPLATE.strip()


def test_build_system_prompt_inserts_only_candidates() -> None:
    normal = build_system_prompt(NORMAL_CANDIDATE_IDS)
    agenda = build_system_prompt(AGENDA_CANDIDATE_IDS)
    assert "{{CANDIDATE_SCENES}}" not in normal
    assert len(re.findall(r"^- [a-z_]+（", normal, re.M)) == 29
    assert len(re.findall(r"^- [a-z_]+（", agenda, re.M)) == 20
    assert "- project_progress（项目进度会）" in normal
    assert "- clinical_advisory（就医咨询）" not in agenda


def test_build_user_message_normal_and_agenda() -> None:
    normal = build_user_message("会议内容")
    assert normal == "【待检测文本】\n会议内容"

    agenda = build_user_message("会议内容", "1. 议题：定价\n2. 议题：排期")
    assert agenda.startswith("【现场审定的有效议题清单】\n1. 议题：定价")
    assert "【待检测文本】\n会议内容" in agenda


def test_build_candidate_block_rejects_unknown_id() -> None:
    try:
        build_candidate_block(["not_a_template"])
    except ValueError as exc:
        assert "not_a_template" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("未知 ID 应该抛出 ValueError")


def test_prompt_version() -> None:
    assert TEMPLATE_CLASSIFIER_PROMPT_VERSION == "scene-v1"
