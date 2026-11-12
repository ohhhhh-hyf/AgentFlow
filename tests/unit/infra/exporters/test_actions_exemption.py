"""测试 actions 任务线彻底豁免生成 actions.md 与 actions.html，并按开关落盘平铺 actions.json 与 actions_update.json。"""
from __future__ import annotations

import json
from pathlib import Path
from core.runner.context import load_domain
from infra.exporters.outputs import save_report_artifacts


def test_actions_exempted_from_md_and_html_and_saves_flat_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACTIONS_CALENDAR_BACKFILL", "off")
    ctx = load_domain("meeting", tmp_path)
    ctx.output_dir = tmp_path
    report_data = {
        "title": "待办清单",
        "actions": [
            {"title": "任务1", "item": "动作1", "owner": "张三", "deadline": "明天下午"},
            {"title": "任务2", "item": "动作2", "owner": "李四", "deadline": None},
        ],
        "personalized_text": '[{"title": "任务1", "item": "动作1"}]',
    }

    paths = save_report_artifacts(ctx, "actions", report_data)

    # 1. 绝对无 text (md) 或 html
    assert "text" not in paths
    assert "html" not in paths

    assert not (tmp_path / "actions.md").exists()
    assert not (tmp_path / "actions.html").exists()
    assert not (tmp_path / "result.md").exists()

    # 2. 开关为 off 时：仅生成平铺 actions.json，不生成 actions_update.json
    assert "actions_json" in paths
    assert "actions_update_json" not in paths
    assert (tmp_path / "actions.json").exists()
    assert not (tmp_path / "actions_update.json").exists()

    content = json.loads((tmp_path / "actions.json").read_text(encoding="utf-8"))
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["title"] == "任务1"
    assert content[0]["deadline"] == "明天下午"


def test_actions_saves_both_jsons_when_backfill_on(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACTIONS_CALENDAR_BACKFILL", "on")
    ctx = load_domain("meeting", tmp_path)
    ctx.output_dir = tmp_path
    report_data = {
        "title": "待办清单",
        "actions": [
            {
                "title": "任务1",
                "item": "动作1",
                "owner": "张三",
                "deadline": "2026-10-30T18:00:00",
                "deadline_raw": "明天下午",
                "deadline_display": "2026/10/30 下午",
            },
            {
                "title": "任务2",
                "item": "动作2",
                "owner": "李四",
                "deadline": None,
                "deadline_raw": None,
                "deadline_display": None,
            },
        ],
        "personalized_text": '[...]',
    }

    paths = save_report_artifacts(ctx, "actions", report_data)

    # 1. 绝不生成 md 或 html
    assert not (tmp_path / "actions.md").exists()
    assert not (tmp_path / "actions.html").exists()

    # 2. 开关为 on 时：同时生成平铺 actions.json 与 actions_update.json
    assert "actions_json" in paths
    assert "actions_update_json" in paths
    assert (tmp_path / "actions.json").exists()
    assert (tmp_path / "actions_update.json").exists()

    # actions.json 为纯净 7 字段（无 deadline_raw / deadline_display）
    raw_saved = json.loads((tmp_path / "actions.json").read_text(encoding="utf-8"))
    assert isinstance(raw_saved, list)
    assert raw_saved[0]["deadline"] == "明天下午"
    assert "deadline_raw" not in raw_saved[0]
    assert "deadline_display" not in raw_saved[0]

    # actions_update.json 包含增强字段
    updated_saved = json.loads((tmp_path / "actions_update.json").read_text(encoding="utf-8"))
    assert isinstance(updated_saved, list)
    assert updated_saved[0]["deadline"] == "2026-10-30T18:00:00"
    assert updated_saved[0]["deadline_display"] == "2026/10/30 下午"
    assert updated_saved[0]["deadline_raw"] == "明天下午"


def test_other_lines_still_generate_artifacts(tmp_path: Path) -> None:
    ctx = load_domain("meeting", tmp_path)
    ctx.output_dir = tmp_path
    report_data = {
        "title": "风险分析",
        "risks": [{"title": "风险1"}],
        "personalized_text": "# 风险分析\n\n- 风险1",
    }

    paths = save_report_artifacts(ctx, "risks", report_data)

    # 其它线（如 risks）仍正常生成
    assert "text" in paths
    assert paths["text"].exists()
    assert paths["text"].name == "risks.md"
