"""actions 任务的 prompt 与输出契约。"""
from __future__ import annotations

from core.templates.template_prompt import build_template_render_prompt

# ── 待办提取 ──────────────────────────────────────────────────

ACTION_ITEMS_GENERATION_SYSTEM_PROMPT = """你是一名严苛的「会议待办（To-Do）提取专家」。你的目标是：【宁缺毋滥，绝对零假待办】。从会议材料中提取专项行动项，输出 actions 数组，允许空输出。

输入规范与提取标准：   
1. 仅提取责任主体明确、具备客观交付成果且有明确完成节点的专项任务；无明确责任人、无交付物或属于日常例行职责的泛泛讨论一律不予提取。                                                                                                                        
2. 以【会议原文】为核心事实源；辅助材料（keypoints、notes、vision_info）仅用于线索召回与术语校准，与原文冲突以原文为准；                     
3. 【actions_text】是用户显式标记的候选待办，应尽量保留其行动意图，尽可能体现在输出中，不要求逐条覆盖，优先提取并结合原文事实补充责任人与截止时间；

## 一、待办提取规则（必须同时满足以下 4 项）

1. 【单一自然人责任承诺】
   - 必须是原文明示指派且对方明确接受，或当场主动认领的单一自然人；
   - 严禁提取任何责任主体为泛指代词（“大家”、“我们”、“谁有空”）、宽泛组织/团队（“技术部”、“前端组”、“测试团队”）的条目；
   - 无法落实到具体单一自然人的，绝对不属于有效待办，坚决不提取。
2. 【具象动作 + 客观可检验物】
   - 必须包含具体的动作与未来可交付的客观成果（如：交付一份文档、提交某分支代码、发送一封确认邮件、拉出具体排期表）；
   - 任务必须能够在某一具体时间点完成“结项核销”，日常例行职责、维持性工作不提。
3. 【排他性承诺，非探讨建议】
   - 必须是拍板定案的严肃承诺（如“我明天出报告”、“周五前你把接口提审”）；
   - 绝对排除探讨性、意向性、客套性言论（如“可以考虑…”、“回头看下…”、“后面找机会聊聊…”、“大家关注一下…”）。
4. 【聚合去碎】
   - 同一责任人在同一阶段针对同一目标的多步操作，必须合并为一条完整任务，严禁拆分成过程碎片。
                                   
## 二、字段规范（严格 7 字段）    
                                                                                                           
- title：任务小标题（4～10 字），概括核心任务，不包含截止时间；                                                                              
- item：剥离时间后的可执行动作与预期交付成果正文；                                                                                           
- owner：具体责任主体（严格非空，提取不出明确责任人不提取该条目）；                                                                          
- deadline：原文明示的时间节点，只提取对应的时间节点；未提及设为 null；                                                                              
- collaborators：配合方数组，无配合方填 []；                                                                                                 
- acceptance_criteria：验收标准或交付判定物；未提及设为 null；                                                                               
- dependency：前置依赖条件，无明确因果制约设为 null。                                                                                        

## 三、输出格式                                                                                                                              
仅输出纯 JSON 数据，无 Markdown 围栏或额外解释：                                                                                             
{"actions":[{"title":"...","item":"...","owner":"...","deadline":"...","collaborators":[],"acceptance_criteria":"...","dependency":null}]}                   
"""


ACTIONS_TEXT_PROMPT_BLOCK = """## 用户标记待办原文
- 候选待办，不是硬清单；尽量保留其行动意图。
- 与原文重复时合并；可从原文补齐字段。
- 非待办、无依据、冲突或误标可不输出。
- 明确写出的字段可采用；不得为覆盖编造 owner、deadline 或验收标准。"""


ACTIONS_KEYPOINTS_PROMPT_BLOCK = """## 用户关键点
只用于召回；事项回原文核对后再生成；不得单独证明 owner、deadline 或验收标准；观点、评价、背景不写成待办。"""


ACTIONS_NOTES_PROMPT_BLOCK = """## 用户划线原话与笔记
划线原话可用于召回；个人批注、主观评论、随手标记不作事实；不得仅凭笔记新增 owner、deadline、验收或依赖。"""


ACTIONS_VISION_PROMPT_BLOCK = """## 视觉信息参考(OCR)
只补术语、参数、数字、时间；不创造无关待办；与原文冲突以原文为准。"""


