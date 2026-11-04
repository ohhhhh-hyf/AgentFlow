# 拆分自 test_placeholder_parser.py，覆盖：test_default_minutes_template, test_ellipsis_table_row_template_recognized, test_domain_specific_accuracy_rules…

"""tests/unit/core/templates/test_placeholder_parser.py -- 占位符 AST、正则与字面量解析单元测试。"""

from __future__ import annotations
import logging
import re
import sys
from pathlib import Path
import pytest
from core.templates.router._base import iter_placeholders, split_template_meta
from core.templates.router._detect import parse_placeholder_template
from core.templates.router._gate import scan_fixed_bracket_literals, validate_rendered_output
from core.templates.router._placeholder import plan_placeholder_fill
from tests.support.expectations import expect
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
)

FILL_TPL = (
    "# [甲栏]\n[一段话概括甲栏内容]\n\n"
    "# [乙栏]\n[一段话概括乙栏内容]\n\n"
    "# [丙栏]\n[一段话概括丙栏内容]\n"
)

CAPTION_TPL = (
    "# [甲栏]\n[一段话概括甲]\n\n"
    "# [进度追踪]\n"
    "[按下表逐行填写各模块的进展与当前状态（一行一个模块）；不要另建表格，表内已写的明细不在别处重复]\n\n"
    "| 模块 | 进展 |\n| --- | --- |\n| … | … |\n\n"
    "# [乙栏]\n[一段话概括乙]\n"
)

BODY_CAPTION_TPL = (
    "# [治疗方案与医嘱]\n"
    "[医嘱清单：检查安排、用药、生活方式、复诊与陪同要求各占一条，每条都是 `- ` 分点行；药品明细只写进下表]\n\n"
    "| 药名 | 剂量 |\n| --- | --- |\n| … | … |\n"
)

def test_default_minutes_template() -> None:
    """纪要线不传模板 → 自动路由到「通用纪要」（不再走无模板自由渲染）。

    回归背景（2026-09-18 实测无模板纪要）：完全听模型的——栏目自定、无缺省词、
    无段落上限、不跑模板门禁（同一份原文 6410 汉字 / 最长单行 515 字 / 超篇幅上限 16% 无人管）。
    """
    from app.config import DEFAULT_MINUTES_TEMPLATE
    from app.tasks import _template_file

    expect(DEFAULT_MINUTES_TEMPLATE == "general_minutes", "默认纪要模板常量为 general_minutes", DEFAULT_MINUTES_TEMPLATE)

    auto = _template_file("meeting", "minutes", "")
    expect(auto is not None, "纪要线留空 → 自动套用模板（返回模板文件）", f"{auto}")
    if auto is not None:
        text = auto.read_text(encoding="utf-8")
        expect("# [全文摘要]" in text and "# [要点梳理]" in text, "自动套用的就是「通用纪要」（含全文摘要/要点梳理栏）", text[:60])
    expect(_template_file("meeting", "minutes_trace", "") is None, "其它线留空仍不套模板（minutes_trace）", "")
    expect(_template_file("notes", "catalog", "") is None, "其它域留空仍不套模板（notes/catalog）", "")

    from app.tasks import ApiError

    try:
        _template_file("meeting", "minutes", "不存在的模板")
        raised = False
    except ApiError:
        raised = True
    expect(raised, "显式传入非法模板仍 400（不静默套默认）", "")
    expect(_template_file("meeting", "minutes", "项目进度会") is not None, "显式传入合法模板照旧生效", "")


