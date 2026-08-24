# -*- coding: utf-8 -*-
import json

from tools.ocr.levels.light import (
    LIGHT_OCR_BATCH,
    OCR_PARALLEL,
    combine_ocr_pages,
    concat_page_lines,
    next_batch_version_stem,
    reconstruct_and_review_pages,
    save_combined_ocr_outputs,
)
from tools.ocr.levels.standard import combine_page_visuals, save_combined_meta


def test_version_stem_starts_at_v1(tmp_path):
    assert next_batch_version_stem("1", "phy", tmp_path) == "v1"


def test_version_stem_increments_for_same_user_subject(tmp_path):
    first = save_combined_ocr_outputs(
        [
            {"name": "a.jpg", "raw_text": "raw-a", "reviewed_markdown": "# A"},
            {"name": "b.jpg", "raw_text": "raw-b", "reviewed_markdown": "# B"},
        ],
        user_id="1",
        subject="phy",
        project_root=tmp_path,
    )
    second = save_combined_ocr_outputs(
        [
            {"name": "c.jpg", "raw_text": "raw-c", "reviewed_markdown": "# C"},
            {"name": "d.jpg", "raw_text": "raw-d", "reviewed_markdown": "# D"},
        ],
        user_id="1",
        subject="phy",
        project_root=tmp_path,
    )
    other = save_combined_ocr_outputs(
        [
            {"name": "e.jpg", "raw_text": "raw-e", "reviewed_markdown": "# E"},
            {"name": "f.jpg", "raw_text": "raw-f", "reviewed_markdown": "# F"},
        ],
        user_id="1",
        subject="math",
        project_root=tmp_path,
    )
    assert first.reviewed_path is not None
    assert first.reviewed_path.name == "v1.md"
    assert first.files == [str(first.reviewed_path)]
    assert second.reviewed_path.name == "v2.md"
    assert other.reviewed_path.name == "v1.md"
    assert not (tmp_path / "data" / "1" / "ocr" / "phy" / "txt" / "v1.txt").exists()
    md = first.reviewed_path.read_text(encoding="utf-8")
    assert md.index("# A") < md.index("# B")
    assert "第 1 页" not in md
    assert combine_ocr_pages(
        [{"name": "a.jpg", "reviewed_markdown": "x"}],
        key="reviewed_markdown",
    ) == "x"
    assert combine_ocr_pages(
        [{"reviewed_markdown": "<!-- 第 9 页：U202314751_9.jpg -->\n# 算符"}],
        key="reviewed_markdown",
    ) == "# 算符"


def test_combined_meta_regenerates_from_full_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr("domain.notes.tasks.catalog.store.PROJECT_ROOT", tmp_path)
    captured: dict = {}

    def fake_generate(raw_text, reviewed_markdown, visual, project_root, **kwargs):
        captured["raw"] = raw_text
        captured["md"] = reviewed_markdown
        captured["visual"] = visual
        captured["kwargs"] = kwargs
        return {
            "catalog_hints": [{"title": "算符", "level": "1"}],
            "knowledge_points": [{"title": "右矢", "topic": "狄拉克符号"}],
        }

    monkeypatch.setattr("tools.ocr.levels.standard._generate_meta", fake_generate)
    pages = [
        {
            "name": "a.jpg",
            "raw_text": "raw-a",
            "reviewed_markdown": "# A",
            "visual": {
                "reading_order": ["算符"],
                "regions": [{"role": "title", "text": "算符", "level": 1}],
            },
        },
        {
            "name": "b.jpg",
            "raw_text": "raw-b",
            "reviewed_markdown": "# B",
            "visual": {
                "reading_order": ["基矢"],
                "regions": [{"role": "title", "text": "基矢", "level": 2}],
            },
        },
    ]
    stem = next_batch_version_stem("1", "phy", tmp_path)
    combined = save_combined_ocr_outputs(
        pages,
        user_id="1",
        subject="phy",
        project_root=tmp_path,
        output_stem=stem,
    )
    meta_path = save_combined_meta(
        raw_text=combined.raw_text,
        reviewed_markdown=combined.reviewed_markdown,
        pages=pages,
        user_id="1",
        output_stem=stem,
        project_root=tmp_path,
    )
    assert combined.reviewed_path.name == "v1.md"
    assert meta_path.name == "v1_meta.json"
    assert captured["md"].index("# A") < captured["md"].index("# B")
    assert "第 1 页" not in captured["md"]
    assert captured["kwargs"].get("max_hints") == 24
    visual = combine_page_visuals(pages)
    assert visual["reading_order"][0].startswith("第1页")
    assert visual["reading_order"][1].startswith("第2页")


def test_light_batch_size_is_four():
    assert OCR_PARALLEL == 4
    assert LIGHT_OCR_BATCH == 4
    assert list(range(0, 20, LIGHT_OCR_BATCH)) == [0, 4, 8, 12, 16]


def test_concat_page_lines_keeps_order_and_offsets_y():
    pages = [
        {
            "lines": [
                {
                    "text": "左页",
                    "bbox": [[0, 10], [40, 10], [40, 20], [0, 20]],
                    "layout": {"top": 10},
                }
            ]
        },
        {
            "lines": [
                {
                    "text": "右页",
                    "bbox": [[0, 10], [40, 10], [40, 20], [0, 20]],
                    "layout": {"top": 10},
                }
            ]
        },
    ]
    lines = concat_page_lines(pages)
    assert [item["text"] for item in lines] == ["左页", "右页"]
    assert lines[1]["layout"]["top"] > lines[0]["layout"]["top"]
    assert lines[1]["bbox"][0][1] > lines[0]["bbox"][0][1]


def test_reconstruct_and_review_pages_runs_once_each_in_order(monkeypatch):
    calls: list = []

    def fake_reconstruct(lines, **kwargs):
        calls.append(("reconstruct", [item.get("text") for item in lines], kwargs.get("max_tokens")))
        return "# " + " / ".join(item.get("text") or "" for item in lines)

    def fake_review(markdown, lines, **kwargs):
        calls.append(("review", markdown, [item.get("text") for item in lines], kwargs.get("max_tokens")))
        return markdown + "\n审校", "ok"

    monkeypatch.setattr("tools.ocr.levels.light.reconstruct_markdown", fake_reconstruct)
    monkeypatch.setattr("tools.ocr.levels.light.review_markdown", fake_review)
    text = reconstruct_and_review_pages(
        [
            {"lines": [{"text": "波函数"}]},
            {"lines": [{"text": "宇称"}]},
        ]
    )
    assert [item[0] for item in calls] == ["reconstruct", "review"]
    assert calls[0][1] == ["波函数", "宇称"]
    assert calls[1][2] == ["波函数", "宇称"]
    assert text.index("波函数") < text.index("宇称")
    assert "审校" in text
    assert "第 1 页" not in text
