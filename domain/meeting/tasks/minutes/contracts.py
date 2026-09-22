"""minutes 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类 MinutesGenerationContract → to_json_template() 生成生成契约 prompt
- 审阅契约类 MinutesSupervisorContract → to_json_template() 生成审阅契约 prompt
"""
from __future__ import annotations

from tools.schema.contracts import (
    Check, Decision, Feedback, GenerationContract, StrField, StrListField,
    SupervisorContract,
)
from tools.schema.fallback_rules import FallbackRules, Join, Raw


class MinutesGenerationContract(GenerationContract):
    """纪要草稿输出契约。"""

    fields = [
        StrField("headline", "会议纪要标题"),
        StrListField(
            "executive_summary",
            "概述（数组每项 = 一整段正文，**不超过约 200 字**（写法上 2–3 句为宜），不是标题、不是一句话。"
            "按槽位排序：进展/评价·结论/下一步；同性质事实合并在同一段，"
            "仅当结论口径或主体/地点不同才另起一段；**段数按内容定、不设固定上限**；"
            "**段数/句数是表达预算，不构成删事实的理由**——"
            "范围纳入/排除、同一指标的多组对照取值、金额与收付款节点、时限与责任人必须全在，"
            "不得只放决策段或风险段）",
        ),
        StrListField(
            "key_decisions",
            "决策（来自MeetingUnderstanding.decisions：客观全量搬运；"
            "职业/真人从上游下采本视角相关，措辞用上游原文，不得改写新增；"
            "真人模式下**有明确归属才分组**：**上游 decisions 是纯文本、没有归属，"
            "要对照会议原文补出归属**——原文里谁提出、谁拍板"
            "（含「我这边…」这类第一人称，按发言人归人）；"
            "归属本人的先写一行 `**与我相关**：` 再列其条目、条目内不写自己的姓名；"
            "归属他人的写一行 `**姓名**：` 再列其条目；"
            "**看不出归属的不写姓名、平铺在最前**；同一人的条目相邻；没有某组内容就不出现该组）",
        ),
        StrListField(
            "personally_relevant_points",
            "执行要点（有明确分工则写，无则[]；每条 2–3 句完整句、信息少时 1 句但要带数字/对象："
            "谁、具体做什么、相关要求/协同对象、时间；禁止半截句。"
            "**真人模式**（以【本用户命中】里他的待办为准）：**自己的条目排最前**——"
            "先给一个组名元素 `**与我相关**：`（独占该元素、不加 `- `），其下条目**不写自己的姓名**；"
            "**他人每位各给一个组名元素 `**姓名**：`**（独占元素，姓名照原文），"
            "其下写该人的条目、**条目不重复姓名**；"
            "确需他配合的合并成一句（如「上游出包后才能联调」）；"
            "客观/职业模板按有明确责任人的分工条数写）",
        ),
        StrListField(
            "risks_and_blockers",
            "风险（客观全量；职业/真人从上游 risks 下采本视角相关，措辞用上游原文；"
            "真人模式下**有明确归属才分组**：**带「姓名：」前缀的即该人提出/在跟"
            "（本人按姓名原样给出），无前缀的是看不出归属的全局项**。"
            "**分组写法**：归属本人的先写一行 `**与我相关**：` 再列其条目、"
            "条目内不写自己的姓名；归属他人的写一行 `**姓名**：` 再列其条目；"
            "**看不出归属的不写姓名、平铺在最前**；同一人的条目相邻；没有某组内容就不出现该组）",
        ),
        StrListField(
            "unresolved_questions",
            "未决问题（客观全量；职业/真人从上游 open_questions 下采本视角相关，措辞用上游原文；"
            "真人模式下**有明确归属才分组**（本人 `**与我相关**：`、"
            "他人 `**姓名**：`，条目内不写姓名）；带「姓名：」前缀的即该人的，"
            "无前缀的平铺在最前、不加任何姓名）",
        ),
        StrListField(
            "history_comparison",
            "与历史对比（仅当上下文有历史记忆注入【记忆命中/历史项目状态/项目纪要素材】时填写："
            "新增决策/延续事项/已闭环/风险演变四类对照，各至多一条并标注来源场次；无历史素材则[]）。"
            "每条必须是单个字符串（如「延续事项（自第2场）：…」），禁止对象数组",
        ),
    ]


class MinutesSupervisorContract(SupervisorContract):
    """纪要审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("facts_check", "仅记录严重问题，轻微问题不记录"),
        Check("perspective_check", "仅记录严重问题"),
        Check("consistency_check", "仅记录严重问题"),
    ]


MINUTES_GENERATION_OUTPUT_CONTRACT = MinutesGenerationContract.to_output_contract()
MINUTES_SUPERVISOR_OUTPUT_CONTRACT = MinutesSupervisorContract.to_output_contract()

# 降级拼装规则（声明式类）：fallback 节点由 sync_domain.py 检测子类后生成
class MinutesFallbackRules(FallbackRules):
    """纪要降级拼装：headline + 5 段（带标签）+ 免责声明。"""

    sections = [
        Raw("headline"),
        Join("executive_summary", "会议要点"),
        Join("key_decisions", "关键决策"),
        Join(
            "personally_relevant_points",
            label={"objective": "全员执行要点", "personal": "职责相关事项"},
        ),
        Join("risks_and_blockers", "风险与阻塞"),
        Join("unresolved_questions", "未决问题"),
        Join("history_comparison", "与历史对比"),
    ]
    empty_text = "请直接参考会议原文。"
    empty_purpose = True
    disclaimer = False


MINUTES_FALLBACK_RULES = MinutesFallbackRules()

__all__ = [
    "MINUTES_GENERATION_OUTPUT_CONTRACT",
    "MINUTES_SUPERVISOR_OUTPUT_CONTRACT",
    "MINUTES_FALLBACK_RULES",
]
