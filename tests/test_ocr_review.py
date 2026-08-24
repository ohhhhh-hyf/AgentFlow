from tools.ocr.reconstruct import (
    _as_reviewed_markdown,
    _number_draft_lines,
    apply_review_patches,
)


def test_number_draft_lines_uses_visible_indexes():
    numbered = _number_draft_lines("# 导数\n\n其中 sln x")
    assert numbered.splitlines()[0].startswith("L001:")
    assert numbered.splitlines()[2] == "L003: 其中 sln x"


def test_empty_patches_keep_draft():
    draft = "# 导数\n\n定义。"
    reviewed, notes = apply_review_patches(draft, [])
    assert reviewed == draft
    assert "未发现" in notes


def test_whole_line_patch_replaces_matching_line():
    draft = "# 导数\n其中 sln x → 0\n结束"
    reviewed, notes = apply_review_patches(
        draft,
        [{"line": 2, "from": "其中 sln x → 0", "to": "其中 sin x → 0"}],
    )
    assert reviewed.splitlines()[1] == "其中 sin x → 0"
    assert reviewed.splitlines()[0] == "# 导数"
    assert "L2 已替换" in notes


def test_mismatch_skips_and_keeps_line():
    draft = "# 导数\n其中 sln x → 0"
    reviewed, notes = apply_review_patches(
        draft,
        [{"line": 2, "from": "完全不是这行", "to": "其中 sin x → 0"}],
    )
    assert reviewed == draft
    assert "原文不匹配" in notes


def test_substring_patch_only_on_that_line():
    draft = "sln 出现一次\n另一行也有 sln"
    reviewed, _notes = apply_review_patches(
        draft,
        [{"line": 1, "from": "sln", "to": "sin"}],
    )
    assert reviewed.splitlines() == ["sin 出现一次", "另一行也有 sln"]


def test_multiline_merge_patch():
    draft = "alpha\n$$\nE=mc\n$$\nomega"
    reviewed, notes = apply_review_patches(
        draft,
        [{"line": 2, "end": 4, "from": "$$\nE=mc\n$$", "to": "$$E=mc^2$$"}],
    )
    assert reviewed.splitlines() == ["alpha", "$$E=mc^2$$", "omega"]
    assert "L2-4 已替换" in notes


def test_apply_from_bottom_so_earlier_lines_stay():
    draft = "sln\n中段\n1im"
    reviewed, _notes = apply_review_patches(
        draft,
        [
            {"line": 1, "from": "sln", "to": "sin"},
            {"line": 3, "from": "1im", "to": "lim"},
        ],
    )
    assert reviewed.splitlines() == ["sin", "中段", "lim"]


def test_as_reviewed_markdown_applies_json_patches():
    draft = "# 旧稿\n其中 sln"
    payload = '{"patches":[{"line":2,"from":"其中 sln","to":"其中 sin"}]}'
    reviewed, notes = _as_reviewed_markdown(payload, draft)
    assert "其中 sin" in reviewed
    assert "已替换" in notes


def test_as_reviewed_markdown_empty_patches():
    draft = "# 重构稿"
    reviewed, notes = _as_reviewed_markdown('{"patches":[]}', draft)
    assert reviewed == draft
    assert "未发现" in notes


def test_as_reviewed_markdown_keeps_draft_on_truncated_json():
    draft = "# 完整重构稿\n" * 20
    truncated = '{"patches":[{"line":1,"from":"# 导数","to":"'
    reviewed, notes = _as_reviewed_markdown(truncated, draft)
    assert reviewed == draft
    assert "未返回补丁" in notes


def test_as_reviewed_markdown_ignores_full_markdown_rewrite():
    draft = "# 重构稿"
    reviewed, notes = _as_reviewed_markdown("# 审校后的全文\n不该整篇替换", draft)
    assert reviewed == draft
    assert "未返回补丁" in notes


def test_as_reviewed_markdown_empty_keeps_draft():
    draft = "# 重构稿"
    reviewed, notes = _as_reviewed_markdown("   ", draft)
    assert reviewed == draft
    assert "为空" in notes


def test_as_reviewed_markdown_strips_json_fence():
    draft = "其中 sln"
    payload = "```json\n{\"patches\":[{\"line\":1,\"from\":\"其中 sln\",\"to\":\"其中 sin\"}]}\n```"
    reviewed, _notes = _as_reviewed_markdown(payload, draft)
    assert reviewed == "其中 sin"
