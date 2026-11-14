"""模板引擎自测 (测试模板读取、回退逻辑、元数据剥离、跨行占位符解析与栏目解析)."""
import sys
from pathlib import Path

# 确保优先导入 demo 下的模块，完全独立于外部历史代码
DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from core.templates import (
    KNOWN_TEMPLATE_IDS,
    STANDARD_TEMPLATES,
    extract_placeholders,
    load_template,
    parse_template_metadata,
    resolve_template_id,
)


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
    assert "具体研讨主题" in res.placeholders[1]
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


def test_resolve_template_id_empty_and_none():
    """测试空值与未传返回空串（触发上层智能模板分类器）."""
    assert resolve_template_id(None) == ""
    assert resolve_template_id("") == ""
    assert resolve_template_id("   ") == ""
    assert resolve_template_id("  .md  ") == ""


def test_resolve_template_id_standard_english():
    """测试标准英文模板 ID 大小写与 .md 后缀归一化."""
    assert resolve_template_id("project_progress") == "project_progress"
    assert resolve_template_id("project_progress.md") == "project_progress"
    assert resolve_template_id("PROJECT_PROGRESS.MD") == "project_progress"
    assert resolve_template_id("  team_meeting.md ") == "team_meeting"
    assert resolve_template_id("general_minutes") == "general_minutes"


def test_resolve_template_id_chinese_names():
    """测试 29 种中文场景名称标准映射."""
    assert len(STANDARD_TEMPLATES) == 29
    assert resolve_template_id("项目进度会") == "project_progress"
    assert resolve_template_id("团队例会") == "team_meeting"
    assert resolve_template_id("决策评审会") == "decision_review"
    assert resolve_template_id("工作研讨会") == "workshop_session"
    assert resolve_template_id("总结复盘会") == "retrospective_session"
    assert resolve_template_id("通用纪要") == "general_minutes"
    assert resolve_template_id("家校沟通") == "home_school_liaison"
    assert resolve_template_id("辩论会") == "debate_forum"
    assert resolve_template_id("用户自定义") != "user_customized"  # 已剔除自定义项


def test_resolve_template_id_aliases():
    """测试常用别名容错折叠至 general_minutes."""
    assert resolve_template_id("常规纪要") == "general_minutes"
    assert resolve_template_id("通用") == "general_minutes"
    assert resolve_template_id("通用纪要/其他") == "general_minutes"
    assert resolve_template_id("通用/其他") == "general_minutes"


def test_load_template_with_chinese_name_and_placeholder_files():
    """测试传中文场景名通过映射引擎精准定位物理文件（不被兜底逻辑掩盖）."""
    # 1. 普通模式下读取“项目进度会”
    res_normal = load_template("项目进度会", is_agenda=False, lang="zh")
    assert res_normal.meta.source_path.replace("\\", "/").endswith("resources/templates/zh/project_progress.md")

    # 2. 议程模式下读取“项目进度会” (优先命中 agenda_templates)
    res_agenda = load_template("项目进度会", is_agenda=True, lang="zh")
    assert res_agenda.meta.source_path.replace("\\", "/").endswith("resources/agenda_templates/zh/project_progress.md")

    # 3. 议程模式下读取仅支持普通模板的“辩论会” (平滑回退至 normal 目录的辩论会)
    res_fallback = load_template("辩论会", is_agenda=True, lang="zh")
    assert res_fallback.meta.source_path.replace("\\", "/").endswith("resources/templates/zh/debate_forum.md")

    # 4. 读取通用纪要，验证真实内容完备
    res_general = load_template("通用纪要", is_agenda=True, lang="zh")
    assert res_general.meta.mode == "topic_major"
    assert res_general.sections == ["全文摘要", "议题梳理"]

