"""模板 v2 草稿：按场景对模板正文做轻度内容优化，输出到 ``template_v2/`` 供对比。

``template/*.md`` 是权威 YAML 的逐字副本（由 ``sync_templates.py`` 生成，不得手工改）。
本脚本不碰 ``template/``，而是把优化写成可逐条复核的替换表 ``EDITS``（字段 + 原文片段 →
新片段 + 理由），在内存里应用到 YAML 模板后，按同一渲染格式写同名文件到 ``template_v2/``：

    python tools/scripts/draft_template_v2.py --write   # 生成/刷新 template_v2/（含 DIFF.md、README.md）
    python tools/scripts/draft_template_v2.py --check   # 校验 template_v2/ 与 YAML+EDITS 一致
    python tools/scripts/draft_template_v2.py --apply   # 落地：把 EDITS 写进权威 YAML + 刷新 template/*.md

优化目标：提升各场景生成内容的正确率与完整度（修正措辞与串场景表述、补必要的防错口径），
仅动方括号内的内容提示文字，不改动整体结构、不给现有章节新增字段。以下为硬约束
（脚本断言，不符即报错）：

1. 每条替换在目标字段中恰好命中 1 次（防手滑改错位置）；
2. 结构不变：优化前后 ``format`` 的标题行（``# …``）与表格行（``| … |``）必须完全一致；
3. 占位符示例行（如 ``- [ ] 任务内容``、``> 原话引语……``）保持原样。

落地用 ``--apply``：按字节替换 YAML（保留原换行与缩进），随后读回 YAML 校验每个模板的
``format`` / ``requirement`` 与草稿逐字一致，最后调 ``sync_templates`` 刷新 ``template/*.md``。
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_templates import (  # noqa: E402
    ROOT,
    TEMPLATE_YAML,
    check_copies,
    check_readme,
    load_templates,
    render_copy,
    write_copies,
)

V2_DIR = ROOT / "template_v2"

# 每条 = 一个模板的一处优化：field ∈ {format, requirement}，old 必须唯一命中。
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
    {
        "key": "daily_journal_general_minutes",
        "field": "requirement",
        "old": "目的为生成符合选定长度的结构化会议摘要和确保摘要内容准确反映会议核心内容，语气为客观的集成陈述、零情感色彩的官方口吻和非人格化权威表述",
        "new": "客观生成符合选定长度的结构化会议摘要，确保准确反映会议核心内容；语气为客观的集成陈述、零情感色彩，采用非人格化的官方口吻",
        "why": "写作要求是半句病句（「目的为生成…和确保…」），改为可执行的祈使句，含义不变",
    },
)

_HEADING_RE = re.compile(r"^\s*#")


def _structure(text: str) -> list[str]:
    """结构行 = 标题行 + 表格行（优化前后必须一致）。"""
    return [ln.strip() for ln in text.splitlines() if _HEADING_RE.match(ln) or ln.strip().startswith("|")]


def build_drafts() -> tuple[list[dict[str, object]], str]:
    """把 EDITS 应用到 YAML 模板 → (v2 草稿列表, 状态)。

    状态：``pending`` = YAML 还是原文，需应用 EDITS；``applied`` = EDITS 已在 YAML 中生效
    （此时草稿即 YAML 现状，--check/--write 仍可用；--apply 幂等返回成功）。
    """
    drafts: dict[str, dict[str, object]] = {str(item["key"]): dict(item) for item in load_templates()}
    hits = 0

    for edit in EDITS:
        key, field, old, new = edit["key"], edit["field"], edit["old"], edit["new"]
        if key not in drafts:
            raise SystemExit(f"EDITS 指向未知模板：{key}")
        text = str(drafts[key][field])
        has_old, has_new = old in text, new in text
        if has_new:
            hits += 1
            continue
        if not has_old:
            raise SystemExit(f"{key}.{field} 既无原文也无新文（YAML 已被改过？）：{old[:40]}…")
        if text.count(old) != 1:
            raise SystemExit(f"{key}.{field} 命中 {text.count(old)} 次（应为 1）：{old[:40]}…")
        drafts[key][field] = text.replace(old, new, 1)

    out: list[dict[str, object]] = []
    for item in load_templates():
        key = str(item["key"])
        draft = drafts[key]
        if _structure(str(item["format"])) != _structure(str(draft["format"])):
            raise SystemExit(f"{key}：优化改动了标题/表格结构，违反结构不变约束")
        out.append(draft)
    return out, ("applied" if hits == len(EDITS) else "pending" if hits == 0 else "partial")


def render_all(drafts: list[dict[str, object]]) -> dict[str, str]:
    """组合 key（``场景_模板``）→ 渲染后的文件内容。"""
    return {str(d["key"]): render_copy(d) for d in drafts}


def write_all(drafts: list[dict[str, object]]) -> int:
    want = render_all(drafts)
    items = {str(item["key"]): item for item in load_templates()}
    changed = 0
    V2_DIR.mkdir(parents=True, exist_ok=True)
    for key, text in want.items():
        path = V2_DIR / f"{items[key]['template']}.md"
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8")
        changed += 1
    print(f"template_v2：{len(want)} 个文件，改动 {changed} 个")
    (V2_DIR / "DIFF.md").write_text(_diff_md(want, items), encoding="utf-8")
    (V2_DIR / "README.md").write_text(_readme_md(drafts), encoding="utf-8")
    print("已写出 template_v2/DIFF.md、template_v2/README.md")
    return changed


def _diff_md(want: dict[str, str], items: dict[str, dict[str, object]]) -> str:
    """全部逐字差异（unified diff，n=1）汇总成一份可读文件。"""
    lines = [
        "# 模板优化差异（template → template_v2）",
        "",
        "由 `python tools/scripts/draft_template_v2.py --write` 生成；`-` 原模板，`+` 优化稿。",
        "结构（标题、表格、占位符示例行）未改动，差异全部落在方括号内容提示或 requirement 上。",
        "",
        "本文件是生成时刻的对比快照。执行 `--apply` 落地后 `template/` 已与 `template_v2/` 一致，",
        "此后要看运行时生效的改动请用 `git diff template/`（副本）与 `git diff cm_template_v2_changed_0722.yaml`（权威源）。",
        "",
    ]
    left = ROOT / "template"
    for key, text in want.items():
        name = str(items[key]["template"])
        base = (left / f"{name}.md").read_text(encoding="utf-8")
        if base == text:
            continue
        lines.append(f"## {items[key]['order']}. {items[key]['name']}（`{key}`）")
        lines.append("")
        lines.append("```diff")
        lines.extend(
            ln
            for ln in difflib.unified_diff(
                base.splitlines(),
                text.splitlines(),
                f"template/{name}.md",
                f"template_v2/{name}.md",
                lineterm="",
                n=1,
            )
            if ln.startswith(("+", "-", "@"))
        )
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _readme_md(drafts: list[dict[str, object]]) -> str:
    """说明 + 每个模板的修改点与理由（便于逐条复核）。"""
    by_key: dict[str, list[dict[str, str]]] = {}
    for edit in EDITS:
        by_key.setdefault(edit["key"], []).append(edit)
    lines = [
        "# template_v2（优化稿，供对比）",
        "",
        "本目录是 `template/*.md` 的优化稿：逐字差异见 [DIFF.md](DIFF.md)，"
        "逐文件对比可 `diff -u template/xx.md template_v2/xx.md`。",
        "",
        "- 优化范围：仅方括号内的内容提示与 1 处 requirement 措辞；",
        "- 整体结构不动：标题、章节顺序、表格、占位符示例行全部保持原样；",
        "- 生效方式：本目录**不被运行时读取**——`python tools/scripts/draft_template_v2.py --apply` "
        "把 EDITS 写进权威 `cm_template_v2_changed_0722.yaml`（`templates[].format` / `requirement`），"
        "并刷新 `template/` 副本；",
        "- 落地后的改动明细看 `git diff template/` 与 `git diff cm_template_v2_changed_0722.yaml`；",
        "- 重新生成/校验：`python tools/scripts/draft_template_v2.py --write|--check`。",
        "",
        "## 修改点与理由",
        "",
    ]
    for draft in drafts:
        key = str(draft["key"])
        edits = by_key.get(key)
        if not edits:
            continue
        lines.append(f"### {draft['order']}. {draft['name']}（`{key}`）")
        lines.append("")
        for edit in edits:
            lines.append(f"- **[{edit['field']}]** {edit['why']}")
        lines.append("")
    unchanged = [f"{d['name']}（`{d['key']}`）" for d in drafts if str(d["key"]) not in by_key]
    if unchanged:
        lines.append("## 未改动（现有措辞已准确、完整）")
        lines.append("")
        lines.append("- " + "、".join(unchanged))
        lines.append("")
    return "\n".join(lines)


def check_all(drafts: list[dict[str, object]], want: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if not V2_DIR.is_dir():
        return ["template_v2/ 不存在（先跑 --write）"]
    items = {str(i["key"]): i for i in load_templates()}
    for key, text in want.items():
        name = str(items[key]["template"])
        path = V2_DIR / f"{name}.md"
        if not path.is_file():
            problems.append(f"{path.name}：缺失")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"{path.name}：与 YAML+EDITS 不一致")
    # DIFF.md 是 --write 时刻的对比快照（落地后 template/ 与之相等而失去对比意义），故不参与校验；
    # README.md 完全由 EDITS 生成，参与校验以防手改。
    path = V2_DIR / "README.md"
    if not path.is_file() or path.read_text(encoding="utf-8") != _readme_md(drafts):
        problems.append("README.md：未随 EDITS 更新（跑 --write）")
    return problems


def apply_to_yaml(drafts: list[dict[str, object]], state: str) -> list[str]:
    """把 EDITS 按字节写进权威 YAML，读回校验后再刷新 template/*.md。返回问题列表。"""
    if state == "applied":
        print("EDITS 已全部生效，跳过写入（幂等）")
        changed = write_copies(load_templates())
        print(f"template/*.md 已刷新（改动 {changed} 个文件）")
        return check_copies(load_templates()) + check_readme(load_templates())
    if state != "pending":
        return ["EDITS 与 YAML 只部分匹配（原文/新文混杂），请先人工核对再落地"]
    raw = TEMPLATE_YAML.read_bytes().decode("utf-8")
    problems = [
        f"{edit['key']}.{edit['field']} 在 YAML 中命中 {raw.count(edit['old'])} 次（应为 1）：{edit['old'][:30]}…"
        for edit in EDITS
        if raw.count(edit["old"]) != 1
    ]
    if problems:
        return ["落地前校验失败（YAML 可能已被改过或已应用过本表）：", *problems]

    text = raw
    for edit in EDITS:
        text = text.replace(edit["old"], edit["new"], 1)
    TEMPLATE_YAML.write_bytes(text.encode("utf-8"))
    print(f"已写入 {TEMPLATE_YAML.name}（{len(EDITS)} 处替换）")

    # 读回 YAML：每个模板的 format/requirement 必须与草稿逐字一致
    now = {str(item["key"]): item for item in load_templates()}
    for draft in drafts:
        key = str(draft["key"])
        for field in ("format", "requirement"):
            if str(now[key][field]) != str(draft[field]):
                problems.append(f"{key}.{field} 读回后与草稿不一致")
    if problems:
        return problems

    changed = write_copies(load_templates())
    print(f"template/*.md 已刷新（改动 {changed} 个文件）")
    return check_copies(load_templates()) + check_readme(load_templates())


def main() -> int:
    ap = argparse.ArgumentParser(description="生成/校验/落地 template_v2 优化稿")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="按 YAML+EDITS 生成 template_v2/")
    group.add_argument("--check", action="store_true", help="校验 template_v2/ 是否为当前 EDITS 的结果")
    group.add_argument("--apply", action="store_true", help="把 EDITS 写进权威 YAML，并刷新 template/*.md（幂等）")
    args = ap.parse_args()

    drafts, state = build_drafts()
    want = render_all(drafts)
    edited = len({e["key"] for e in EDITS})
    print(f"EDITS：{len(EDITS)} 处替换，覆盖 {edited} 个模板（共 {len(drafts)} 个可见模板）；状态：{state}")

    problems: list[str] = []
    if args.apply:
        problems = apply_to_yaml(drafts, state)
        if not problems:
            print("OK：EDITS 已生效（YAML + template/ 副本一致）")
    else:
        if args.write:
            write_all(drafts)
        problems = check_all(drafts, want)
        if not problems:
            print("OK：template_v2/ 与 YAML+EDITS 一致")
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
