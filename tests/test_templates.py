"""模板引擎自测 (测试模板读取、回退逻辑、元数据剥离、跨行占位符解析与栏目解析)."""
import sys
from pathlib import Path

# 确保优先导入 demo 下的模块，完全独立于外部历史代码
DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from core.templates import extract_placeholders, load_template, parse_template_metadata


def test_load_normal_template():
    """测试普通通用纪要模板读取."""
    res = load_template("general_minutes", mode="normal", lang="zh")
    assert res.text.startswith("# 全文摘要")
    assert "<!-- requirement" not in res.text
    assert "<!-- layout" not in res.text
    assert res.sections == ["全文摘要", "要点梳理", "结论共识"]
    assert res.meta.mode == "column_major"
    assert len(res.placeholders) == 3
    assert "单段概括" in res.placeholders[0]
    assert "业务板块名称" in res.placeholders[1]
    assert "推进基调" in res.placeholders[2]


def test_load_agenda_template():
    """测试议题通用纪要模板读取 (单行 layout、无 container、无 requirement、多行占位符)."""
    res = load_template("general_minutes", mode="agenda", lang="zh")
    assert res.text.startswith("# 全文摘要")
    assert "<!-- requirement" not in res.text
    assert "<!-- layout" not in res.text
    assert res.sections == ["全文摘要", "议题梳理"]
    assert res.meta.mode == "topic_major"

    # 验证多行方括号占位符解析
    assert len(res.placeholders) == 2
    assert "单段概括" in res.placeholders[0]
    agenda_placeholder = res.placeholders[1]
    assert "以现场审定的有效议题清单为主线逐个议题闭环展开" in agenda_placeholder
    assert "- ### 要点梳理：" in agenda_placeholder
    assert "- ### 结论共识：" in agenda_placeholder
    assert "\n" in agenda_placeholder  # 确实验证了跨行换行完整保留


def test_extract_placeholders_multiline_and_nested():
    """测试方括号占位符的跨行提取、内嵌复选框匹配与 Markdown 链接排除."""
    sample = (
        "# 任务要求\n"
        "[这是一个跨行的说明占位符：\n"
        "- [ ] 事项 A\n"
        "- [ ] 事项 B\n"
        "请务必在周五前完成。]\n\n"
        "详情请见 [说明文档](https://example.com/docs) 。\n"
        "[单行占位1] 与 [单行占位2]"
    )
    phs = extract_placeholders(sample)
    # 应成功提取 3 个占位符（跨行块 + 单行1 + 单行2），排除 Markdown 链接
    assert len(phs) == 3

    assert "跨行的说明占位符" in phs[0].inner
    assert "- [ ] 事项 A" in phs[0].inner
    assert phs[0].inner.endswith("请务必在周五前完成。")

    assert phs[1].inner == "单行占位1"
    assert phs[2].inner == "单行占位2"


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
    assert res.placeholders == ["正文"]


def test_parse_metadata_inline():
    """测试单行 layout 注释解析."""
    raw = "<!-- layout: topic_major -->\n# 标题\n[正文]"
    cleaned, meta = parse_template_metadata(raw)
    assert cleaned == "# 标题\n[正文]"
    assert meta.mode == "topic_major"
