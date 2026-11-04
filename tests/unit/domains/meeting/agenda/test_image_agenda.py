from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas import TaskRequest
from app.tasks import _prepare
from domains.meeting.agenda_vision import AgendaPlan


def test_prepare_agenda_minutes_with_vlm_image(tmp_path, monkeypatch):
    img_path = tmp_path / "agenda_img.png"
    img_path.write_bytes(b"dummy")

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: img_path)

    mock_vlm_data = {
        "theme": "技术年会",
        "date_time": "2026-10-22",
        "attendees": ["高虹", "俞凯"],
        "agenda_items": [
            {"seq": "01", "title": "语音模仿与鉴别", "presenters": ["陶建华"], "time_range": "09:30-10:15"}
        ],
    }

    mock_client = MagicMock()
    mock_client.extract_agenda.return_value = mock_vlm_data

    with patch("domains.meeting.agenda_vision.AgendaVisionClient", return_value=mock_client):
        req = TaskRequest(
            texts={"transcript": "陶建华 09:30\n我们在语音模仿与鉴别领域取得了新进展。"},
            docs=["agenda_img.png"],
        )
        prep = _prepare(domain="meeting", task="agenda_minutes", req=req, user_id="1")
        assert "agenda_minutes" in prep.extra_line_inputs
        agenda_val = prep.extra_line_inputs["agenda_minutes"]
        assert "语音模仿与鉴别" in agenda_val
        assert "陶建华" in agenda_val


def test_prepare_minutes_with_vlm_image_enhanced_mode(tmp_path, monkeypatch):
    img_path = tmp_path / "agenda_img.png"
    img_path.write_bytes(b"dummy")

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: img_path)

    mock_vlm_data = {
        "theme": "语音技术研讨",
        "date_time": "2026-10-22",
        "attendees": ["高虹", "陶建华"],
        "agenda_items": [
            {"seq": "01", "title": "语音模仿与鉴别", "presenters": ["陶建华"], "time_range": "09:30-10:15"}
        ],
    }

    mock_client = MagicMock()
    mock_client.extract_agenda.return_value = mock_vlm_data

    with patch("domains.meeting.agenda_vision.AgendaVisionClient", return_value=mock_client):
        req = TaskRequest(
            texts={"transcript": "陶建华 09:30\n我们在语音模仿与鉴别技术取得了突破。"},
            docs=["agenda_img.png"],
        )
        prep = _prepare(domain="meeting", task="minutes", req=req, user_id="1")
        assert "agenda_text" in prep.extra_line_inputs
        assert "语音模仿与鉴别" in prep.extra_line_inputs["agenda_text"]


def test_prepare_minutes_with_vlm_fallback_to_ocr(tmp_path, monkeypatch):
    img_path = tmp_path / "agenda_img.png"
    img_path.write_bytes(b"dummy")

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: img_path)

    # 模拟 VLM 重试 3 次后返回 None
    mock_client = MagicMock()
    mock_client.extract_agenda.return_value = None

    fallback_plan = AgendaPlan()
    fallback_text = "| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |\n| :--- | :--- | :--- | :--- |\n| 01 | 自研芯片量产汇报 | 张三 | 09:00-10:00 |"

    with patch("domains.meeting.agenda_vision.AgendaVisionClient", return_value=mock_client), patch(
        "domains.meeting.agenda_vision.ocr_fallback_single_agenda_doc",
        return_value=(fallback_plan, fallback_text),
    ):
        req = TaskRequest(
            texts={"transcript": "张三 09:00\n自研芯片量产良率达到了预期标准。"},
            docs=["agenda_img.png"],
        )
        prep = _prepare(domain="meeting", task="minutes", req=req, user_id="1")
        assert "agenda_text" in prep.extra_line_inputs
        assert "自研芯片量产汇报" in prep.extra_line_inputs["agenda_text"]
