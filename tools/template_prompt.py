"""模板渲染 prompt 公共构建：占位符模板 / 格式规范模板两类应对。

task 的渲染模板 prompt 只需提供差异项（渲染器名、内容来源、空内容规则、
额外规则），**类型判断与两类渲染规则**统一在这里维护：

- ``build_template_render_prompt``：生成**基础规则**（内容来源、空内容规则、
  输出纪律、一致性）——不含类型判断，供三类路径共用
- ``PLACEHOLDER_RULES`` / ``SPEC_RULES``：**类型专用规则**，由
  ``template_router.route_template`` 在判型成功后拼进 system prompt——
  LLM 只执行已判定类型的规则，不再自行判断
- ``FALLBACK_TEMPLATE_RULES``：两类型简述，供判型失败 / 路由关闭时兜底
  （此时类型未知，才需要 LLM 自己判断）

用法（task 的 prompts.py）：

    ITEM_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
        renderer="待办事项渲染器",
        source="已审核通过的待办提取结果",
        empty_rule="待办列表为空时，按模板对「无内容」的要求输出（如输出 [] 或空表格）",
    )
"""
from __future__ import annotations


def build_template_render_prompt(
    *,
    renderer: str,
    source: str,
    empty_rule: str,
    extra_rules: list[str] | None = None,
) -> str:
    """按差异项生成模板渲染的基础规则（类型判断由 template_router 完成）。

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
        "模板类型已由系统判定并在下方标注，请按对应类型规则执行。\n\n"
        "通用规则：\n"
        f"{numbered}"
    )


# 类型专用规则：判型成功后由 route_template 拼在基础规则之后。
# 不含 source（用"内容来源"泛指），因此可作为模块级常量。

PLACEHOLDER_RULES = """
【模板类型已判定：占位符模板】模板含 [描述] / [xxx] 占位符
- 保留模板中所有固定文字，仅替换占位符为内容来源中的内容
- [xxx / yyy / zzz] = 多选一，含 emoji；含 [xxx] 的表格行 = 行模板，按内容展开
- **Markdown 表格：表头、分隔行、每一条数据各占一行**；禁止把多行数据粘在同一行（禁止出现 || 粘连）
- **遵守模板正文中的全部约束**（字数、条数/行数、范围、各节职责等）；有体量限制时精选，勿全量堆砌
- 各小节/各表只写该处应有内容，不要串节；不要输出全空数据行
- 输出与模板结构对齐（标题层级、表头保留）"""

SPEC_RULES = """
【模板类型已判定：格式规范模板】模板无占位符，而是输出格式说明 + 示例
- 把内容来源按模板规定的字段结构与格式输出（例如标准 JSON 数组、表格等）
- 模板中的示例仅用于演示格式，不要照抄示例里的输入内容
- 严格按【格式指令】段的字段结构输出"""

FALLBACK_TEMPLATE_RULES = """
下方模板有两种可能类型，先判断属于哪种，再按对应规则执行：
【类型一：占位符模板】模板含 [描述] / [xxx] 占位符 → 保留固定文字、仅替换占位符
【类型二：格式规范模板】模板无占位符，而是输出格式说明 + 示例 → 按字段结构输出，示例仅用于演示格式、不要照抄示例输入"""
