"""tools.template_router —— 模板路由层（拆分子模块后的聚合门面）。

对外接口与原 template_router.py 完全一致；实现按职责拆分在
_base（常量/基础工具）/_detect（判型路由）/_placeholder（占位符填充）
_gate（门禁编译）/_preview（可读化）五个子模块。

设计约束（无痛插入的承诺）：

1. 纯函数为主，不 import 任何任务线 / domain
2. route_template 任何异常 / 解析失败都返回 None，调用方回退旧路径
3. 环境变量 TEMPLATE_ROUTER=off 一键关闭路由
4. validate_rendered_output 默认只读
"""
from ._base import (
    _body_han_count,
    clear_compile_caches,
    is_router_enabled,
    split_template_meta,
    strip_outer_markdown_fence,
    wrap_template_requirement,
)
from ._detect import (
    detect_template_kind,
    extract_description_cues,
    parse_placeholder_template,
    route_template,
    split_spec_template,
    strip_char_budget_meta,
)
from ._placeholder import (
    assemble_placeholder_output,
    build_placeholder_fill_user,
    fill_placeholder_template,
    normalize_fill_tables,
    parse_fill_response,
    plan_placeholder_fill,
    preview_to_template,
    template_to_preview,
)
from ._preview import (
    edit_model_to_template,
    extract_listed_aspects,
    preview_to_edit_model,
    preview_to_readable,
    readable_to_template,
)
from ._gate import (
    check_compile_fidelity,
    maybe_compile_natural_template,
    merge_preview_fill,
    modify_template,
    validate_rendered_output,
)

LINE_SCHEMA_HINTS: dict[str, str] = {
    "minutes": (
        "headline, executive_summary, key_decisions, risks_and_blockers, "
        "unresolved_questions, personally_relevant_points"
    ),
    "actions": (
        "my_actions / unassigned_actions；每项含 task, owner, deadline, priority, status"
    ),
    "risk": "risks 列表（描述、等级、相关方、缓解建议等）",
    "mindmap": "outline（Markdown 树状大纲：#/##/### 与 - 短分支；禁止表格）",
    "graph": "nodes / edges / outline",
    "review": "knowledge_points / issues / corrected_notes",
    "quiz": "questions（prompt, dimension, answer_points）",
}


__all__ = [
    "LINE_SCHEMA_HINTS",
    "assemble_placeholder_output",
    "build_placeholder_fill_user",
    "check_compile_fidelity",
    "clear_compile_caches",
    "detect_template_kind",
    "edit_model_to_template",
    "extract_description_cues",
    "extract_listed_aspects",
    "fill_placeholder_template",
    "is_router_enabled",
    "maybe_compile_natural_template",
    "merge_preview_fill",
    "modify_template",
    "normalize_fill_tables",
    "parse_fill_response",
    "parse_placeholder_template",
    "plan_placeholder_fill",
    "preview_to_edit_model",
    "preview_to_readable",
    "preview_to_template",
    "readable_to_template",
    "route_template",
    "split_spec_template",
    "split_template_meta",
    "strip_char_budget_meta",
    "strip_outer_markdown_fence",
    "wrap_template_requirement",
    "template_to_preview",
    "validate_rendered_output",
]


