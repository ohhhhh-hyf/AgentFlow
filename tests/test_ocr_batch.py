# -*- coding: utf-8 -*-
import time

from tools.ocr.levels.light import (
    LIGHT_OCR_BATCH,
    OCR_PARALLEL,
    combine_ocr_pages,
    concat_page_lines,
    iter_ocr_review_pipeline,
    next_batch_version_stem,
    reconstruct_and_review_pages,
    save_combined_ocr_outputs,
)


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


def test_pipeline_runs_next_batch_only_after_review():
    stamps: list[tuple[str, float]] = []

    def ocr_fn(path):
        stamps.append((f"ocr:{path}", time.perf_counter()))
        return f"raw-{path}", [{"text": str(path)}]

    def review_fn(pages):
        stamps.append(("review:" + "|".join(item["name"] for item in pages), time.perf_counter()))
        time.sleep(0.05)
        return "|".join(item["name"] for item in pages)

    entries = [(f"im{i}", f"im{i}") for i in range(4)]
    done = [
        event["reviewed"]
        for event in iter_ocr_review_pipeline(
            entries,
            ocr_fn=ocr_fn,
            review_fn=review_fn,
            batch_size=2,
        )
        if event["type"] == "batch_done"
    ]
    assert done == ["im0|im1", "im2|im3"]
    names = [item[0] for item in stamps]
    assert names.index("review:im0|im1") < names.index("ocr:im2")
    assert names.index("review:im0|im1") < names.index("ocr:im3")


def test_pipeline_skips_failed_image_and_continues():
    def ocr_fn(path):
        if str(path) == "im1":
            raise RuntimeError()
        return f"raw-{path}", [{"text": str(path)}]

    def review_fn(pages):
        return "|".join(item["name"] for item in pages)

    events = list(
        iter_ocr_review_pipeline(
            [("im0", "im0"), ("im1", "im1")],
            ocr_fn=ocr_fn,
            review_fn=review_fn,
            batch_size=2,
        )
    )
    fails = [event for event in events if event["type"] == "ocr_fail"]
    done = [event for event in events if event["type"] == "batch_done"]
    assert len(fails) == 1
    assert "RuntimeError" in str(fails[0].get("error") or "")
    assert done and "im0" in done[0]["reviewed"]
    assert "im1" in done[0]["reviewed"]


def test_pipeline_times_out_stuck_ocr_without_aborting():
    def ocr_fn(path):
        if str(path) == "slow":
            time.sleep(2)
        return f"raw-{path}", [{"text": str(path)}]

    def review_fn(pages):
        return "|".join(item["name"] for item in pages)

    events = list(
        iter_ocr_review_pipeline(
            [("fast", "fast"), ("slow", "slow")],
            ocr_fn=ocr_fn,
            review_fn=review_fn,
            batch_size=2,
            item_timeout=0.3,
        )
    )
    fails = [event for event in events if event["type"] == "ocr_fail"]
    done = [event for event in events if event["type"] == "batch_done"]
    assert fails and "超时" in str(fails[0].get("error") or "")
    assert done
