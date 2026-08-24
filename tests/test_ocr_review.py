from tools.ocr.reconstruct import _as_reviewed_markdown


def test_review_accepts_plain_markdown():
    draft = "# 导数\n\n定义：..."
    reviewed, notes = _as_reviewed_markdown("# 导数\n\n定义：极限。", draft)
    assert reviewed.startswith("# 导数")
    assert "极限" in reviewed
    assert "已完成" in notes


def test_review_strips_markdown_fence():
    draft = "# 标题"
    reviewed, _notes = _as_reviewed_markdown("```markdown\n# 标题\n正文\n```", draft)
    assert reviewed == "# 标题\n正文"


def test_review_keeps_draft_on_truncated_json():
    draft = "# 完整重构稿\n" * 20
    truncated = '{\n  "markdown": "# 导数\n\n正文开始后被截断'
    reviewed, notes = _as_reviewed_markdown(truncated, draft)
    assert reviewed == draft
    assert "不完整" in notes


def test_review_extracts_complete_json_envelope():
    draft = "# 旧稿"
    payload = '{"markdown": "# 新稿\\n\\n正文", "notes": ["修了标题"]}'
    reviewed, notes = _as_reviewed_markdown(payload, draft)
    assert reviewed == "# 新稿\n\n正文"
    assert "修了标题" in notes


def test_review_empty_keeps_draft():
    draft = "# 重构稿"
    reviewed, notes = _as_reviewed_markdown("   ", draft)
    assert reviewed == draft
    assert "为空" in notes
