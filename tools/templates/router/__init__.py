"""tools.templates.router —— 模板路由层（拆分子模块后的聚合门面）。

2026-09-22 从 ``tools/template_router`` 迁入 ``tools/templates/``：模板相关代码
（渲染 prompt / 评测 / 篇幅预算 + 本路由层）集中在一个包内，上层 import 变为
``from tools.templates.router import ...``。

对外接口与原 template_router.py 完全一致；实现按职责拆分在
_base（常量/基础工具）/_detect（判型路由）/_placeholder（占位符填充）
_gate（门禁编译）/_preview（预览维度判定）五个子模块。

设计约束（无痛插入的承诺）：

1. 纯函数为主，不 import 任何任务线 / domain
2. route_template 任何异常 / 解析失败都返回 None，调用方回退旧路径
3. 环境变量 TEMPLATE_ROUTER=off 一键关闭路由
4. validate_rendered_output 默认只读
"""
from ._base import (
    _body_han_count,  # noqa: F401 - 门面再导出：tools/runtime/render.py 从这里取
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
from ._preview import extract_listed_aspects
from ._gate import (
    check_compile_fidelity,
    maybe_compile_natural_template,
    merge_preview_fill,
    modify_template,
    validate_rendered_output,
)
from ._guard import (
    analyze_speaker_topology,
    guard_template_routing,
    is_special_lecture_disqualified,
    load_fallback_template_text,
    resolve_guarded_template,
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
    "preview_to_template",
    "route_template",
    "split_spec_template",
    "split_template_meta",
    "strip_char_budget_meta",
    "strip_outer_markdown_fence",
    "wrap_template_requirement",
    "analyze_speaker_topology",
    "guard_template_routing",
    "is_special_lecture_disqualified",
    "load_fallback_template_text",
    "resolve_guarded_template",
    "template_to_preview",
    "validate_rendered_output",
]