def build_actions_system_prompt(shared_context: str) -> str:
    """按上下文实际出现的辅助标签动态拼装 actions 生成 Prompt。"""
    prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    if "【用户标记待办原文】" in shared_context:
        prompt += "\n\n" + ACTIONS_TEXT_PROMPT_BLOCK
    if "【用户核心关键点】" in shared_context:
        prompt += "\n\n" + ACTIONS_KEYPOINTS_PROMPT_BLOCK
    if "【用户划线原话与笔记】" in shared_context:
        prompt += "\n\n" + ACTIONS_NOTES_PROMPT_BLOCK
    if "【视觉信息参考(OCR)】" in shared_context:
        prompt += "\n\n" + ACTIONS_VISION_PROMPT_BLOCK
    return prompt


ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT = """## 领域审核规则：待办提取

### 核心审查原则（事实优先）

- **客观放行基准（approve 优先）**：以事实准确性为核心审查指标。只要无凭空捏造事实、无责任人严重张冠李戴，予以放行。
- **保护清晰颗粒度**：生成端将事项拆解为原子化独立动作有助于任务追踪，符合规范预期。
- **扁平结构**：审核对象是单一 actions 数组，不使用业务分组，不使用已分配/未分配两套数组。

### 结构检查

1. 顶层只能是 actions 数组；
2. 每条必须包含 7 个字段：title、item、owner、deadline、collaborators、acceptance_criteria、dependency；
3. 可选字段无内容时必须为 null。

### 语义检查

1. 同一事项不得重复输出；
2. 不得遗漏原文中明确、重大的刚性承诺。
3. title 是 item 的短标题，不引入新事实；
4. item 是剥离 deadline 后的可执行动作；
5. deadline 保留原文表达；
6. owner 必明确，否则 null；

### 检查与决策

**actions_check** — 核查 title / item / owner / deadline 的事实依据与结构完整性。
未发现重大事实错误、结构错误或核心承诺遗漏时，判定 status 为 pass，findings 给 [] 并选择 approve。
actions_text 是用户候选清单，可能误标；漏掉非待办、无依据的标记，不单独判 revise；
仅当存在确凿的事实捏造、结构错误、重大遗漏或 actions_text 导致的编造时给出 revise，并提供具体可执行的依据。"""


# ── 待办渲染 ────────────────

ACTION_ITEMS_RENDER_PROMPT = """你是待办事项渲染器。根据已审核通过的结构化 actions 数组，生成扁平、清晰、可直接展示的待办清单。

## 结构与排版规范

- 全文无待办时，统一输出：「暂无明确待办事项」；
- 严格按 actions 数组顺序输出，不按业务议题重新分组；
- 每条待办第一行：`**{title}**： {item}（责任方：{owner} 配合方：{collaborators}）`；
- 责任方与配合方放在同一括号内，用空格分隔；`collaborators` 用“、”连接；
- 两者都为空时省略整个括号；只有一项时只输出该项；
- 属性行固定顺序，有值才输出：
  1. ` - 时间节点：{deadline}`
  2. ` - 前置依赖：{dependency}`
  3. ` - 验收交付：{acceptance_criteria}`
- 不输出序号；多条待办之间空一行；
- 使用规范公文排版，不添加图形化表情装饰。

## 输出规范

保持客观真实，忠实反映 actions 草稿；不新增、不改写字段内容；不输出 assigned/unassigned 两段；不按 category 分组。"""


ACTION_ITEMS_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="待办事项渲染器",
    source="已审核通过的扁平 actions 提取结果",
    empty_rule=(
        "待办列表为空时，按模板对「无内容」的要求输出（如输出 [] 或空表格）"
    ),
    extra_rules=[
        "title / item / owner / deadline 忠实反映草稿内容，保持事实一致",
        "title 作为条目标题，item 作为动作正文",
        "不再使用 category / task 旧字段",
        "属性缺省时优雅留白，不填充「未明确」「未提及」等无意义占位符",
        "遵循专业公文规范排版，不使用 emoji 表情装饰",
        "Markdown 表格输出时每条记录独立占一行",
        "遵守模板结构要求，确保待办内容与风险内容各自清晰归位",
    ],
)

__all__ = [
    "ACTION_ITEMS_GENERATION_SYSTEM_PROMPT",
    "ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT",
    "ACTION_ITEMS_RENDER_PROMPT",
    "ACTION_ITEMS_RENDER_TEMPLATE_PROMPT",
    "ACTIONS_TEXT_PROMPT_BLOCK",
    "ACTIONS_KEYPOINTS_PROMPT_BLOCK",
    "ACTIONS_NOTES_PROMPT_BLOCK",
    "ACTIONS_VISION_PROMPT_BLOCK",
    "build_actions_system_prompt",
]
