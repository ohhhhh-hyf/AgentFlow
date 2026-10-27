from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domains.meeting.agenda_vision import (
    agenda_plan_to_markdown,
    extract_agenda_from_image_docs,
    vision_json_to_agenda_plan,
)
from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaPlan,
    _PARSED_AGENDA_RAW_CACHE,
)


def test_vision_json_to_agenda_plan_mapping():
    data = {
        "theme": "语音技术研讨会",
        "date_time": "2026-10-22",
        "attendees": ["高虹", "俞凯"],
        "agenda_items": [
            {
                "title": "开幕式致辞",
                "time_range": "09:00-09:30",
                "attendees": ["高虹"],  # 测试兼容模型输出的 attendees 键名
            },
            {
                "seq": "2",
                "title": "语音大模型前沿",
                "presenters": ["俞凯"],  # 测试标准的 presenters 键名
                "duration": "45min",
            },
        ],
    }

    plan = vision_json_to_agenda_plan(data)
    assert plan.meta.theme == "语音技术研讨会"
    assert plan.meta.date_time == "2026-10-22"
    assert plan.meta.attendees == "高虹；俞凯"

    assert len(plan.items) == 2
    assert plan.items[0].seq == "01"
    assert plan.items[0].title == "开幕式致辞"
    assert plan.items[0].presenters == ["高虹"]
    assert plan.items[0].time_range == "09:00-09:30"

    assert plan.items[1].seq == "02"
    assert plan.items[1].title == "语音大模型前沿"
    assert plan.items[1].presenters == ["俞凯"]
    assert plan.items[1].duration == "45min"


def test_vision_json_english_presenters_not_split():
    """VLM 返回字符串型英文姓名时，不能被空格拆成两个人。"""
    data = {
        "theme": "Architecture Review",
        "attendees": "Alice Chen, Bob Lee",
        "agenda_items": [
            {"seq": "01", "title": "Architecture Review", "presenters": "Alice Chen, Bob Lee"},
            {"seq": "02", "title": "Release Plan", "presenters": "Carol Wu and Dave Park"},
        ],
    }
    plan = vision_json_to_agenda_plan(data)
    assert plan.meta.attendees == "Alice Chen；Bob Lee"
    assert plan.items[0].presenters == ["Alice Chen", "Bob Lee"]
    assert plan.items[1].presenters == ["Carol Wu", "Dave Park"]


def test_vision_json_mixed_cn_en_names():
    """中英混排名单：中文多人名与英文全名都要保持正确。"""
    data = {
        "attendees": ["张三", "Alice Chen"],
        "agenda_items": [
            {"title": "混合议题", "presenters": "张三；Alice Chen"},
        ],
    }
    plan = vision_json_to_agenda_plan(data)
    assert plan.meta.attendees == "张三；Alice Chen"
    assert plan.items[0].presenters == ["张三", "Alice Chen"]


def test_vision_json_string_attendees_chinese():
    """字符串型中文名单仍按原有空格/分号规则拆分。"""
    data = {
        "attendees": "高虹；俞凯",
        "agenda_items": [
            {"title": "语音技术研讨", "presenters": "张三 李四"},
        ],
    }
    plan = vision_json_to_agenda_plan(data)
    assert plan.meta.attendees == "高虹；俞凯"
    assert plan.items[0].presenters == ["张三", "李四"]


def test_agenda_plan_to_markdown():
    data = {
        "theme": "芯片进度例会",
        "date_time": "2026-10-22 14:00",
        "attendees": ["张三", "李四"],
        "agenda_items": [
            {"seq": "01", "title": "良率提升汇报", "presenters": ["张三"], "time_range": "14:00-14:30"}
        ],
    }
    plan = vision_json_to_agenda_plan(data)
    md = agenda_plan_to_markdown(plan)

    assert "**会议主题**：芯片进度例会" in md
    assert "**会议时间**：2026-10-22 14:00" in md
    assert "**全程与会人/主持人**：张三；李四" in md
    assert "| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |" in md
    assert "| 01 | 良率提升汇报 | 张三 | 14:00-14:30 |" in md


def test_extract_agenda_primary_channel_vlm_success(tmp_path):
    img1 = tmp_path / "agenda_p1.png"
    img1.write_bytes(b"dummy_img_bytes")

    mock_vlm_client = MagicMock()
    mock_vlm_client.extract_agenda.return_value = {
        "theme": "技术年会",
        "date_time": "2026-10-22",
        "attendees": ["王五"],
        "agenda_items": [
            {"seq": "01", "title": "声学技术突破", "presenters": ["王五"], "time_range": "09:00-10:00"}
        ],
    }

    with patch("domains.meeting.agenda_vision.ocr_fallback_single_agenda_doc") as mock_ocr_fallback:
        plan, md = extract_agenda_from_image_docs(
            image_paths=[img1],
            vlm_client=mock_vlm_client,
        )

        assert plan is not None
        assert len(plan.items) == 1
        assert plan.items[0].title == "声学技术突破"
        assert "声学技术突破" in md
        # 验证主通道成功时，绝对不调用 OCR 兜底
        mock_ocr_fallback.assert_not_called()
        # 验证结果已存入 raw_cache
        assert md in _PARSED_AGENDA_RAW_CACHE


def test_extract_agenda_fallback_channel_when_vlm_fails(tmp_path):
    img1 = tmp_path / "agenda_p1.png"
    img1.write_bytes(b"dummy_img_bytes")

    # 模拟视觉接口重试 3 次后仍返回 None
    mock_vlm_client = MagicMock()
    mock_vlm_client.extract_agenda.return_value = None

    fallback_plan_obj = AgendaPlan(
        items=[
            MagicMock(seq="01", title="OCR兜底识别议题", presenters=["赵六"], raw_presenter="赵六", duration="30min")
        ]
    )

    with patch(
        "domains.meeting.agenda_vision.ocr_fallback_single_agenda_doc",
        return_value=(fallback_plan_obj, "| 01 | OCR兜底识别议题 | 赵六 | 30min |"),
    ) as mock_ocr_fallback:
        plan, md = extract_agenda_from_image_docs(
            image_paths=[img1],
            vlm_client=mock_vlm_client,
        )

        assert plan is not None
        assert "OCR兜底识别议题" in md
        # 验证在 VLM 失败时，无缝且确定地触发了传统 OCR 兜底
        mock_ocr_fallback.assert_called_once()


def test_extract_agenda_from_image_docs_forwards_lang(tmp_path):
    img = tmp_path / "agenda_en.png"
    img.write_bytes(b"dummy")

    mock_vlm_client = MagicMock()
    mock_vlm_client.extract_agenda.return_value = {
        "agenda_items": [
            {
                "seq": "01",
                "title": "Cloud Migration",
                "presenters": ["Alice"],
            }
        ]
    }

    with patch(
        "domains.meeting.agenda_vision.ocr_fallback_single_agenda_doc"
    ) as mock_ocr_fallback:
        plan, md = extract_agenda_from_image_docs(
            image_paths=[img],
            vlm_client=mock_vlm_client,
            lang="en",
        )

    assert plan is not None
    assert plan.items[0].title == "Cloud Migration"
    mock_vlm_client.extract_agenda.assert_called_once_with(
        img, max_retries=3, lang="en"
    )
    mock_ocr_fallback.assert_not_called()
