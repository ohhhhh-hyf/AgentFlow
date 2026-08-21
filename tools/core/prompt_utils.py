"""prompt_utils.py —— 通用渲染 prompt 组装工具。

各任务线的 render（纪要/风险等"自由文本渲染"）共享同一套模板分支逻辑：
- 有模板：用模板 prompt，模板原样拼进用户消息（LLM 只替换占位符）
- 无模板：用普通渲染 prompt，用户消息就是上下文本身

模板路由（tools.template_router）：有模板时先自动判型分派——
占位符模板 / 格式规范模板 / 自然语言描述三类各自最优处理；
任何无法处理的情况回退旧路径（原样拼模板），不影响现有逻辑。
开关：环境变量 ``TEMPLATE_ROUTER=off`` 关闭路由。

用法（任务线 render 内）：
    from tools.prompt_utils import build_render_prompt

    def _prompt_and_user(self, context, template):
        return build_render_prompt(
            context, template, MY_RENDER_PROMPT, MY_RENDER_TEMPLATE_PROMPT
        )
"""
from __future__ import annotations

from tools.template_prompt import FALLBACK_TEMPLATE_RULES
from tools.template_router import route_template


def build_render_prompt(
    context: str,
    template: str,
    render_prompt: str,
    template_prompt: str,
) -> tuple[str, str]:
    """按是否提供模板选择渲染 prompt，并组装 (prompt, user)。

    Args:
        context: 已审核的渲染上下文（草稿 + 审核结论 + 原文等）。
        template: 输出模板文本；空白表示不使用模板。
        render_prompt: 无模板时的渲染指令（system prompt）。
        template_prompt: 有模板时的渲染指令（system prompt）。

    Returns:
        (prompt, user)：
        - 有模板 → (template_prompt, f"{context}\\n\\n{template}")
          先经模板路由分派；无法处理时回退此旧路径
        - 无模板 → (render_prompt, context)
    """
    template = template or ""
    if not template.strip():
        return render_prompt, context
    routed = route_template(context, template, render_prompt, template_prompt)
    if routed is not None:
        return routed
    # 判型失败 / 路由关闭 / 自然语言编译失败：类型未知，
    # 追加两类型简述让 LLM 自行判断（兜底，与旧行为等价）
    return (
        template_prompt + FALLBACK_TEMPLATE_RULES,
        f"{context}\n\n{template}",
    )


__all__ = ["build_render_prompt"]
