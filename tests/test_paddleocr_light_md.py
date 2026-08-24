# -*- coding: utf-8 -*-
from PIL import Image

from tools.ocr.levels.light import run_light_ocr


def test_paddleocr_light_writes_combined_style_md(tmp_path, monkeypatch):
    image = tmp_path / "U202314751_15.jpg"
    Image.new("RGB", (32, 16), "white").save(image)

    def fake_recognize(path, **_kwargs):
        return "算符\n狄拉克符号", "", "", "# 算符\n\n狄拉克符号", "ok"

    monkeypatch.setenv("OCR_ENGINE", "paddleocr")
    monkeypatch.setattr(
        "tools.ocr.levels.light.server_ocr_image_recognize",
        fake_recognize,
    )
    result = run_light_ocr(
        image,
        user_id="1",
        subject="phy",
        project_root=tmp_path,
        output_stem="v1",
    )
    assert result.reviewed_path.name == "v1.md"
    text = result.reviewed_path.read_text(encoding="utf-8")
    assert "算符" in text
    assert "第 1 页" not in text
    assert not (tmp_path / "data" / "1" / "ocr" / "phy" / "txt" / "v1.txt").exists()
