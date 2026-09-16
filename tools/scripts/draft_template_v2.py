"""模板优化工具：把「逐条可复核的文本优化」应用到模板文件。

**权威模板源就是 ``template_v2/*.md``**（运行时直接读这一份，没有 YAML、没有第二兜底源）。
每个模板文件结构固定：

    # {中文名}

    <!-- requirement
    {写作要求}
    -->

    {format 正文}

优化以替换表 ``EDITS``（原文片段 → 新片段 + 理由）表达，逐条应用到对应模板文件：

    python tools/scripts/draft_template_v2.py --apply   # 落地（幂等、可增量）
    python tools/scripts/draft_template_v2.py --check   # 只校验：每条是否都已生效（漂移则退出码 1）

**模板写法公约**（新增/修改模板时遵守；与运行时规则互相印证）：

1. ``requirement`` 只写底线（不得丢失/篡改/臆断/失真），**不写形态词**（逐条 / 分项 /
   不得合并 / 保留原始语义）——形态由 ``format`` 与尺寸规则决定；
2. 兜底写成祈使式（"缺项直接写「无」"），**禁用"若…则…"条件句**（会被模型复述进正文）；
3. 同类/对立信息用"可归并、不可抹平"的措辞。

硬约束（脚本断言，不符即报错）：每条替换在目标文件里**恰好命中 1 次**；
模板的标题行与表格行必须齐备（``check_structure``）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "template_v2"
sys.path.insert(0, str(ROOT))

EDITS: tuple[dict[str, str], ...] = (
    # ── 会议纪要 ──────────────────────────────────────────────────────────────
    {
        "key": "meeting_minutes_project_progress",
        "field": "format",
        "old": "[一段话概括本次项目进度会的主要内容]",
        "new": "[一段话概括项目阶段、整体健康度及本次进度会的主要内容]",
        "why": "进度会概况应落在「阶段 + 健康度」两条主线上（需求：聚焦项目健康度）",
    },
    {
        "key": "meeting_minutes_project_progress",
        "field": "format",
        "old": "或利用表格形式进行总结]",
        "new": "或利用表格形式进行总结；状态统一使用 ✅已完成 / 🔄进行中 / ⛔阻塞 标注]",
        "why": "补状态口径，避免同一份纪要里状态用词各异（不加字段、不增量）",
    },
    {
        "key": "meeting_minutes_project_progress",
        "field": "format",
        "old": "关键交付物**具体内容**；",
        "new": "关键交付物用 **具体内容** 强调；",
        "why": "原文漏了「用…强调」，占位符说明不成句",
    },
    {
        "key": "meeting_minutes_decision_review",
        "field": "format",
        "old": "最终结论请 **具体内容** 呈现。",
        "new": "最终结论用 **具体内容** 强调。",
        "why": "与其他章节统一为「用 **…** 强调」的占位符口径",
    },
    {
        "key": "meeting_minutes_retrospective_session",
        "field": "format",
        "old": "[一段话概括本次总结复盘会的主要内容]",
        "new": "[一段话概括预期目标、实际结果及本次复盘会的主要内容]",
        "why": "复盘概况缺「目标 vs 结果」的对比（需求：还原预期目标与实际结果）",
    },
    {
        "key": "meeting_minutes_retrospective_session",
        "field": "format",
        "old": "可用「现象 → 原因 」的结构呈现",
        "new": "可用「现象 → 根因」的结构呈现",
        "why": "错字与多余空格：需求要求归因到根本原因，措辞统一为「根因」",
    },
    # ── 学习笔记 ──────────────────────────────────────────────────────────────
    {
        "key": "study_notes_class_transcript",
        "field": "format",
        "old": "[一段话概括本次课程的主要内容]",
        "new": "[一段话概括课程名称/章节及本次课程的主要内容]",
        "why": "课程概况补课程名称/章节，便于日后检索复习",
    },
    {
        "key": "study_notes_class_transcript",
        "field": "format",
        "old": "[明确教师强调的复习重点及教师推荐的学习建议，若存在作业内容也可列出]",
        "new": "[明确教师布置的作业及提交要求（原文提及时）、强调的复习重点与推荐的学习建议]",
        "why": "作业与提交要求是可执行项，不应作为「也可列出」的补充",
    },
    {
        "key": "study_notes_special_lecture",
        "field": "format",
        "old": "[以一段话形式概括本次讲座的主要内容]",
        "new": "[以一段话概括讲座主题、主讲人及机构（原文提及时）、核心内容]",
        "why": "讲座概况补主讲人/机构（需求：专有名词须准确提取）",
    },
    {
        "key": "study_notes_special_lecture",
        "field": "format",
        "old": "需确保内容详略得当，重点突出，避免篇幅失衡或核心信息缺失。若讲座中存在多个子论点或争议点，应分别列出并明确区分，避免内容重复或混淆。",
        "new": "需确保详略得当、重点突出；存在多个子论点或争议点时应分别列出，避免内容重复或混淆。",
        "why": "同义反复压缩为一句，降低提示噪声（信息量不变）",
    },
    {
        "key": "study_notes_special_lecture",
        "field": "format",
        "old": "摘录主讲人讲座中的核心金句与深刻见解，以引用格式呈现，突出其思想价值与启发意义。每句金句应附简要说明其背景或意义，以增强理解与记忆。摘录内容应严格基于原文语境，避免脱离上下文的孤立引用。若金句在原文中与特定论点或案例相关，应简要说明其关联性，以体现其在讲座中的具体作用与价值。",
        "new": "摘录主讲人讲座中的核心金句与深刻见解，以引用格式呈现；摘录须严格基于原文语境，并简要说明其背景或关联论点，避免脱离上下文的孤立引用。",
        "why": "四句压成一句，保留「忠于原文语境 + 交代背景」两条硬要求",
    },
    {
        "key": "study_notes_group_seminar",
        "field": "format",
        "old": "[一段话概括讨论主题、及核心探讨问题的主要内容]",
        "new": "[一段话概括讨论主题、成员构成及核心探讨问题]",
        "why": "修正顿号病句，并补成员构成（小组讨论的必要背景）",
    },
    {
        "key": "study_notes_group_seminar",
        "field": "format",
        "old": "标明分歧所在]",
        "new": "标明发言人身份与分歧所在]",
        "why": "需求要求不遗漏关键发言，需能对应到人",
    },
    {
        "key": "study_notes_knowledge_memo",
        "field": "format",
        "old": "[以一段话完整概括会议讨论的知识领域、涉及的核心议题、主要观点及整体逻辑框架，确保涵盖所有重要学者或发言人的核心观点，避免遗漏关键内容。语言需简洁清晰，突出会议主题与讨论重点]",
        "new": "[以一段话概括本笔记涉及的知识领域、核心议题、主要观点及整体逻辑框架，涵盖所有关键概念、学者观点与结论，避免遗漏。语言简洁清晰，突出知识主题与脉络]",
        "why": "串场景修正：知识笔记不是会议，「会议讨论/发言」改为知识域表述",
    },
    {
        "key": "study_notes_knowledge_memo",
        "field": "format",
        "old": "[按会议内容梳理关键定义",
        "new": "[按原文内容梳理关键定义",
        "why": "同上：会议 → 原文",
    },
    {
        "key": "study_notes_knowledge_memo",
        "field": "format",
        "old": "[提炼会议中的重点内容、易混淆点及待澄清问题，易错点以 **具体内容** 强调。需涵盖知识的主要内容，严格依据原文内容进行总结，不要随意扩展]",
        "new": "[提炼原文的核心结论、易混淆点及待澄清问题，易错点以 **具体内容** 强调；严格依据原文总结，不要随意扩展]",
        "why": "串场景修正 + 明确产出物是「核心结论」（与章节名一致）",
    },
    {
        "key": "study_notes_debate_forum",
        "field": "format",
        "old": "[一段话概括辩题、正反方立场、及整体辩论内容]",
        "new": "[一段话概括辩题、正反方立场及整体辩论内容]",
        "why": "顿号病句（同小组讨论模板）",
    },
    {
        "key": "study_notes_debate_forum",
        "field": "format",
        "old": '体现"攻—防"的对应关系',
        "new": "体现「攻—防」的对应关系",
        "why": "直引号统一为书名号式引号，与其余模板标点一致",
    },
    # ── 对话访谈 ──────────────────────────────────────────────────────────────
    {
        "key": "dialogue_interview_research_dialogue",
        "field": "format",
        "old": "[基于访谈内容提炼核心洞察、产品/服务优化建议、被访谈者倾向、表达等内容，忠实与原文，不要过度总结]",
        "new": "[基于访谈内容提炼核心洞察、产品/服务优化建议及受访者的偏好与倾向性表达，忠实于原文，不要过度总结]",
        "why": "错字「忠实与原文」→「忠实于原文」；「倾向、表达」改为可执行的表述",
    },
    {
        "key": "dialogue_interview_interview_transcript",
        "field": "format",
        "old": "[关注以下内容：受访者观点/事实陈述,客观记录受访者就该议题提供的信息、描述的情况、陈述的观点。使用要点形式，保持原意，已确认的信息点，总结在此议题上双方达成一致或已验证的事实。根据【待处理文本】进行总结标题与内容并生成markdown格式内容，可以多层级或者用表格解释，尽可能的不遗漏细节，但不要过度总结。]",
        "new": "[按议题分节记录受访者的观点与事实陈述，客观记录其就该议题提供的信息、描述的情况；已确认的信息单列，并标明双方达成一致或已验证的事实。使用要点形式并保持原意，可多层级或用表格呈现；尽可能不遗漏细节，但不要过度总结]",
        "why": "删掉内部变量名【待处理文本】（会泄漏到提示词），并拆清「记录/已确认/呈现方式」三层要求",
    },
    # ── 求职面试 ──────────────────────────────────────────────────────────────
    {
        "key": "job_interview_hiring_report",
        "field": "format",
        "old": "[一段话概括候选人基本信息、应聘岗位、面试轮次及面试过程中的具体内容]",
        "new": "[一段话概括候选人基本信息、应聘岗位、面试轮次及整体面试表现]",
        "why": "「面试过程中的具体内容」指向不明，改为可评估的「整体面试表现」",
    },
    {
        "key": "job_interview_hiring_report",
        "field": "format",
        "old": "严格依据原文，不要过度总结和推断]",
        "new": "并给出推进建议（原文提及时）；严格依据原文，不要过度总结和推断]",
        "why": "面试报告缺结论项：补推进建议，避免只罗列观察",
    },
    {
        "key": "job_interview_interview_debrief",
        "field": "format",
        "old": "逐项梳理；  每个环节需分别总结",
        "new": "逐项梳理；每个环节需分别总结",
        "why": "多余空格",
    },
    {
        "key": "job_interview_interview_debrief",
        "field": "format",
        "old": "[基于面试官反馈，提炼出需提升的能力点、需补充的知识领域及后续需跟进的事项]",
        "new": "[基于面试官反馈，按优先级提炼需提升的能力点、需补充的知识领域及后续跟进事项]",
        "why": "改进计划补优先级，便于取舍",
    },
    # ── 医疗咨询 ──────────────────────────────────────────────────────────────
    {
        "key": "medical_consultation_psychological_session",
        "field": "format",
        "old": "[一段话概括本次咨询的主要内容]",
        "new": "[一段话概括咨询目标、来访者核心困扰及本次咨询的主要内容]",
        "why": "咨询概况补咨询目标，便于跨次咨询衔接",
    },
    {
        "key": "medical_consultation_psychological_session",
        "field": "format",
        "old": "建议内容等，保持中立客观的描述；",
        "new": "建议内容等；情绪变化与风险评估（原文提及时）须明确记录，保持中立客观的描述；",
        "why": "补情绪变化与风险评估两条临床必要信息（仅在原文提及时记录，不编造）",
    },
    # ── 法律咨询 ──────────────────────────────────────────────────────────────
    {
        "key": "legal_consultation_court_transcript",
        "field": "format",
        "old": "双方辩论交点",
        "new": "双方辩论的争议焦点",
        "why": "错词：应为「争议焦点」（需求：聚焦争议焦点）",
    },
    {
        "key": "legal_consultation_court_transcript",
        "field": "format",
        "old": "[提炼庭审结果]",
        "new": "[归纳争议焦点与庭审结果：当庭宣判结果、调解意见或下次开庭安排；未决事项一并说明]",
        "why": "原文仅 6 字，未宣判/调解场景会丢关键信息，按庭审实际情形补齐",
    },
    {
        "key": "legal_consultation_contract_vetting",
        "field": "format",
        "old": "[一段话概括合同名称、签约双方、及合同沟通的整体内容]",
        "new": "[一段话概括合同名称、签约双方及本次合同审核的整体情况]",
        "why": "顿号病句 + 「合同沟通」与审核场景不符",
    },
    {
        "key": "legal_consultation_contract_vetting",
        "field": "format",
        "old": "验收标准等核心条款；",
        "new": "验收标准、违约责任、争议解决等核心条款；",
        "why": "合同审核的必要条款缺违约责任与争议解决（需求点名违约责任）",
    },
    # ── 发布会公文 ────────────────────────────────────────────────────────────
    {
        "key": "press_conference_product_launch",
        "field": "format",
        "old": "可包含现场演示情况、发言人精彩语录等内容，总结此产品的差异化竞争力所在]",
        "new": "对比同类产品总结差异化竞争力；现场演示与发言人关键表述可作为佐证]",
        "why": "定位章节混入了演示/语录（应属佐证），改为明确「对比同类产品的差异化」",
    },
    {
        "key": "press_conference_product_launch",
        "field": "format",
        "old": "每个功能模块应有明确的过渡句或小结，避免信息跳跃或突兀。",
        "new": "各维度参数须与原文一致，不得夸大或编造未提及的参数。",
        "why": "写作技巧提示改为本条线最关键的准确性红线（参数与原文一致）",
    },
    {
        "key": "press_conference_government_bulletin",
        "field": "format",
        "old": "[一段话概括报告名称、发布单位、核心主题及整体基调]",
        "new": "[一段话概括报告名称、发布单位、报告期间及核心主题与整体基调]",
        "why": "政府报告缺「报告期间」，指标口径无法定位",
    },
    {
        "key": "press_conference_government_bulletin",
        "field": "format",
        "old": "[按经济、民生、环保等领域分类梳理重点工作及具体措施，可分章节呈现，重点内容、承诺或表态可用 > 引用]",
        "new": "[按原文涉及的领域（如经济、民生、环保）分类梳理重点工作及具体措施，可分章节呈现，重点承诺或表态可用 > 引用]",
        "why": "领域改为随原文而定，避免预设报告不涉及的领域",
    },
    # ── 日常记录 ──────────────────────────────────────────────────────────────
    # ── 修复：requirement 用「形态词」表达「保真目标」，与 format 的收敛形态互斥 ──
    #   写法公约：requirement 只写底线（不得丢/不得改/不得失真），形态（逐条/合并/篇幅）只由 format 定。
    {
        "key": "meeting_minutes_team_meeting",
        "field": "requirement",
        "old": "不遗漏任何成员的发言",
        "new": "不得遗漏任何成员的关键结论、诉求与承诺（同类可归并，信息点不得丢）",
        "why": "「不遗漏发言」是形态词，与 format「禁止逐分项开条」互斥；改为底线词",
    },
    {
        "key": "meeting_minutes_workshop_session",
        "field": "requirement",
        "old": "完整保留有价值的创新思路；避免流水账式记录，不遗漏关键分歧",
        "new": "避免流水账式记录，关键创新思路与分歧不得丢（同类可归并，不逐项铺开）",
        "why": "同上：把「完整保留/不遗漏」收成「不得丢」底线，形态交给 format",
    },
    {
        "key": "meeting_minutes_decision_review",
        "field": "requirement",
        "old": "不得篡改、合并或主观臆断评审意见",
        "new": "不得篡改、臆断或混淆归属（同类可归并，对立立场不得抹平）",
        "why": "「不得合并」与 format「先合并同类」冲突；改为「可归并、不可抹平」",
    },
    {
        "key": "meeting_minutes_exchange_forum",
        "field": "requirement",
        "old": "对关键表述、特殊语气或语境依赖较强的语句，应通过引用或转述方式保留其原始语义，以确保上下文理解的准确性与完整性",
        "new": "关键表态可用 `> 引用` 原文原话，但引用仅限关键表态、不宜多；压缩不得改变原意与因果关系",
        "why": "「保留原始语义」近乎禁止压缩，与篇幅上限冲突；限定为「关键表态才引用」",
    },
    # ── 修复：条件式说明会被模型复述进正文（如「以上改进计划均未明确责任人和时间，填写“无”。」）──
    {
        "key": "meeting_minutes_project_progress",
        "field": "format",
        "old": "若某项在原文未提及则标注无。",
        "new": "缺项直接写「无」，不写说明句。",
        "why": "把「若…则标注无」改成不可复述的写法，避免模型把规则当正文写出来",
    },
    {
        "key": "meeting_minutes_retrospective_session",
        "field": "format",
        "old": "若原文不存在明确责任人或时间，则填写“无”即可，禁止编造",
        "new": "缺责任人或时间时直接写「无」（不写说明句），不编造",
        "why": "同上：该写法曾导致「…均未明确责任人和时间，填写“无”。」整句进入正文",
    },
    {
        "key": "meeting_minutes_exchange_forum",
        "field": "format",
        "old": "若某项不存在则填写“无”；",
        "new": "缺项直接写「无」（不写说明句）；",
        "why": "同上：条件式说明有被复述的风险",
    },
    {
        "key": "daily_journal_conversation_transcript",
        "field": "format",
        "old": "若对话中提及承诺及后续行动可在此章节呈现，若不存在则无需此章节",
        "new": "有承诺或后续行动才写本节，无内容则整节省略（不要写「本节无内容」之类说明）",
        "why": "同上：把「若不存在则无需此章节」改成不可复述的写法",
    },
    {
        "key": "daily_journal_general_minutes",
        "field": "requirement",
        "old": "目的为生成符合选定长度的结构化会议摘要和确保摘要内容准确反映会议核心内容，语气为客观的集成陈述、零情感色彩的官方口吻和非人格化权威表述",
        "new": "客观生成符合选定长度的结构化会议摘要，确保准确反映会议核心内容；语气为客观的集成陈述、零情感色彩，采用非人格化的官方口吻",
        "why": "写作要求是半句病句（「目的为生成…和确保…」），改为可执行的祈使句，含义不变",
    },
    {
        "key": "press_conference_product_launch",
        "field": "format",
        "old": "| 维度 | 本产品 | 上代/竞品 | 提升 |\n| --- | --- | --- | --- |",
        "new": "| 维度 | 本产品 | 上代/竞品 | 提升 |\n| --- | --- | --- | --- |\n| … | … | … | … |",
        "why": "补一行占位数据行：表格回到程序拼装路径（表头逐字保真、行由模型填），消除重复表头与门禁误判",
    },
)

_HEADING_RE = re.compile(r"^\s*#")


def _structure(text: str) -> list[str]:
    """结构行 = 标题行 + 表格行（模板文件必须始终具备）。"""
    return [ln.strip() for ln in text.splitlines() if _HEADING_RE.match(ln) or ln.strip().startswith("|")]


def _template_id(edit: dict[str, str]) -> str:
    """EDITS.key（内部键 ``{场景ID}_{模板ID}``）→ 模板 ID（= 模板文件名）。

    场景 ID 自身含下划线（meeting_minutes 等），按已知场景前缀去掉即可。
    """
    from app.config import SCENARIO_NAMES

    key = edit["key"]
    tid = key
    for sid in sorted(SCENARIO_NAMES, key=len, reverse=True):
        if key.startswith(sid + "_"):
            tid = key[len(sid) + 1 :]
            break
    if not (TEMPLATE_DIR / (tid + ".md")).is_file():
        raise SystemExit("模板文件不存在：" + tid + ".md（EDITS.key=" + edit["key"] + "）")
    return tid


def check_structure() -> None:
    """模板文件必须保留标题/表格结构行（防止误删章节）。"""
    for path in sorted(TEMPLATE_DIR.glob("*.md")):
        if path.stem.lower() in {"readme", "diff"}:
            continue
        if not _structure(path.read_text(encoding="utf-8")):
            raise SystemExit(f"{path.name}：读不到任何标题/表格结构行")


def apply_all(*, dry: bool = False) -> tuple[int, int]:
    """把 EDITS 逐条应用到模板文件；返回 (本次应用数, 已生效数)。"""
    applied = already = 0
    for edit in EDITS:
        path = TEMPLATE_DIR / (_template_id(edit) + ".md")
        text = path.read_text(encoding="utf-8")
        old, new = edit["old"], edit["new"]
        if new in text:
            already += 1
            continue
        if old not in text:
            raise SystemExit(path.name + "：既无原文也无新文（文件被手工改过？）：" + old[:40] + "…")
        if text.count(old) != 1:
            raise SystemExit(path.name + "：原文命中 " + str(text.count(old)) + " 次（应为 1）：" + old[:40] + "…")
        if not dry:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        applied += 1
    return applied, already


def verify_registry() -> list[str]:
    """用运行时同一套解析读回模板：29 条、名称/要求/正文齐备、EDITS 新文已生效。"""
    import app.config as cfg

    registry = cfg.template_registry()
    problems: list[str] = []
    if len(registry) != 29:
        problems.append("注册表 " + str(len(registry)) + " 条（应为 29）")
    by_id = {str(v.get("template")): v for v in registry.values()}
    for edit in EDITS:
        tid = _template_id(edit)
        item = by_id.get(tid)
        if item is None:
            problems.append(tid + "：注册表里找不到")
            continue
        blob = str(item["name"]) + str(item["requirement"]) + str(item["format"])
        if edit["new"] not in blob:
            problems.append(tid + "：新文未生效")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="把 EDITS 应用到 template_v2/*.md（运行时模板源）")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="落地：把 EDITS 写进模板文件（幂等、可增量）")
    group.add_argument("--check", action="store_true", help="只校验每条是否已生效（漂移退出码 1）")
    args = ap.parse_args()

    check_structure()
    print("EDITS：" + str(len(EDITS)) + " 处替换，覆盖 " + str(len({e['key'] for e in EDITS})) + " 个模板")
    if args.apply:
        applied, already = apply_all()
        print("本次应用 " + str(applied) + " 处，已生效 " + str(already) + " 处")
    else:
        applied, already = apply_all(dry=True)
        if applied:
            print("发现 " + str(applied) + " 处未生效（跑 --apply 落地）：", file=sys.stderr)
            for edit in EDITS:
                path = TEMPLATE_DIR / (_template_id(edit) + ".md")
                if edit["new"] not in path.read_text(encoding="utf-8"):
                    print("  - " + edit["key"] + "：" + edit["why"], file=sys.stderr)
            return 1
        print("OK：EDITS 全部已生效（" + str(already) + " 处）")

    problems = verify_registry()
    if problems:
        print("注册表校验失败：", file=sys.stderr)
        for problem in problems:
            print("  - " + problem, file=sys.stderr)
        return 1
    print("OK：template_v2/*.md 即运行时模板源，29 条齐备、EDITS 生效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