def test_ellipsis_table_row_template_recognized() -> None:
    """省略号样例行（`| … |`）也要被认成表格行模板——否则空表/缺表/行数检查整体失效。

    回归背景（2026-09-18 第27条实测）：就医咨询药品表只有表头没有数据行，但
    extract_template_table_constraints 只认 `[...]` 占位 → constraints=[] →
    「表格无有效数据行」对这类模板永不触发，空表静默落盘。
    """
    from core.templates.template_eval import (
        evaluate_output_against_template,
        extract_template_table_constraints,
    )

    advisory = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    cons = extract_template_table_constraints(advisory)
    expect(bool(cons) and "[治疗方案]" in cons[0]["section_title"], "就医咨询：`| … |` 样例表被认成约束（section=治疗方案）", f"{cons}")

    art = (
        "# 就医咨询\n\n"
        "# [治疗方案与医嘱]\n"
        "- **用药**：医生开了药。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    expect("表格无有效数据行" in evaluate_output_against_template(advisory, art)[0]
          if evaluate_output_against_template(advisory, art) else False, "表头在、数据行缺失 → 报「表格无有效数据行」（硬伤，走 repair）", f"{evaluate_output_against_template(advisory, art)}")

    # 顺带钉住 row-hint 的两个误判源（会把"形态/泛指"读成行数上限）
    from core.templates.template_eval import parse_row_hint

    expect(parse_row_hint("不要用连续多行独占一行的 `**类别**：` 段落代替分点") is None, "「不要用连续多行独占一行的…」不是 1 行上限", "")
    expect(parse_row_hint("每行一个事项") is None, "「每行一个X」是形态要求不是数量", "")
    expect(parse_row_hint("最多 3 行") == 3, "「最多 3 行」仍是真上限", "")

    # 真实产物回归：正常带数据的表不再被"约需 1 行"误伤
    for stem, artifact in (
        ("clinical_advisory", "5b17e044d210441a87bce540540b7163"),
        ("debate_forum", "67648012"),
        ("project_progress", "dff4ac29"),
    ):
        tpl = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        matches = sorted(Path("data/test/output").glob(f"{artifact}*/result.md"))
        if not matches:
            continue
        issues = [
            x
            for x in evaluate_output_against_template(tpl, matches[0].read_text(encoding="utf-8", errors="ignore"))
            if "行（超出）" in x
        ]
        expect(not issues, f"{stem}：带数据行不被「约需 1 行」误判", f"{issues[:1]}")


def test_domain_specific_accuracy_rules() -> None:
    """医疗、媒体和庭审模板保留各自的事实边界。"""
    d = _active_dir()

    media = (d / "media_qa_session.md").read_text(encoding="utf-8")
    expect("问答成对还原" in media and "结论先行" in media, "媒体问答：问答成对还原、结论先行", "")
    expect("事实数据、政策口径与回应内容忠实保真" in media, "媒体问答：事实与口径忠实保真", "")
    expect("过滤寒暄客套与同义反复" in media, "媒体问答：过滤寒暄与同义反复", "")

    court = (d / "court_transcript.md").read_text(encoding="utf-8")
    expect("明确标明诉讼当事人与法庭认定来源" in court, "庭审记录：标明当事人与法庭认定来源", "")
    expect("程序节点准确还原" in court, "庭审记录：程序节点准确还原", "")
    for heading in ("## [庭审概况]", "## [诉辩意见]", "## [举证质证]", "## [庭审结果]"):
        expect(heading in court, f"庭审记录：包含栏位 {heading}", "")


def test_prefix_caching_invariant_layout() -> None:
    """验证 vLLM Prefix Caching 前缀布局：静态契约绝对置顶，动态素材后置，尾部附执行令。"""
    from core.templates.router import route_template
    from core.runner.prompt_utils import build_render_prompt

    # 1. 占位符路由：不同会议素材必须共享 100% 相同的前缀
    context_a = "这是第一场关于预算审批的会议材料，包含财务报表与人员汇报。"
    context_b = "这是第二场关于架构重构的技术研讨，包含系统设计与集群规划。"

    routed_a = route_template(context_a, FILL_TPL, "无模板提示", "模板系统提示")
    routed_b = route_template(context_b, FILL_TPL, "无模板提示", "模板系统提示")

    assert routed_a is not None and routed_b is not None
    sys_a, user_a = routed_a
    sys_b, user_b = routed_b

    # 系统提示词完全一致
    assert sys_a == sys_b
    assert "模板系统提示" in sys_a

    # 用户消息中：静态模板原文置顶（已彻底切除冗余的模板结构解析，直接阅读原文）
    assert user_a.startswith("模板原文：\n")

    # 静态契约前缀必须在动态上下文之前
    idx_template_a = user_a.index("模板原文：")
    idx_ctx_a = user_a.index("【待处理业务素材】")
    idx_action_a = user_a.index("【交付执行令】")
    assert idx_template_a < idx_ctx_a < idx_action_a

    # 提取两请求在动态素材之前的共同前缀
    prefix_a = user_a[:idx_ctx_a]
    prefix_b = user_b[:idx_ctx_a]
    assert prefix_a == prefix_b, "相同模板的不同会议请求，在【待处理业务素材】前的静态前缀必须字节级完全一致！"

    # 执行令位于最末尾
    assert user_a.strip().endswith("直接输出最终 Markdown 正文。")
    assert user_b.strip().endswith("直接输出最终 Markdown 正文。")

    # 2. 兜底渲染链路同样遵循静态前置规范
    fb_sys, fb_user = build_render_prompt(context_a, "# 固定简单模板\n内容", "无模板提示", "模板系统提示")
    assert fb_user.startswith("模板原文：\n# 固定简单模板")
    assert fb_user.index("模板原文：") < fb_user.index("【待处理业务素材】") < fb_user.index("【交付执行令】")
