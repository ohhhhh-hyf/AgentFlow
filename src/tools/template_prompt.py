"""模板渲染 prompt 公共构建：占位符模板 / 格式规范模板两类应对。

task 的渲染模板 prompt 只需提供差异项（渲染器名、内容来源、空内容规则、
额外规则），**类型判断与两类渲染规则**统一在这里维护：

- 类型一：占位符模板（含 [描述] / [xxx]）→ 保留固定文字、替换占位符
- 类型二：格式规范模板（无占位符，是格式说明 + 示例）→ 按字段结构输出

用法（task 的 prompts.py）：

    ITEM_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
        renderer="待办事项渲染器",
        source="已审核通过的待办提取结果",
        empty_rule="待办列表为空时，按模板对「无内容」的要求输出（如输出 [] 或空表格）",
    )
"""


def build_template_render_prompt(
    *,
    renderer: str,
    source: str,
    empty_rule: str,
    extra_rules: list[str] | None = None,
) -> str:
    """按差异项生成模板渲染 prompt（两类模板应对规则为公共部分）。

    - ``renderer``：渲染器角色名（如 "待办事项渲染器"）
    - ``source``：内容来源描述（如 "已审核通过的待办提取结果"）
    - ``empty_rule``：无内容 / 信息不足时的处理规则
    - ``extra_rules``：该线特有的补充规则（如 "严禁编造事实"）
    """
    rules = [
        f"以「{source}」为唯一内容来源：不新增内容、不改变已有内容，只做格式转换",
        empty_rule,
        "只输出最终内容，不要输出解释、不要输出 Markdown 代码块包装",
        "输出一致性：同一输入重复生成时结果稳定，措辞优先沿用"
        + f"{source}",
    ]
    if extra_rules:
        rules.extend(extra_rules)
    numbered = "\n".join(f"{i}. {rule}" for i, rule in enumerate(rules, start=1))
    return (
        f"你是{renderer}。根据{source}和下方输出模板，生成输出。\n\n"
        "下方模板有两种可能类型，先判断属于哪种，再按对应规则执行：\n\n"
        "【类型一：占位符模板】模板含 [描述] / [xxx] 占位符\n"
        f"- 保留模板中所有固定文字，仅替换占位符为{source}中的内容\n"
        "- [xxx / yyy / zzz] = 多选一，含 emoji；含 [xxx] 的表格行 = 行模板，"
        "按内容生成对应行数\n"
        "- 输出与模板逐字符对齐\n\n"
        "【类型二：格式规范模板】模板无占位符，而是输出格式说明 + 示例\n"
        f"- 把{source}按模板规定的字段结构与格式输出"
        "（例如标准 JSON 数组、表格等）\n"
        "- 模板中的示例仅用于演示格式，不要照抄示例里的输入内容\n\n"
        "通用规则：\n"
        f"{numbered}"
    )
