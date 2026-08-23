from __future__ import annotations

from pathlib import Path

from PIL import Image

from tools.ocr.levels import medium


class FakeVLM:
    def describe_image(self, image_path, prompt="", **kwargs):
        return """
        ```json
        {
          "is_double_page": true,
          "confidence": 0.91,
          "split_ratio": 0.5,
          "reading_order": ["左页", "右页"],
          "crop_plan": [
            {"id": "左页", "x1_ratio": 0, "y1_ratio": 0, "x2_ratio": 0.52, "y2_ratio": 1},
            {"id": "右页", "x1_ratio": 0.48, "y1_ratio": 0, "x2_ratio": 1, "y2_ratio": 1}
          ],
          "visual_hints": {
            "background_marked_regions": [
              {"location": "left page top", "confidence": 0.85},
              {"location": "right page middle", "confidence": 0.78}
            ]
          },
          "notes": ["双页"]
        }
        ```
        """


class FlakyVLM:
    def __init__(self):
        self.calls = 0

    def describe_image(self, image_path, prompt="", **kwargs):
        self.calls += 1
        if self.calls == 1:
            return "{not valid json"
        return FakeVLM().describe_image(image_path, prompt, **kwargs)


def test_parse_split_plan_normalizes_chinese_ids():
    plan = medium.parse_split_plan(FakeVLM().describe_image("x.jpg"))

    assert plan.is_double_page is True
    assert plan.confidence == 0.91
    assert plan.reading_order == ("left", "right")
    assert [region.id for region in plan.crop_plan] == ["left", "right"]
    assert plan.crop_plan[0].x2_ratio == 0.52
    assert plan.crop_plan[1].x1_ratio == 0.48
    assert plan.visual_hints["background_marked_regions"][0]["location"] == "left page top"
    assert plan.visual_hints["background_marked_regions"][0]["confidence"] == 0.85


def test_parse_split_plan_uses_center_default_when_crop_missing():
    plan = medium.parse_split_plan(
        '{"is_double_page": true, "confidence": 0.8, "reading_order": ["left", "right"]}'
    )

    assert plan.is_double_page is True
    assert [region.id for region in plan.crop_plan] == ["left", "right"]
    assert plan.crop_plan[0].x2_ratio == 0.515
    assert plan.crop_plan[1].x1_ratio == 0.485


def test_parse_split_plan_repairs_common_json_noise():
    noisy = """
    根据图片判断如下：
    {
      “is_double_page”: True,
      “confidence”: 0.77,
      “reading_order”: [“left”, “right”,],
      “crop_plan”: [
        {“id”: “left”, “x1_ratio”: 0, “y1_ratio”: 0, “x2_ratio”: 0.51, “y2_ratio”: 1,},
        {“id”: “right”, “x1_ratio”: 0.49, “y1_ratio”: 0, “x2_ratio”: 1, “y2_ratio”: 1,},
      ],
    }
    """

    plan = medium.parse_split_plan(noisy)

    assert plan.is_double_page is True
    assert plan.confidence == 0.77
    assert plan.reading_order == ("left", "right")
    assert [region.id for region in plan.crop_plan] == ["left", "right"]


def test_plan_double_page_split_retries_bad_json(tmp_path):
    image_path = tmp_path / "double.jpg"
    Image.new("RGB", (1000, 500), "white").save(image_path)
    vlm = FlakyVLM()

    plan = medium.plan_double_page_split(image_path, project_root=tmp_path, vlm_client=vlm)

    assert vlm.calls == 2
    assert plan.is_double_page is True


def test_run_medium_ocr_splits_pages_and_saves_outputs(tmp_path, monkeypatch):
    image_path = tmp_path / "double.jpg"
    Image.new("RGB", (1000, 500), "white").save(image_path)
    seen_lines = []

    def fake_recognize_image(path: str):
        name = Path(path).name
        text = "左页内容" if name.startswith("left") else "右页内容"
        return {"lines": [{"text": text, "conf": 0.99}]}

    def fake_reconstruct(lines):
        seen_lines.extend(lines)
        return "\n".join(str(item.get("text") or "") for item in lines if item.get("text"))

    def fake_review(markdown, lines):
        return f"审校版\n{markdown}", "ok"

    monkeypatch.setattr(medium, "recognize_image", fake_recognize_image)
    monkeypatch.setattr(medium, "reconstruct_markdown", fake_reconstruct)
    monkeypatch.setattr(medium, "review_markdown", fake_review)

    result = medium.run_medium_ocr(
        image_path,
        user_id="u1",
        subject="math",
        project_root=tmp_path,
        vlm_client=FakeVLM(),
    )

    assert result.fallback_reason == ""
    assert result.split_plan is not None
    assert "左页内容" in result.raw_text
    assert "右页内容" in result.raw_text
    assert "审校版" in result.reviewed_markdown
    assert "第 1 页" not in result.reviewed_markdown
    assert "第 2 页" not in result.reviewed_markdown
    assert [item.get("page_region") for item in seen_lines] == ["left", "right"]
    assert result.raw_text == "左页内容\n\n右页内容"
    assert result.raw_path.exists()
    assert result.reviewed_path.exists()
    assert len(result.debug_files) == 2
    assert all(path.exists() for path in result.debug_files)
    assert all(str(path) in result.files for path in result.debug_files)
    assert result.raw_path.parent == tmp_path / "data" / "u1" / "ocr" / "math" / "txt"
    assert result.reviewed_path.parent == tmp_path / "data" / "u1" / "ocr" / "math" / "md"
    assert result.debug_files[0].parent.parent == tmp_path / "data" / "u1" / "ocr" / "math" / "debug"
