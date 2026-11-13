"""模板引擎自测 (测试模板读取、回退逻辑、元数据剥离与栏目解析)."""
import sys
from pathlib import Path

# 确保优先导入 demo 下的模块，完全独立于外部历史代码
DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from core.templates import load_template, parse_template_metadata


def test_load_normal_template():
    """测试普通通用纪要模板读取."""
    res = load_template("general_minutes", mode="normal", lang="zh")
    assert res.text.startswith("# 全文摘要")
    assert "<!-- requirement" not in res.text
    assert "<!-- layout" not in res.text
    assert res.sections == ["全文摘要", "要点梳理", "结论定调"]
    assert "公文陈述" in res.meta.requirement
    assert res.meta.mode == "column_major"


def test_load_agenda_template():
    """测试议题通用纪要模板读取."""
    res = load_template("general_minutes", mode="agenda", lang="zh")
    assert res.text.startswith("# 全文摘要")
    assert "<!-- requirement" not in res.text
    assert "<!-- layout" not in res.text
    assert res.sections == ["全文摘要", "议题梳理"]
    assert res.meta.mode == "topic_major"
    assert res.meta.container == "议题梳理"
    assert "以现场审定的有效议题为主线" in res.meta.requirement


def test_fallback_to_normal_when_agenda_missing(tmp_path):
    """测试议题模板不存在时平滑回退普通模板."""
    normal_dir = tmp_path / "templates" / "zh"
    agenda_dir = tmp_path / "agenda_templates" / "zh"
    normal_dir.mkdir(parents=True)
    agenda_dir.mkdir(parents=True)

    test_file = normal_dir / "custom_test.md"
    test_file.write_text("# 唯一模板\n[正文]", encoding="utf-8")

    res = load_template("custom_test", mode="agenda", lang="zh", resources_root=tmp_path)
    assert res.sections == ["唯一模板"]
    assert res.meta.mode == "column_major"


def test_parse_metadata_inline():
    """测试单行 layout 注释解析."""
    raw = "<!-- layout: topic_major -->\n# 标题\n[正文]"
    cleaned, meta = parse_template_metadata(raw)
    assert cleaned == "# 标题\n[正文]"
    assert meta.mode == "topic_major"
