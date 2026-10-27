from __future__ import annotations

import json
from unittest.mock import patch

from infra.vlm.agenda_client import (
    AGENDA_VISION_EN_TAIL,
    AGENDA_VISION_PROMPT,
    AgendaVisionClient,
    build_agenda_vision_prompt,
    calc_sign,
    safe_load_json,
)


def test_calc_sign():
    query = {"bId": "test_b", "flowId": "test_f", "uuId": "12345"}
    path = ["predict"]
    signkey = "TEST_KEY_12345"
    appid = "test_app"
    data = '{"test": 1}'
    ts, sign = calc_sign(data, signkey, query, path, "POST", appid, mode="easy")
    assert isinstance(ts, int)
    assert isinstance(sign, str)
    assert len(sign) > 10


def test_safe_load_json():
    # 1. 正常标准 JSON
    raw1 = '{"theme": "全员会", "agenda_items": [{"title": "议题1"}]}'
    res1 = safe_load_json(raw1)
    assert res1["theme"] == "全员会"
    assert len(res1["agenda_items"]) == 1

    # 2. 带 Markdown 代码块的 JSON
    raw2 = '```json\n{"theme": "技术会", "agenda_items": []}\n```'
    res2 = safe_load_json(raw2)
    assert res2["theme"] == "技术会"

    # 3. 缺失结尾闭合括号的 JSON 自动修复
    raw3 = '{"theme": "未闭合", "agenda_items": [{"title": "议题A"}'
    res3 = safe_load_json(raw3)
    assert res3.get("theme") == "未闭合"

    # 4. 彻底损坏的 JSON 返回 parse_error
    raw4 = "这是一段完全无法解析的纯文本内容"
    res4 = safe_load_json(raw4)
    assert res4.get("parse_error") == "JSON_INCOMPLETE"


def test_agenda_vision_client_retry_and_success(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00")  # minimal fake jpg

    client = AgendaVisionClient(endpoint_url="http://mock-server/predict", timeout=5)

    # 模拟第 1 次网络异常，第 2 次成功返回有效数据
    mock_success_data = {
        "theme": "季度战略会",
        "date_time": "2026-10-22",
        "attendees": ["张三", "李四"],
        "agenda_items": [
            {"seq": "01", "title": "战略落地汇报", "presenters": ["张三"], "time_range": "09:00-10:00"}
        ],
    }

    calls = [0]

    def mock_predict(img_path, prompt_id, lang="zh"):
        calls[0] += 1
        if calls[0] == 1:
            raise ConnectionError("Temporary connection timeout")
        return 200, mock_success_data

    with patch.object(client, "_predict_once", side_effect=mock_predict):
        res = client.extract_agenda(img, max_retries=3, retry_delay=0.01)
        assert res is not None
        assert res["theme"] == "季度战略会"
        assert len(res["agenda_items"]) == 1
        assert calls[0] == 2  # 验证确实发生了第 2 次重试并成功


def test_agenda_vision_client_all_retries_fail_returns_none(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_text("dummy")

    client = AgendaVisionClient(endpoint_url="http://mock-server/predict", timeout=5)

    calls = [0]

    def mock_predict(img_path, prompt_id, lang="zh"):
        calls[0] += 1
        return 500, {"parse_error": "HTTP_500"}

    with patch.object(client, "_predict_once", side_effect=mock_predict):
        res = client.extract_agenda(img, max_retries=3, retry_delay=0.01)
        assert res is None  # 验证 3 次重试失败后安全降级返回 None
        assert calls[0] == 3


def test_build_agenda_vision_prompt_defaults_to_zh():
    for lang in (None, "", "zh", "ZH", "fr"):
        assert build_agenda_vision_prompt(lang) == AGENDA_VISION_PROMPT


def test_build_agenda_vision_prompt_en():
    prompt = build_agenda_vision_prompt("en")
    assert prompt.startswith("你是一名「英文会议议程与日程结构化解析专家」。")
    assert AGENDA_VISION_EN_TAIL in prompt
    assert "【字段定义】" in prompt
    assert "【提纯与清洗规约】" in prompt
    assert "【输出约束】" in prompt
    assert "Professor" in prompt
    assert "Registration" in prompt
    assert "JSON 字段名保持英文原样" in prompt
    assert "texts" not in prompt
    assert "四字段" not in prompt


def test_en_prompt_english_rules_before_output_constraints():
    prompt = build_agenda_vision_prompt("en")
    assert prompt.index("【英文识别规约】") < prompt.index("【输出约束】")
    assert prompt.rstrip().endswith(
        '{"theme": null, "date_time": null, "attendees": [], "agenda_items": []}'
    )


def test_extract_agenda_forwards_lang_to_predict_once(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"dummy")
    client = AgendaVisionClient(endpoint_url="http://mock-server/predict", timeout=5)
    captured: dict = {}

    def mock_predict(img_path, prompt_id, lang="zh"):
        captured["lang"] = lang
        return 200, {"agenda_items": [{"title": "Topic A"}]}

    with patch.object(client, "_predict_once", side_effect=mock_predict):
        res = client.extract_agenda(img, max_retries=1, lang="en")

    assert res is not None
    assert captured["lang"] == "en"


def test_predict_once_payload_uses_lang_prompt(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"dummy")
    client = AgendaVisionClient(endpoint_url="http://mock-server/predict", timeout=5)
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = '{"agenda_items": [{"title": "Topic A"}]}'

    def fake_post(self, url, data=None, headers=None, **kwargs):
        captured["payload"] = json.loads(data.decode("utf-8"))
        return FakeResponse()

    with patch("requests.Session.post", fake_post), patch(
        "infra.vlm.agenda_client.img2b64_string", return_value="fakeb64"
    ):
        status, result = client._predict_once(
            img, prompt_id="AGENDA_VISION", lang="en"
        )

    assert status == 200
    assert result["agenda_items"][0]["title"] == "Topic A"
    assert captured["payload"]["data"]["promptId"] == "AGENDA_VISION"
    assert captured["payload"]["data"]["prompt"] == build_agenda_vision_prompt("en")
