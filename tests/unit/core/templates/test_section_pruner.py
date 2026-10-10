"""tests/unit/core/templates/test_section_pruner.py -- 模板装配器、自适应隐去与 SectionPruner 单元测试。"""
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
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FAIL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    PASS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
    check,
)

def test_table_carried_column_allows_blank() -> None:
    """表格承载栏允许为空：拼装产物不强填缺省词、表格内容照常装配。"""
    from core.templates.router._placeholder import assemble_placeholder_output

    tpl = (
        "# [候选人概况]\n[一段话概括候选人]\n\n"
        "# [能力评估]\n[**本栏明细由下表承载**（本栏不再另写说明文字、不要写「未提及」）]\n"
        "| 评估维度 | 评级 |\n| --- | --- |\n| [维度] | [评级] |\n"
    )
    out = assemble_placeholder_output(
        tpl,
        {"1": "候选人概况内容。", "2": ""},
        tables=[[["综合分析", "良"]]],
    )
    check("表格承载栏为空 ⇒ 终稿不含「未提及」", bool(out) and "未提及" not in (out or ""), (out or "")[:100])
    check("表格内容照常装配", "综合分析" in (out or ""), (out or "")[:140])

def test_paragraph_split() -> None:
    """段落字数超限：按句界确定性拆段（零 LLM 调用），拆完不再报「超出段落字数上限」。"""
    from core.execution.gate import (
        enforce_render_output,
        gate_render_output,
        split_overlong_paragraphs,
        split_overlong_paragraphs_except_first,
    )
    from core.templates.template_eval import parse_section_char_budgets

    from core.templates.router._base import split_template_meta, wrap_template_requirement

    body, req = split_template_meta(
        "# 甲\n\n<!-- requirement\n客观记录\n-->\n\n"
        "# [摘要]\n[一段话（最多 3 段、每段不超过 400 字）交代要点]\n"
    )
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines = lines[i + 1 :]
            break
    tpl = wrap_template_requirement("\n".join(lines).strip(), req)
    check("拆分用模板：段落上限已识别",
          any(b["hi"] == 400 and b.get("scope") == "paragraph"
              for b in parse_section_char_budgets(tpl)),
          f"{parse_section_char_budgets(tpl)}")

    long_para = "本次会议围绕小区物业服务与业主权益展开专项讨论。" * 30  # ≈690 汉字
    doc = f"# 摘要\n{long_para}\n"
    fixed, _ = split_overlong_paragraphs(doc, tpl)
    body_only = fixed.split("\n", 1)[1] if "\n" in fixed else fixed
    parts = [p for p in body_only.split("\n\n") if p.strip()]
    han_of = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s))
    check("超长段被按句界拆开（≥2 段且每段汉字 ≤ 上限）",
          len(parts) >= 2 and all(han_of(p) <= 400 for p in parts),
          f"段数={len(parts)} 各段汉字={[han_of(p) for p in parts]}")
    check("拆分只加换行、不改文字",
          re.sub(r"\s", "", fixed) == re.sub(r"\s", "", doc), "")
    gate = gate_render_output(tpl, fixed)
    check("拆完不再报「超出段落字数上限」",
          not any("超出段落字数上限" in x for x in gate["issues"]), f"{gate['issues']}")

    # 段边界丢换行曾把 `# 栏名` 粘到上一栏末尾：渲染层对同一文本跑两次 enforce，
    # 第一遍把空行削成单换行、第二遍直接粘连（2026-09-22 真链路实测）。
    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    two = "# 分段速览\n" + long_para + "\n\n# 要点梳理\n- 乙\n"
    once, n_once = split_overlong_paragraphs_except_first(two, gm)
    twice, _ = split_overlong_paragraphs_except_first(once, gm)
    check("段边界换行保留（跑两次也不把 `# 要点梳理` 粘上去）",
          n_once and "\n\n# 要点梳理" in once and "\n\n# 要点梳理" in twice,
          f"once={once[-26:]!r} twice={twice[-26:]!r}")
    glued_doc, gnotes, _ = enforce_render_output(gm, "# 分段速览\n正文结束。# 要点梳理\n- 乙\n")
    check("已粘连的栏名由兜底步骤提回独立行",
          "\n# 要点梳理" in glued_doc and any("粘连" in n for n in gnotes),
          f"{gnotes} {glued_doc[-34:]!r}")

    # 回归（2026-09-22）：`## 栏名` 曾被误判为「粘在正文里的栏名」⇒ 改写成 `#` 裸行 +
    # 重复标题（knowledge_memo 的 `## 核心结论` 稳定复现）。合法子标题必须原样保留。
    keep_doc, keep_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n## 分段速览\n- 乙\n"
    )
    check("合法的 ## 子标题（与栏名同名）保持原样、不改写",
          "## 分段速览" in keep_doc
          and not re.search(r"(?m)^#\s*$", keep_doc)
          and not keep_notes,
          f"{keep_notes} {keep_doc[-46:]!r}")
    keep2, keep2_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n### 分段速览\n- 乙\n"
    )
    check("合法的 ### 子标题同样不改写",
          "### 分段速览" in keep2 and not keep2_notes, "")

    # 标题形态加固（2026-09-22）：裸标题确定性删除；同级别同名标题重复判硬伤。
    bare_doc, bare_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n#\n\n# 分段速览\n- 乙\n"
    )
    check("裸标题行（只有 # 没有文字）被确定性删除并记 note",
          not re.search(r"(?m)^#\s*$", bare_doc)
          and any("裸标题" in n for n in bare_notes),
          f"{bare_notes} {bare_doc[-40:]!r}")

def test_progress_table_rows() -> None:
    """项目进度会：两张表要"分项成行"、风险含待办型、状态补齐四态——且不许写示例式软引导。

    回归背景（2026-09，now.xlsx 行8）：进度追踪 7 行装了约 31 个分项（一个模块一行），
    风险预警只收"实体缺陷型"，把"尚未开展 / 资料依据不完善"这类待办型漏到别的栏 → 条目偏少。
    """
    text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    for need in (
        "一个分项一行",
        "原文有几个分项就写几行，宁多不漏",
        "未开始",
        "尚未开展或尚未闭合的事项",
        "资料、依据、签字等程序性不完善",
    ):
        check(f"项目进度会：含「{need}」", need in text, "")
    check("项目进度会：不夹带示例式软引导（如「应拆成 … 五行」）",
          "应拆成" not in text and "五行" not in text, "")
    from core.templates.body_rules import BODY_FORMAT_RULES

    check("共用形态规则的状态集同步四态",
          "⏸未开始" in BODY_FORMAT_RULES, "")

def test_knowledge_memo_groups() -> None:
    """知识笔记 [核心结论]：固定三子组 + 缺省写法（治"待澄清"空条与说明句）。

    回归背景（2026-09，now.xlsx 行15）：原文没有"待澄清"信号时模型写了
    「- 原文未提及待澄清问题。」——既是空条，又踩了"禁止缺失说明句"；
    同时"适用条件/前提/边界"这类普遍存在的内容此前被埋进"易混淆点"。
    """
    text = (_active_dir() / "knowledge_memo.md").read_text(encoding="utf-8")
    for need in ("## 关键判断与结论", "## 易混点与适用边界", "## 待澄清问题",
                 "整组没内容就不出现该组", "不要写「原文未提及…」这类说明句"):
        check(f"知识笔记：含「{need}」", need in text, "")
    check("知识笔记：仍保留输出契约的栏名 [核心结论]",
          "# [核心结论]" in text, "")
    # 2026-09-19 now.xlsx 行13 实测：全篇 900 汉字（低于下限 1080），概念栏里出现
    # 「笔记中内容较多，未详细展开」这类模型自我省略。
    check("知识笔记：概述栏给尺寸 250–350（含下限口径）",
          "约 250–350 字" in text and "低于 250 字说明三项没交代清" in text, "")
    check("知识笔记：每个概念 2–4 条（定义/步骤/评点）+ 禁止自我省略说明",
          "每个概念 2–4 条" in text and "不得写「未详细展开」" in text
          and "篇幅所限" in text, "")

def test_group_headings_need_body() -> None:
    """`## 组 + - 条` 型栏目：标题下必须有正文；空标题是门禁硬伤（2026-09-20）。

    回归背景：讲座那条 199.6s 的请求在渲染阶段「只重写 [核心观点与论证]」→ 单栏重写后仍不过
    → 整篇回退重填（46s + 63s + 49s）。最可能的硬伤是「只有标题没有正文（空栏）」——
    """
    clause = "**标题下必须至少一条正文"
    cols = (
        ("special_lecture.md", "核心观点与论证"),
        ("class_transcript.md", "核心知识点"),
        ("group_seminar.md", "发言要点"),
        ("interview_transcript.md", "访谈详细记录"),
        ("general_minutes.md", "要点梳理"),
        ("media_briefing.md", "核心信息"),
        ("media_briefing.md", "官方表态"),
        ("exchange_forum.md", "核心信息与数据"),
        ("debate_forum.md", "核心争议与攻防"),
        ("government_bulletin.md", "重点工作"),
        ("knowledge_memo.md", "核心概念"),
        ("research_dialogue.md", "核心反馈"),
        ("hiring_report.md", "面试问答纪要"),
        ("psychological_session.md", "咨询详情"),
        # 注：product_launch.md [核心卖点与技术参数] 已升级为纯三列表格承载，不再设立组标题
        ("team_meeting.md", "工作进展"),
        ("retrospective_session.md", "结果与关键成果"),
    )
    missing: list[str] = []
    for fn, col in cols:
        text = (_active_dir() / fn).read_text(encoding="utf-8")
        spec = ""
        cur = None
        for seg in parse_placeholder_template(text):
            if seg["kind"] == "title":
                cur = seg["raw"]
            elif seg["kind"] == "field" and cur == col:
                spec = str(seg["hint"])
                break
        if clause not in spec:
            missing.append(f"{fn}#{col}")
    check("组标题必须带正文（标题下至少一条 `- ` 条目或一段）", not missing, f"缺={missing}")
    lec = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    check("讲座：子论点作为条目＋缩进子条，不单独立标题",
          "**子论点作为该论点下的一条" in lec and "不单独立标题**" in lec, "")

def test_home_school_feedback_groups() -> None:
    """家校沟通 [家校探讨]：双分支呈现（对仗子条 / 融合陈述）+ 原话点睛 + 与 [沟通内容] 不重复。"""
    text = (_active_dir() / "home_school_liaison.md").read_text(encoding="utf-8")
    check("家校沟通：[家校探讨] 包含探讨议题项规范",
          "- **探讨议题**：" in text, "")
    check("家校沟通：[家校探讨] 包含校方引导与家长心声双分支子条规范",
          "**校方引导**" in text and "**家长心声**" in text, "")
    check("家校沟通：[家校探讨] 包含典型原话引号点睛规范",
          "在句末以双引号真实引用点睛" in text, "")
    check("家校沟通：[家校探讨] 无实质探讨写「未提及」 + 与 [沟通内容] 不重复",
          "全场无实质教育探讨写「未提及」" in text
          and "本栏与 [沟通内容] 不重复" in text, "")
    # 只在本栏范围内查示例（避免误伤其它栏的正当措辞）
    spec = next(l for l in text.splitlines() if l.startswith("[") and ("家校探讨" in l or "探讨议题" in l))
    check("家校沟通：[家校探讨] 不再出现示例式软引导（项别名与示范清单已清除）",
          "如费用" not in spec and "如手机" not in spec and "例如" not in spec
          and "（照原文）" not in spec, spec[:60])

def test_home_school_content_groups() -> None:
    """家校沟通 [沟通内容]：自适应组织（涵盖班情/规章/通报，严禁分号并入单条）。"""
    p = Path("resources/templates") / "home_school_liaison.md"
    text = p.read_text(encoding="utf-8")
    check("template 家校沟通：[沟通内容] 自适应组织且严禁机械套用预设分组",
          "根据实际沟通内容自适应组织" in text and "严禁机械套用预设分组" in text, "dir=template")
    check("template 家校沟通：[沟通内容] 包含观察维度/通报事项条目规范",
          "- **观察维度/通报事项**：客观事实陈述与校内举措" in text, "dir=template")
    check("template 家校沟通：[沟通内容] 包含严禁分号并入同一条指令",
          "严令禁止将多个学生表现用分号并入同一条" in text, "dir=template")
    plan = plan_placeholder_fill(text)
    check("template 家校沟通：标量字段数保持 4 栏", len(plan["scalars"]) == 4, f"scalars={len(plan['scalars'])}")

def test_clinical_history_column() -> None:
    """就医咨询：4 栏 + 5 列药品表（2026-09-20 按 v2 参考收敛），病史并入 [就诊概况]。

    回归背景（2026-09，now.xlsx 行24）：原文 5 次提到"过敏"，产出一次都没写（基线写了）；
    职业（研究所）等个人史同样丢失——4 栏后这些硬要求挂在 [就诊概况] 上。
    """
    text = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    for need in (
        "过敏史、禁忌类信息原文出现就必须逐项写入，不得省略",
        "原文提到就逐项落条",
        "职业照原文",
        "只有医生或原文明确认定为异常、偏高、偏低或需关注的指标才加粗",
        "不得依据医学常识、参考范围或模型判断自行认定异常",
    ):
        check(f"就医咨询：含「{need}」", need in text, "")
    check("就医咨询：旧口径（病史留给「下面各栏」）已清除",
          "病史与用药细节留给下面各栏" not in text, "")
    # 2026-09-20 用户口径：病史背景从 [就诊概况] 拆出，单开一栏按点总结（5 栏）。
    check("就医咨询：5 栏（病史背景单开 [病史与背景]；[病情说明与沟通] 仍不退场）",
          ("[病史与背景]" in text) and "[病情说明与沟通]" not in text
          and (text.count("\n# [") == 5 or text.count("\n## [") == 5), "")
    check("就医咨询：[病史与背景] 按点总结（一条一个事实 + 原文明说才写缺省）",
          "**一条一个事实**（`- **项别**：内容`）" in text
          and "原文说到哪几项就写哪几项，不要为凑清单把没有的项写成「未提及」" in text
          and "过敏史、禁忌类信息原文出现就必须逐项写入" in text
          and "个人史与生活史原文提到就逐项落条" in text, "")
    # 药品明细表：5 列（药品名称/剂量/频次/用法/注意事项）；药名不漏记；整表无药只写一行缺省
    # —— 与程序侧「整表缺省保留首行」「占位行按表头列数生成」配套。
    check("就医咨询：有药名就一行一药、缺格写 `—`",
          "原文出现过的药名不得漏记" in text and "有药名而某格缺失的写 `—`" in text, "")
    check("就医咨询：药表五列 = 药品名称 / 剂量 / 频次 / 用法 / 注意事项",
          "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |" in text
          and "| … | … | … | … | … |" in text
          and "（药名、剂量、频次、用法）" in text
          and "用法用量 | 注意事项" not in text, "")
    check("就医咨询：一条药品信息都没有时整表只写一行缺省（不留空表）",
          "原文一条药品信息都没有时整表只写一行「未提及」并保留该行，不留空表" in text, "")
    check("就医咨询：缺省禁令已收窄到单元格级（旧「原文没写的项不写」已清除）",
          "原文没写的项**不写**" not in text and "不逐格标「未明确」" in text, "")
    # 5 列的格位纪律（2026-09-20 评测：剂量被挂到另一味药名下、非药品项混进表）
    check("就医咨询：格位纪律（每格只写该格内容、同行几格同源）",
          "表格每一格只写该格该写的内容" in text
          and "同一行的几格必须来自同一味药的同一处表述" in text, "")
    check("就医咨询：药名与用法同源 + 非药品项不进表",
          "用法用量必须与药名同源" in text
          and "原文提到的药品、中成药与补充剂可进表" in text
          and "仅作为对比或举例提到、并非该患者用药的不进表" in text, "")
    # 尺寸：带表格的栏（[治疗方案与医嘱]）解析不出节级预算（parser 行为），写进文本即可。
    from core.templates.template_eval import parse_section_char_budgets

    got = [(b["title"], b["lo"], b["hi"]) for b in parse_section_char_budgets(text)]
    check("就医咨询：四栏尺寸口径（概况 250–400 / 病史 250–450 / 诊断 250–500 / 复诊 100–250）",
          ("就诊概况", 250, 400) in got and ("病史与背景", 250, 450) in got
          and ("诊断与检查结果", 250, 500) in got
          and ("复诊与预警信号", 100, 250) in got, f"{got}")
    check("就医咨询：概况栏要素密度（主诉照原文写全 + 归位句 + 未确诊写法）",
          "核心主诉照原文写全" in text
          and "**病史与个人史明细归 [病史与背景]**" in text
          and "未确诊照原文写「考虑…，需…进一步明确」，不把推测写成确诊" in text, "")
    check("就医咨询：症状叙述不算过程铺陈、不得压缩（[病史与背景]）",
          "症状与病史的描述本身就是核心事实" in text
          and "不得当成「过程铺陈」压缩成一句" in text, "")
    check("就医咨询：各栏不再硬要原文没有的项（按实际出现立条 / 有哪几类写哪几类）",
          "按原文实际给出的类别立条" in text
          and "有哪几类写哪几类，没有的类别不立条" in text, "")
    check("就医咨询：复诊栏条件化（原文给了安排才写）+ 预警逐项 + 观察项落点",
          "原文给出复诊/随访安排才写复诊时间" in text
          and "原文提到的预警症状必须逐项写入" in text
          and "需要观察监测的指标" in text, "")
    check("就医咨询：[复诊与预警信号] 扁平化分点总结（无需人工分组与紧急标签，直接条目化落地）",
          "分点写清复诊随访与预警处置" in text
          and "交代需就医的异常表现" in text
          and "绝不臆造或删减" in text
          and "未明确" in text, "")

def test_overview_specs_have_scope() -> None:
    """概况栏要有“要素 + 尺寸 + 边界”：团队例会/辩论会两处已补，防止回退成裸概括。

    回归背景（2026-09，now.xlsx 行23/26）：[例会概况] 说明只有“一段话概括主要内容”，
    结果 308 字吞掉了 [工作进展] 的明细；[辩论内容概述] 把论据写进了概述，
    而 [结辩与评委点评] 只写了 145 字（真的薄）。
    """
    team = (_active_dir() / "team_meeting.md").read_text(encoding="utf-8")
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    for text, name, size in (
        (team, "团队例会", "约 250–350 字"),
        (debate, "辩论会", "约 250–400 字"),
    ):
        check(f"{name}：概况栏声明尺寸（{size}）", size in text, "")
    check("团队例会：概况栏写明六要素（谁/为什么开/议题及程度/态势/结论）",
          all(k in team for k in (
              "参会成员或部门", "为什么开这次会", "涵盖的主线议题", "整体态势", "结论",
          )), "")
    check("团队例会：概况栏用归位式边界（只到议题级主线 + 态势，不写任务级明细）",
          "本栏只到「议题级主线 + 态势」" in team and "不写任务级明细" in team
          and "[工作进展]" in team and "[落实安排]" in team, "")
    check("团队例会：概况栏声明下限口径（低于 250 字＝没交代清）",
          "低于 250 字说明没交代清" in team, "")
    from core.templates.template_eval import parse_section_char_budgets

    ov = [b for b in parse_section_char_budgets(team) if b["title"] == "例会概况"]
    check("团队例会：概况栏仍解析为节级 250–350（尺寸口径未漂）",
          bool(ov) and ov[0]["scope"] == "section" and ov[0]["lo"] == 250 and ov[0]["hi"] == 350,
          f"{ov}")
    check("辩论会：概况栏写明边界（不展开什么、归哪栏）", "不展开" in debate, "")
    check("团队例会：[工作进展] 声明容量引导（并列任务各占一条）",
          "同一模块/成员下并列的多个任务各占一条" in team, "")
    check("团队例会：设立 [落实安排]（行动项 + 跨组协作看板）",
          "# [落实安排]" in team and "交代具体做什么、交付要求/产出形态与时限责任" in team
          and "展开具体执行动作与交付细节" in team, "")
    check("团队例会：设立 [未决风险]（未决/分歧/阻塞延期 + 不替团队预判）",
          "# [未决风险]" in team and "尚未议定或需要再确认的事项" in team
          and "不替团队预判" in team, "")
    check("团队例会：[工作进展] 声明栏间分工（进展 vs 落实安排不重复）",
          "本栏只写\"已经做了什么、到什么程度\"" in team and "统一归 [落实安排]，两栏不重复" in team, "")
    check("团队例会：requirement 覆盖新栏（决议与待办 / 待确认事项）",
          "决议与待办事项" in team and "待确认事项" in team, "")
    # 尺寸口径：仅首栏例会概况设节级预算（250–350 字），明细与安排等栏目由事实密度驱动
    from core.templates.template_eval import parse_section_char_budgets as _pscb

    tm_budgets = [(b["title"], b["hi"]) for b in _pscb(team)]
    check("团队例会：仅首栏概况设节级预算（350），后续栏目不设机械限字",
          tm_budgets == [("例会概况", 350)], f"{tm_budgets}")
    check("辩论会：结辩栏分三条写",
          "**正方结辩**" in debate and "**反方结辩**" in debate and "**评委点评**" in debate, "")
    check("辩论会：结辩栏给每条尺寸", "每条 60–150 字" in debate, "")

def test_debate_rounds_and_rows() -> None:
    """辩论会：栏目跟原文环节对齐（质询/总结有承载位）+ 论点各自成行 + 归因与引用口径。

    回归背景（2026-09 now.xlsx 行26）：一场 53 分钟、10284 汉字的辩论只出 1249 汉字
    （低于 tier 下限 26%），门禁却全绿——原因是模板按"立论/自由辩论/结辩"设栏，而原文
    里"自由辩论""结辩"**各出现 0 次**（原文说的是"第二个环节（质询）""第三个环节""小节"），
    质询与总结的内容无家可归；表格要求"一行一方" → 论点与论据被压成两行标签串。
    """
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    for col in (
        "# [辩论概况]",
        "# [各方立论体系]",
        "# [核心争议与攻防]",
        "# [结辩与裁决]",
    ):
        check(f"辩论会：4 栏骨架存在 {col}", col in debate, "")
    check("辩论会：旧 5 栏碎片化栏目已退场",
          "# [核心论点]" not in debate and "# [争议焦点]" not in debate
          and "# [环节交锋]" not in debate and "# [结辩与评委点评]" not in debate, "")
    check("辩论会：交锋与焦点合并为 [核心争议与攻防] 并按议题成对对答",
          "按核心分歧点设立小节" in debate and "一条一方，一方一句话" in debate
          and "针锋相对" in debate, "")
    check("辩论会：归因兜底（判不准写「一方」）",
          "判不准就写「一方」" in debate, "")
    check("辩论会：攻防原声引用规范（只引原话、不盲猜署名）",
          "只引原话、不盲猜署名" in debate, "")
    check("辩论会：各方立论体系去碎表格、结构化条目呈现",
          "呈现各持论阵营的初始立论基础" in debate and "核心论点" in debate, "")
    check("辩论会：结辩与胜负裁决规范（原文明示才标注）",
          "原文明示获胜方时才标注" in debate and "未明示不写" in debate, "")

def test_exchange_forum_structure() -> None:
    """沟通交流会：宣贯型素材有承载位 + 共识/待协调互斥 + 首栏边界（治信息墙与重复）。

    回归背景（2026-09 now.xlsx 行3/行31）：两条数据都是单向宣贯型（源里"诉求/协调/承诺"
    全是 0 次），结构化介绍内容全倒进 [信息同步] → 3174 汉字、5 个长段（最长 902 字）；
    "夏令营时间待定"被写进 [达成共识] 又在 [待协调事项] 写一遍；首栏与信息同步数字重复。
    """
    text = (_active_dir() / "exchange_forum.md").read_text(encoding="utf-8")
    for col in (
        "# [沟通背景与目的]",
        "# [核心信息与数据]",
        "# [各方立场与诉求]",
        "# [达成共识]",
        "# [待协调事项与后续]",
    ):
        check(f"沟通交流会：栏位存在 {col}", col in text, "")
    check("沟通交流会：旧栏名已退场（[信息同步]/[待协调事项]）",
          "# [信息同步]" not in text and "# [待协调事项]\n" not in text, "")
    check("沟通交流会：新增栏要求分条与数字落地（不压成长段）",
          "每条 30–120 字" in text and "不要压成长段" in text and "数字、年份、比例" in text, "")
    check("沟通交流会：新增栏声明「条数由原文决定」",
          "条数由原文决定" in text, "")
    check("沟通交流会：立场栏收窄（事实清单归上一栏、不复述）",
          "事实与数字清单归 [核心信息与数据]" in text and "本栏不复述" in text, "")
    check("沟通交流会：共识栏与待协调互斥（待定不进共识）",
          "待定、计划、尚未确定的事项一律归 [待协调事项与后续]" in text, "")
    check("沟通交流会：待协调栏清单化组织与协同推进（支持按业务议题展开）",
          "- **事项名称**" in text and "牵头方/对接人" in text, "")
    check("沟通交流会：待协调栏缺项不写（不逐项标「待定」）",
          "不要逐项标「待定」" in text, "")
    check("沟通交流会：首栏加边界（不展开明细）+ 尺寸 250–400",
          "不展开发言明细与数字清单" in text and "约 250–400 字" in text, "")
    check("沟通交流会：首栏明确数据下沉边界（成串数据下沉）",
          "本栏不展开发言明细与数字清单" in text
          and "成串统计数据与客观事实下沉至 [核心信息与数据]" in text, "")
    check("沟通交流会：首栏严格限定单段与尺寸（约 250–400 字）",
          "一段写完，约 250–400 字" in text, "")
    check("沟通交流会：旧悬空引用已清除（「各方确认的信息」不存在）",
          "各方确认的信息" not in text, "")
    check("沟通交流会：每栏都有缺省词（空栏不成硬伤）",
          text.count("未提及") >= 5, f"未提及×{text.count('未提及')}")
    check("沟通交流会：引用有上限（3–5 句）",
          "整栏最多引 3–5 句" in text, "")

def test_interview_and_lecture_overview() -> None:
    """采访记录 [访谈概述] / 专题讲座 [讲座概况]：补"结论型"要素 + 锚点 + 尺寸 + 防越栏。

    回归背景（2026-09 now.xlsx）：两栏覆盖度好但只有 78–135 汉字（动态下限 238–370 的
    40% 左右），且要素全是"是什么"型（主题/身份/板块/形式），没有落点——行36 的概述把
    话题列全了却一句结论都没有；行48 的 78 字反而越栏写了 [核心观点与论证] 的内容。
    另：采访记录 [访谈详细记录] 缺容量引导，行36 整篇只有 tier 下限的 67% 即此栏偏小。
    """
    interview = (_active_dir() / "interview_transcript.md").read_text(encoding="utf-8")
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")

    for name, text, anchor in (
        ("采访记录", interview, "受访者最核心的观点与结论 1–3 条"),
        ("专题讲座", lecture, "讲座的核心主张或最有分量的 2–3 个判断"),
    ):
        check(f"{name}：概况栏补了结论型要素", anchor in text, "")
        check(f"{name}：概况栏要求 1–3 个数字/专名锚点",
              "作锚点" in text, "")
        check(f"{name}：概况栏尺寸写进模板（约 250–400 字）", "约 250–400 字" in text, "")
    check("采访记录：概况栏落点要素以受访者原话为限（不做外部比较）",
          "这场访谈的看点" in interview and "以受访者原话为限" in interview, "")
    check("采访记录：结论要素写明粒度（一句话点题 + 可带数字/事例依据）",
          "每条一句话点题，可带原文的关键数字或事例作依据" in interview, "")
    check("采访记录：概况栏边界（不展开论据细节，归 [访谈详细记录]）",
          "不展开受访者的论据与细节" in interview, "")
    check("专题讲座：概况栏边界（论证与论据清单归 [核心观点与论证]）",
          "论证过程与论据清单归" in lecture and "核心观点与论证" in lecture and "不逐条复述论点" in lecture, "")
    check("专题讲座：概况栏补落点要素（问题意识/由头 + 对听众的意义）",
          "为什么讲这个、面向谁" in lecture and "对听众的意义或适用对象" in lecture, "")
    check("专题讲座：锚点要求解开（原文有则选，案例可作锚点但不展开）",
          "原文有关键数字、案例或专名时选 1–3 个作锚点" in lecture
          and "没有则不强求" in lecture and "不展开细节" in lecture, "")
    # 承载栏「细节落地」：源里的数字/年份/案例/过程此前被压成一条条 60–90 字的主张
    check("专题讲座：[核心观点与论证] 要求多条论据各占一条（不压成一条）",
          "就各占一条，不要压成一条" in lecture, "")
    check("专题讲座：[核心观点与论证] 要求数字/年份/人名/事例落地",
          "数字、年份、人名、地名、事例与过程都要落进对应条目" in lecture, "")
    check("专题讲座：[核心观点与论证] 给单条尺寸（每条 30–120 字）",
          "每条 30–120 字" in lecture, "")
    check("采访记录：[访谈详细记录] 补了容量引导（多条各占一条、不要压成一条）",
          "各自成条，不要压成一条" in interview and "每条 30–120 字" in interview, "")
    check("采访记录：旧表述「只写这是一场什么讲座」已清除（避免只写节目单）",
          "只写\"这是一场什么讲座\"" not in lecture, "")

def test_conversation_and_seminar_enrichment() -> None:
    """对话记录 / 小组讨论：首栏补结论要素+尺寸、新增关键原话、共识栏双侧、细节落地。

    回归背景（2026-09 now.xlsx）：两栏覆盖度好但首栏只有 103–168 汉字（动态下限 238–370）；
    对话记录 2388 字原文只出 722 汉字、[交流内容] 仅 3 条且把原话塞在里面被压成转述；
    小组讨论 [共识形成] 124–197 字、[发言要点] 里源文的"三次/四个/十分钟"未落地。
    末栏（待探讨/延伸话题）的空是源文所致（那些场"下次/待/分工/负责"全为 0 次），
    所以只把口径写清楚（搁置、没聊透也算），不加下限、不逼内容。
    """
    conv = (_active_dir() / "conversation_transcript.md").read_text(encoding="utf-8")
    semi = (_active_dir() / "group_seminar.md").read_text(encoding="utf-8")

    for name, text, lead, anchor, bound in (
        ("对话记录", conv, "倾向与差异对照", "值得记的数字或具体事例", "不逐条复述各方发言"),
        ("小组讨论", semi, "讨论的整体倾向或是否有结论", "作锚点", "不展开各方发言明细"),
    ):
        check(f"{name}：首栏补结论型要素", lead in text, "")
        check(f"{name}：首栏声明尺寸（约 250–400 字）", "约 250–400 字" in text, "")
        check(f"{name}：首栏要素含锚点要求", anchor in text, "")
        check(f"{name}：首栏带防越栏边界", bound in text, "")

    check("对话记录：[交流内容] 要求细节落地（不只写主张）",
          "都要落进对应条目，不要只写主张" in conv, "")
    check("对话记录：[交流内容] 每位发言人各占一条缩进子条（合并只限同一次发言）",
          "每位发言人的说法各占一条缩进子条" in conv and "同一次发言的碎片合并成一条" in conv
          and "不要把多位发言人塞进同一条" in conv, "")
    check("对话记录：[共识与分歧] 分组分点严禁写成连续段落（约 150–300 字）",
          "约 150–300 字" in conv and "严禁写成连续段落" in conv and "各方立场与理由" in conv, "")
    check("对话记录：[共识与分歧] 包含判断层（分歧性质/本场的倾向与依据）",
          "由事实得出的判断" in conv and "分歧的性质" in conv and "本场的倾向与依据" in conv, "")
    check("对话记录：[共识与分歧] 禁止复述各人事实（明细归 [交流内容]）",
          "不要复述各人分别带什么、认为什么（事实明细归 [交流内容]）" in conv, "")
    check("对话记录：[延伸话题与后续] 扁平自适应清单（约 100–250 字，严禁大段叙述）",
          "约 100–250 字" in conv and "严禁写成大段叙述" in conv and "- **焦点/事项**" in conv, "")
    check("对话记录：[延伸话题与后续] 缺省声明全场皆无写「未提及」",
          "全场无任何延伸与后续写「未提及」" in conv, "")
    check("对话记录：[对话概况] 场合关系只取原文明示，不推断",
          "只写原文明示的角色或关系" in conv and "原文没有身份线索就不补关系、不作推断" in conv
          and "为什么聊起这个话题、话题走向" in conv, "")
    check("对话记录：[对话概况] 差异对照 + 数字/事例 + 不逐条复述",
          "倾向与差异对照" in conv and "值得记的数字或具体事例" in conv
          and "不逐条复述各方发言（明细归 [交流内容]）" in conv, "")
    check("小组讨论：[讨论议题与背景] ④ 降级为点题、明细归 [共识与分歧]（治六成以上重复）",
          ("一致与分歧的明细归 [共识与分歧]，本栏不复述" in semi or "一致与分歧的明细归 [共识形成]，本栏不复述" in semi), "")
    check("小组讨论：[讨论议题与背景] 新增「为什么现在讨论这个」与「讨论怎么推进的」",
          "为什么现在讨论这个" in semi and "讨论怎么推进的" in semi, "")
    check("小组讨论：[共识形成] 扩为双侧（一致意见 + 倾向性认识/主要分歧）",
          "一致意见或产出" in semi and "谁与谁不一致、分歧在哪" in semi
          and "没有统一意见时写本场达成的倾向性认识与主要分歧点" in semi, "")
    check("小组讨论：[共识形成] 补尺寸（约 150–300 字）", "约 150–300 字" in semi, "")
    check("小组讨论：[发言要点] 要求数字/案例落地",
          "具体数字、次数、案例、时间要落进对应条目" in semi, "")
    check("小组讨论：[发言要点] 交锋写实（谁反对、理由与依据）",
          "交锋要写实" in semi and "谁主张什么、谁反对、反对的理由或依据是什么" in semi, "")
    check("小组讨论：交锋按条展开（多条各占一条），合并只限同一次发言",
          "同一议题下的多条交锋各占一条" in semi and "只有同一次发言的碎片才合并" in semi
          and "；同一议题的碎片合并成一条" not in semi, "")
    check("小组讨论：末栏口径写清（搁置/没聊透也算）但不编造分工",
          "没聊透或明确说下次继续的话题都算" in semi and "不要编造分工" in semi, "")
    for name, text in (("对话记录", conv), ("小组讨论", semi)):
        check(f"{name}：旧体例（裸概括首栏）已替换",
              "场景及整体脉络（谈了哪几个话题、以什么为主）" not in text
              and "核心探讨问题（列出谈到的议题范围）" not in text, "")

def test_project_progress_overview() -> None:
    """项目进度会 [项目概况]：删掉不可校验的句数口径，换成可解析的字数区间 + 可执行边界。

    回归背景（2026-09 now.xlsx）：该栏同时挂着"只写 3–6 句"（无程序检查、且句数不是篇幅指标）
    与"每段不超过 400 字"（可解析、超 480 会拆行）——模型只认后者，写成了 6 段 1317 汉字
    （27 句），且与 [进度追踪] 表格的 4-gram 重合 26%（复述明细）。
    """
    text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    specs = [l.strip() for l in text.splitlines() if l.strip().startswith("[") and l.strip().endswith("]")]
    overview = next((s for s in specs if "一段话概览" in s), "")
    check("项目进度会：概况栏改为可解析的字数区间（一段写完，约 250–350 字）",
          "一段写完，约 250–350 字" in overview, f"{overview[:60]}")
    check("项目进度会：旧的句数口径已删除（3–6 句不再出现）",
          "3–6 句" not in text and "句概览" not in text, "")
    check("项目进度会：边界写成可执行的下沉明细栏且无方括号字面",
          "下沉至「进度追踪」、「风险预警」与「后续计划」等明细栏" in overview
          and "本栏不复述" in overview
          and "[" not in overview.replace("[一段话概览", "").replace("]", ""), "")
    # [后续计划] 原来是全模板唯一没有格式要求的栏（其余两栏走表、概况走一段话）→ 实测 4 份
    # 产物里 3 份写成 221–242 汉字的单段、零分点，而源里明明有 6–8 件后续事项。
    plan = next((s for s in specs if "按事项分点写" in s), "")
    check("项目进度会：[后续计划] 要求按事项分点（一条一件事、一条一行）",
          "按事项分点写" in plan and "一条一件事、一条一行" in plan
          and "`- **事项**：做什么 + 责任方 + 时间节点`" in plan, f"{plan[:80]}")
    check("项目进度会：[后续计划] 规范分组，松绑条级机械限字",
          "每组 2–5 条" in plan and "不写与栏名同名的标题" in plan, "")
    check("项目进度会：[后续计划] 保留交付物/依赖提示与套话禁令",
          "核心交付物用 **具体内容** 强调" in plan
          and "依赖前提用 *具体内容* 提示" in plan
          and "无对象的套话" in plan, "")
    check("项目进度会：[后续计划] 旧口径（要素清单式叙述）已清除",
          "从概况与原文提取下一步" not in plan and "验收标准、关键时间节点" not in text, "")
    from core.templates.template_eval import parse_section_char_budgets

    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "项目概况"]
    check("项目进度会：概况栏预算为节级 250–350（首栏只写一段）",
          bool(caps) and caps[0]["hi"] == 350 and caps[0]["scope"] == "section", f"{caps}")

def test_strip_default_only_content() -> None:
    """只有缺省词的内容不展示：表格整行 / 正文整条 / 独立缺省句；整栏缺省则保留一行。

    回归背景（2026-09-18 用户实测）：就医咨询的药表出现整行「未明确」（模板声明的缺省词是
    「未明确」而 `_row_nonempty` 的空集里没有它）→ 被当数据行原样展示；同期还有 3 条
    `- **过敏史**：未提及。` 与 4 处"整栏只有未提及"。用户口径：这类内容不展示，
    但"整栏都没有"要保留一行缺省词（"没有"本身是信息）。
    """
    from core.execution.gate import (
        _item_default_only,
        _row_nonempty,
        apply_table_row_limits,
        enforce_render_output,
        gate_render_output,
        strip_default_only_content,
    )

    check("全缺省表行判为空（含模板缺省词「未明确」）",
          not _row_nonempty("| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |"), "")
    check("全未提及表行判为空", not _row_nonempty("| 未提及 | — | — | — | — |"), "")
    check("有内容的表行不算空", _row_nonempty("| 奥美拉唑 | 未明确 | 口服 | 未明确 | 效果不佳 |"), "")
    check("整条只有缺省词（`- **X**：未提及。`）被识别",
          _item_default_only("- **过敏史**：未提及。") and _item_default_only("- **个人史**：未提及"), "")
    check("有内容的条目不算缺省", not _item_default_only("- **现病史**：2023年9月确诊。"), "")

    doc = (
        "# 就医咨询\n\n# 就诊概况\n- **现病史**：2023年9月确诊。\n"
        "- **过敏史**：未提及。\n- **家族史**：未提及。\n\n"
        "# 治疗方案与医嘱\n- **检查安排**：建议做第二次基因检测。\n"
        "- **用药**：系统治疗包括化疗、靶向、免疫。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n"
        "| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |\n\n"
        "# 复诊与预警信号\n未提及。\n"
    )
    out, notes = strip_default_only_content(doc)
    check("整条缺省被删、有内容的条目保留",
          "- **过敏史**" not in out and "- **现病史**" in out and "- **检查安排**" in out, "")
    check("整表全缺省 → 保留首行缺省数据行（不再把表删空）",
          "| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |" in out and "| 药品名称 |" in out, "")
    check("整节只有缺省词 → 保留标题 + 一行缺省词",
          "# 复诊与预警信号\n未提及" in out, "")
    check("删除有记录（notes 记数）", bool(notes) and "已省略" in notes[0], f"{notes}")

    raw = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    gate = gate_render_output(raw, out)
    # 2026-09-19 起反转：整表缺省是**合法形态**（原文本就没有药品明细），保留首行缺省数据行后
    # 不再报「表格无有效数据行」。旧口径让这条硬伤无法修复（源里没有数据可填），
    # 实测 就医咨询 单次渲染 10 次 LLM 调用、整单 115.8s 后仍降级。
    check("整表缺省不再产生「表格无有效数据行」硬伤",
          "表格无有效数据行" not in gate["issues"] and not gate["hard_issues"],
          f"hard={gate['hard_issues']} issues={gate['issues']}")

    blank = (
        "# 就医咨询\n\n# 治疗方案与医嘱\n- **全身系统治疗**：核心是全身系统治疗。\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n"
    )
    fixed_t, notes_t, issues_t = enforce_render_output(raw, blank)
    check("空表全流程：写入缺省占位行且零硬伤（原文本就没有药品明细时的出口）",
          not issues_t and "| 未提及 | — | — | — | — |" in fixed_t, f"{issues_t} {notes_t}")
    glued, n_glued = apply_table_row_limits(blank.rstrip("\n"), raw)
    check("表格在文末且无末尾换行时，占位行也独立成行（不粘连分隔行）",
          "| 未提及 | — | — | — | — |" in glued.splitlines(), f"{n_glued} {glued.splitlines()[-1]!r}")

    for stem, bad in (
        ("clinical_advisory", "一律写「未明确」"),
        ("decision_review", "缺项直接写「未明确」"),
        ("project_progress", "缺项直接写「无」"),
        ("contract_vetting", "缺则写「无」"),
    ):
        txt = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        check(f"{stem}：不再要求逐项标缺省词", bad not in txt, "")
    pl = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    check("产品发布：缺项不写、整栏才合并成一句",
          "整栏都没有内容时才把缺项**合并成一句**" in pl, "")

def test_media_overview_scope() -> None:
    """新闻发布 [发布会概况]：要素去掉与 [核心信息] 同名的词 + 可解析段上限 + 归位边界。

    回归背景（2026-09-18 实测周会）：概况写了 1264 汉字、212 个数字、单段，
    与 [核心信息] 栏 4-gram 重合 82%——因为它 ① 没有可解析尺寸（程序不拆段不报超限）
    ② 要素里写着"核心信息"，与下面那栏同名（引导复述）。
    """
    from core.execution.gate import split_overlong_paragraphs
    from core.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    spec = next(l.strip() for l in text.splitlines() if l.strip().startswith(("[一段写完", "[一段话概括发布会")))
    check("发布会概况：一段写完（约 300–400 字）",
          "一段写完，约 300–400 字" in spec and "最多 3 段" not in spec, spec[:80])
    check("发布会概况：回答四个问题交代全景",
          "回答四个问题交代全景" in spec or "交代全景" in spec, spec[:80])
    check("发布会概况：写明归位边界",
          "本栏不铺开细节" in spec or "本栏不复述" in spec, "")
    check("发布会概况：① 谁、何时、何地、发布了什么",
          "谁、何时、何地、发布了什么" in spec, "")
    check("发布会概况：② 围绕哪几个板块",
          "围绕哪几个板块" in spec, "")
    check("发布会概况：③ 最关键的 1–2 个宏观指标或整体走势",
          "最关键的 1–2 个宏观指标或整体走势" in spec or "关键宏观指标与整体走势" in spec, "")
    check("发布会概况：④ 问答焦点与后续安排",
          "问答焦点与后续安排" in spec or "问答环节涉及的议题与会议后续安排" in spec, "")
    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "发布会概况"]
    check("发布会概况：解析出节级预算 300–400（首栏只写一段）",
          bool(caps) and caps[0]["scope"] == "section" and caps[0]["lo"] == 300
          and caps[0]["hi"] == 400, f"{caps}")

    han = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s))
    para = "宏观方面，主讲人解读法案要点，测算关税收入可覆盖新增支出，赤字率维持合理区间。" * 18
    doc = "# 新闻发布\n\n# 发布会概况\n" + para + "\n\n# 核心信息\n- **要点**：略。\n"
    fixed, notes = split_overlong_paragraphs(doc, (_active_dir() / "media_briefing.md").read_text(encoding="utf-8"))
    seg = fixed.split("# 发布会概况", 1)[1].split("# 核心信息", 1)[0]
    parts = [q.strip() for q in seg.split("\n\n") if q.strip()]
    check("发布会概况：超长单段按句界拆开（节级 ≤400/段）",
          len(parts) >= 2 and max(han(q) for q in parts) <= 400,
          f"段长={[han(q) for q in parts]} {notes}")

def test_class_transcript_task_groups() -> None:
    """课堂记录：模块化知识梳理、疑难澄清与易错辨析、课后任务与学习建议。

    结构优化：
    1. 摒弃一问一答对话剧本，升级为「疑难澄清与易错辨析」高密度干货清单；
    2. 核心知识点按模块分组，支持缩进子条展开公式推导，严禁空标题；
    3. 课后任务与学习建议自然陈述，全场无课后安排写「未提及」；
    4. 4 个栏目均带合理字数预算。
    """
    from core.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "class_transcript.md").read_text(encoding="utf-8")

    # 栏目完整性
    for col in ("课程概况", "核心知识点", "问答记录", "课后任务"):
        check(f"课堂记录包含 [{col}] 栏目", f"[{col}]" in text, "")

    # 核心知识点要求
    kn = next(l for l in text.splitlines() if "章节模块分组" in l)
    check("核心知识点：要求标题下至少一条正文且不得只有标题",
          "标题下必须至少一条正文" in kn and "不得只有标题" in kn, "")
    check("核心知识点：较复杂推导下挂缩进子条展开",
          "下挂缩进子条" in kn and "严禁将多步推导强行压缩为孤立结论" in kn, "")

    # 问答记录要求
    qa = next(l for l in text.splitlines() if "提炼课堂互动涉及的核心疑问与确定性答案" in l or "按“问题焦点：直接答案”逐条呈现" in l)
    check("问答记录：按 - **[总结的核心问题]**：[直接陈述对应的事实答案] 逐条列出",
          "- **[" in qa and "直接陈述对应的事实答案" in qa, "")
    check("问答记录：提炼实质与结论，去转述前缀，无问答整栏隐去",
          "严禁出现“学生询问" in qa and "整栏自适应隐去" in qa, "")

    # 课后任务要求
    task = next(l for l in text.splitlines() if "清单化记录课后执行动作" in l)
    check("课后任务：涵盖课后作业与复习重点，严禁补写原文没有的作业",
          "课后作业与实践" in task and "复习重点与备考提示" in task and "严禁补写原文没有的作业" in task, "")
    scalars = plan_placeholder_fill(text)["scalars"]
    check("课后任务保留缺省词语义（全场无课后安排 → 「未提及」）", scalars[3].get("missing") is True, "")
    check("问答记录声明整栏隐去", "无现场互动则整栏自适应隐去" in text, "")

    # 预算检查：4 栏全覆盖
    budgets = [(b["title"], b["hi"], b["scope"]) for b in parse_section_char_budgets(text)]
    check("课堂记录：4 栏均带合理预算",
          budgets == [
              ("课程概况", 400, "section"),
              ("核心知识点", 1000, "section"),
              ("疑难辨析", 500, "section"),
              ("课后任务", 300, "section"),
          ], f"{budgets}")

def test_quote_columns_have_background() -> None:
    """金句/引语类栏：每条引用下带一句背景说明（治"脱离上下文的孤立金句"）。

    用户口径（2026-09-18）：金句下面要加一句"当前金句的出现背景"，一句话即可——
    引语没有背景就读不出分量，也无法核对它是否被断章取义。
    """
    from core.templates.router._placeholder import plan_placeholder_fill

    expectations = {
        "special_lecture": ("金句总结", ("讲到哪个话题/论证到哪一步", "无明确背景则写未提及")),
        "interview_transcript": ("金句总结", ("回应什么问题/谈到什么话题", "无明确线索则写未提及")),
    }
    for stem, (col, needles) in expectations.items():
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        head_idx = next(i for i, l in enumerate(lines) if f"[{col}]" in l)
        spec = lines[head_idx + 1]  # 栏名下的说明行
        for k in needles:
            check(f"{stem} [{col}]：背景说明口径（{k[:14]}…）", k in spec, spec[:80])
        check(f"{stem} [{col}]：一体化出版级引用卡片（首行引号引用 + 次行署名语境）",
              '`> “……”`' in spec and ("> —— **受访者姓名**" in spec or "> —— **主讲人" in spec), spec[:90])
        check(f"{stem} [{col}]：旧写法（无引号 / 背景行只写 `-`）已清除",
              "背景行用 `-`" not in spec and "「- 背景未提及」" not in spec, "")
        check(f"{stem} [{col}]：无 3 句下限（有几句写几句，不硬凑）",
              ("最多 8 句" in spec or "最多 6 句" in spec) and "有几句写几句" in spec and "3–8 句" not in spec, "")
        check(f"{stem} [{col}]：背景限定一句话（不展开复述）",
              "一句话即可" in spec, "")
        quote_fields = [s for s in plan_placeholder_fill(text)["scalars"] if "逐字" in (s.get("hint") or "")]
        check(f"{stem} [{col}]：保留缺省词语义",
              bool(quote_fields) and quote_fields[0].get("missing") is True,
              f"{[s.get('missing') for s in quote_fields]}")
    conv_text = (_active_dir() / "conversation_transcript.md").read_text(encoding="utf-8")
    check("conversation_transcript 已移除独立 [关键原话] 栏",
          "[关键原话]" not in conv_text, "")

def test_lecture_evidence_cap() -> None:
    """讲座 [核心观点与论证]：优先 3–4 条代表性论据，但不删除关键论据。

    回归背景（2026-09-19 实测）：陈廷敬讲座场该栏 2277 字（5 论点 × 29 条论据），
    每个论点下 6–8 条论据角度重复——"都要落进对应条目"只有下量没有取舍。
    """
    from core.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    spec = next(l for l in text.splitlines() if "两级结构" in l and "## 论点" in l)
    check("讲座：两级结构 + 论点标题短语化（20 个汉字内，不写成会解析成预算的「20 字」）",
          "两级结构" in spec and "20 个汉字内" in spec and "20 字内" not in spec, spec[:80])
    check("讲座：论点标题短语化与边界（20 个汉字内，互动统一下沉至 Q&A）",
          "20 个汉字内" in spec and "统一下沉至 [Q&A 环节]" in spec, spec[:80])
    check("讲座：直接数据/典型事例优先、细碎铺垫适度聚合",
          "直接数据或典型事例" in spec and "适度聚合" in spec, "")
    got = [(b["title"], b["hi"], b["scope"]) for b in parse_section_char_budgets(text)]
    check("讲座：仅概况保留节级预算（400），中间论点论据由事实密度驱动",
          ("讲座概况", 400, "section") in got, f"{got}")

def test_court_claims_table_both_sides() -> None:
    """庭审 [原告诉称与被告辩称]：双方都要有成行承载（"各占一行"不再是 1 行上限）。

    回归背景（2026-09-19 now.xlsx 实测）：「原告、被告各占一行」被 parse_row_hint 误读成
    "全表最多 1 行"——装配截断 + 模型侧双通道都指向一行，二审场（上诉人国开行 vs 被上诉人
    东源等）被告行整行消失，而概况栏明明写全了当事人。
    """
    from core.execution.gate import apply_table_row_limits
    from core.templates.template_eval import (
        extract_template_table_constraints,
        parse_row_hint,
    )

    text = (_active_dir() / "court_transcript.md").read_text(encoding="utf-8")
    check("庭审模板：样例行含原告与被告两行",
          ("| 原告(或上诉人) | … |" in text or "| 原告（或上诉人） | … |" in text)
          and ("| 被告(或被上诉人) | … |" in text or "| 被告（或被上诉人） | … |" in text), "")
    cons = extract_template_table_constraints(text)
    check("庭审：诉辩表不再有 1 行上限（row_limit=None）",
          bool(cons) and cons[0]["row_limit"] is None, f"{cons}")
    check("parse_row_hint：「各占一行」是形态不是上限",
          parse_row_hint("原告、被告各占一行（原文有第三人、反诉方的照此增行）") is None, "")
    check("parse_row_hint：数字行数仍有效（最多 3 行）",
          parse_row_hint("最多 3 行") == 3, "")

    # 端到端：两行诉辩数据不再被截成一行
    doc = (
        "# 庭审记录\n\n"
        "# 庭审概况\n本案系金融借款合同纠纷上诉案。\n\n"
        "# 原告诉称与被告辩称\n\n"
        "| 方 | 诉讼请求/答辩意见 | 事实与理由 |\n| --- | --- | --- |\n"
        "| 上诉人（国开行） | 请求改判 | 主张善意取得 |\n"
        "| 被上诉人（东源） | 请求驳回 | 一审判决正确 |\n\n"
        "# 举证与法庭调查\n- **证据**：略。\n\n"
        "# 庭审结果\n未提及。\n"
    )
    fixed, notes = apply_table_row_limits(doc, text)
    check("两行诉辩数据不再被截断", not notes and "被上诉人（东源）" in fixed, f"{notes}")

def test_subjective_judgment_guardrails() -> None:
    """主观判断以原文明示为准：采访"看点"内化、辩论占优/获胜限源、hiring 评级不代打。

    用户指出（2026-09-19）：① 采访"讲了什么别人讲不出的"需要外部比较，越界；
    ② 辩论"转折/占优方/获胜方"在无主持人或评委结论时属主观裁判；
    ③ 面试官没给评级时模型会自行打分、"潜在风险点"会代面试官预判风险。
    """
    d = _active_dir()
    itv = (d / "interview_transcript.md").read_text(encoding="utf-8")
    check("采访：看点以受访者原话为限（不做外部比较）",
          "以受访者原话为限" in itv and "不做外部比较" in itv, "")

    deb = (d / "debate_forum.md").read_text(encoding="utf-8")
    check("辩论：转折/占优只在原文明示时写",
          "转折或占优只在原文明示时写" in deb and "不自判" in deb, "")
    check("辩论：获胜方原文明示才标注，未明示不写",
          "原文明示获胜方时才标注" in deb and "未明示不写" in deb, "")

    hir = (d / "hiring_report.md").read_text(encoding="utf-8")
    # 2026-09-19 曾按用户口径删掉「推荐评级」列（模型自行打分、7/7 全是「未评」）；
    # 2026-09-20 用户要求恢复：表头三列，并配「评级只依据原文 + 与同行依据同源、无依据写 —」。
    check("面试：[能力评估] 表头三列（评估维度 / 推荐评级 / 评估依据）",
          "# [能力评估]" in hir
          and "| 评估维度 | 推荐评级 | 评估依据（具体事例） |" in hir
          and "| … | … | … |" in hir, "")
    check("面试：维度名取原文考察要素/评价口径、不自行发明能力模型",
          "取原文的考察要素或评价口径" in hir and "不自行发明能力模型" in hir
          and "岗位匹配度、问题解决能力、思维逻辑性、应变能力" not in hir, "")
    check("面试：行数随原文 + 依据必须有事例支撑",
          "行数随原文，原文提到几个维度就写几行" in hir
          and "每条都要有事例支撑，不做原文以外的推断" in hir, "")
    # 2026-09-20 实测（now.xlsx 行19）：原口径「评级只依据原文」被读成「原文没写评分 → 全列 `—`」；
    # 改成「判据是本行依据、有依据必须给评级、只有无点评无事实才写 `—`」。
    check("面试：评级纪律（判据是本行依据、有依据必须给评级、无依据才写 `—`）",
          "**评级的判据是本行的依据**" in hir and "依据栏写了事例的维度**必须给出评级**" in hir
          and "**只有该维度既无点评也无作答事实时评级才写 `—`**" in hir
          and "评级不得与依据矛盾、不得出现录用结论" in hir
          and "不自行给候选人评分、评级或下结论" in hir, "")
    check("面试：[综合素质] 分组分点（三组固定名 + 组内一条一个观察）",
          "**按组、按点写**" in hir and "`## 突出亮点`" in hir
          and "`## 潜在风险点`" in hir and "`## 推进建议`" in hir
          and "有内容才写该组，原文没有的组不出现" in hir, "")
    check("面试：突出亮点/风险点/推进建议三组都只写原文表达过的（不代面试官预判）",
          "只写面试官或候选人原文表达过的内容" in hir
          and "不代面试官预判风险" in hir, "")

    # 完整性总原则：课堂/讲座 requirement 明确取舍边界
    cls = (d / "class_transcript.md").read_text(encoding="utf-8")
    lec = (d / "special_lecture.md").read_text(encoding="utf-8")
    check("课堂 requirement：取舍只作用于重复/同角度/次要内容",
          "取舍只作用于重复、同角度或次要内容" in cls, "")
    check("讲座 requirement：关键论点/直接数据/典型事例必须保留",
          "取舍只作用于重复、同角度或次要论据" in lec
          and "关键论点、直接数据与典型事例**必须保留" in lec, "")

def test_media_briefing_evidence_and_depth() -> None:
    """新闻发布会：核心信息要有依据、官方表态要能归属（主体/引语/第三方落点）。

    回归背景（2026-09-18 实测两篇）：[核心信息] 那句"数据注明来源或背景"没有落点——
    慕安会篇 9 条里带依据 0 条、带数字口径 0 条；[官方表态] 8 条 0 主体（同一篇 Q&A 每轮
    反而都有 `**王毅**：`，差别只在模板有没有称呼规则），引语 3 条平均 13 字且无归属，
    现场还出现"同一句两种措辞、其中一条被标成引语"。深挖与保真都以"谁说的、依什么"为前提。

    2026-09-19 用户口径：覆盖度已达标但**太细太碎**——"一条一件事、一条不落"把条目钉在
    单指标粒度上。改法：分两层（`## 板块名` 分组 + 每组 3–5 条）、条目单位上提（一条一个
    主题、同类合并）、覆盖度口径从"条"上移到"板块/主题"；依据/口径/时间表要求保持不变。
    """
    from core.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    core = next(l for l in text.splitlines() if l.strip().startswith(("[按板块设立", "[提炼官方发布", "[展示官方发布")))
    stance = next(l for l in text.splitlines() if l.strip().startswith(("[记录发言人", "[只写发言人", "[按每组一行", "[按 `###")))

    check("核心信息：两级结构（`### 板块名` 分组 + 每组 1–4 条）",
          "`### 板块名`" in core and "每组 1–4 条" in core, core[:80])
    check("核心信息：组内按 `- 具体事实/数据/举措` 或 `- **要点**：` 展开",
          "- 具体事实/数据/举措" in core or "- **要点**：" in core, "")
    check("核心信息：一条讲透一个主题，一次说全，严禁拆成孤立指标碎片",
          "一条讲透一个主题" in core or "严禁拆成孤立指标碎片" in core, "")
    check("核心信息：同一指标多组取值并列写全、不只留一侧",
          "同一指标多组取值并列写全" in core or ("多组取值" in core and "不要只留一侧" in core), "")
    check("核心信息：保留加粗与 `具体内容` 标注口径",
          "关键数据加粗" in core and "`具体内容`" in core, "")
    check("核心信息：本栏不写人名与主语前缀，讲透事实依据即止",
          "本栏不写人名与主语前缀" in core or "本栏不逐条写人名" in core, "")

    check("官方表态：分组标题按 机构或职务｜议题 或 议题",
          "`### 议题`" in stance, "")
    check("官方表态：关键定调原话逐字引用，保留限定语",
          "关键定调原话逐字引用" in stance and "保留限定语" in stance, "")
    check("官方表态：第三方表态单独标明来源",
          "第三方表态标明来源" in stance, "")
    check("官方表态：与提问对应的归入 Q&A，不重复写",
          "Q&A" in stance and "不重复写" in stance, "")

    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "发布会概况"]
    check("发布会概况预算解析正常（hi=400 或 350）", bool(caps) and caps[0]["hi"] in (350, 400), f"{caps}")

def test_product_launch_overview() -> None:
    """产品发布：概况要素归位（Slogan/主体/背景）+ 卖点不越栏 + 缺项合并成一句。

    回归背景（2026-09，now.xlsx 行28）：原文 5 次出现核心 Slogan 与研发主体、5 次出现
    地域对比背景，产出全丢；概况 137 字写成了"痛点+卖点清单"（167 厘米/60 厘米嵌入/无水盒），
    与 [市场定位]/[核心卖点] 重复；[定价与发售信息] 有 3 行"未提及"各占一行。
    另注：基线表里的"减少 39% 残留泡沫""拦截 99% 毛絮"原文并无，属于编造——不学。
    """
    text = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    for need in (
        "核心 Slogan（原文有则逐字写）",
        "不展开痛点清单与卖点细节",
        "约 250–400 字",
        "原文给出的地域或人群差异背景",
        "原文给出的定价策略或价值口径按其原话一并写",
        "合并成一句",
    ):
        check(f"产品发布：含「{need}」", need in text, "")
    # 概况边界补到价格与参数（治"价格写进概况、[定价与发售信息] 只剩未提及"）
    for need in (
        "价格归 [定价与发售信息]",
        "参数与代际对比归 [核心卖点与技术参数]",
        "本栏不复述",
        "目标人群与一句话定位",
        "与发布场合",
    ):
        check(f"产品发布：概况栏边界/要素含「{need}」", need in text, "")

    # 首栏尺寸抬到 ≥动态下限（238）：这两栏首句是"一段话交代…"，进不了首栏四要素分支，
    # 只能靠模板自述的尺寸；写 120 会让它们成为唯一低于下限的一档。
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    check("专题讲座：概况栏尺寸已抬到 250–400 字", "约 250–400 字" in lecture, "")
    leftovers = [
        p.stem
        for p in _active_dir().glob("*.md")
        if "约 120–250 字" in p.read_text(encoding="utf-8")
    ]
    check("首栏尺寸统一到 250–400（旧的 120–250 已清除）", not leftovers, f"残留={leftovers}")

def test_retro_annual_groups() -> None:
    """复盘会 [结果与关键成果]：业务按议题模块分组、成员评价独立小节集中呈现，彻底拔除软引导。

    回归背景：移除旧的硬编码年度场景（表彰、福利）与软引导示例，
    成员评价从散乱的多标题 ### 姓名 收敛为 ### 成员评价 下的一人一行。
    """
    text = (_active_dir() / "retrospective_session.md").read_text(encoding="utf-8")
    for need in (
        "# [结果与关键成果]",
        "### 模块名",
        "### 成员评价",
        "- **姓名**：一句话客观评价与事实依据",
        "一条一人，一句话写完，不拆多条",
    ):
        check(f"复盘会：含「{need}」", need in text, "")
    check("复盘会：旧年度专用栏名与固定五分组已移除",
          "# [全年结果与表彰]" not in text and "固定五分组" not in text, "")
    check("复盘会：软引导示例与特定场景词汇已拔除",
          "交付与里程碑" not in text and "年度总结、奖项、表彰或福利" not in text, "")

def test_fallback_text_dedupe() -> None:
    """降级拼装：headline 与文档标题重复时不再重复输出；「；」连接不再出现「。；」。"""
    from domains.meeting.tasks.minutes.contracts import MinutesFallbackRules
    from core.graph.engine_text import fallback_text

    headline = "闲聊出门必带物品与个人习惯"
    state = {
        "objective_perspective": True,
        "lines": {"minutes": {"draft": {
            "headline": headline,
            "executive_summary": ["第一件事结束了。", "第二件事也完成了。"],
            "unresolved_questions": ["还有疑问吗？"],
        }}},
    }
    text, _ = fallback_text(state, "minutes", MinutesFallbackRules, {}, lambda s: "", "", title=headline)
    check("降级文本不再重复文档标题（headline 去重）", text.count(headline) == 0, f"{text[:40]!r}")
    check("多项用「；」连接、不出现「。；」", "。；" not in text and "；" in text, f"{text!r}")
    text2, _ = fallback_text(state, "minutes", MinutesFallbackRules, {}, lambda s: "", "", title="别的标题")
    check("标题不同时仍保留 headline", text2.startswith(headline), f"{text2[:24]!r}")

def test_first_column_single_paragraph_merge() -> None:
    """总述栏「一段写完」的程序保证：多段合并成一段 + 总述栏豁免拆段（两条规则不打架）。

    回归背景（2026-09-19 now.xlsx 实测）：项目概况 862 字/3 段、沟通背景 974 字/3 段、
    课程概况 734 字/4 段——"一段写完"只有 prompt 约束；节级预算只管"单段超上限才拆"，
    模型拆成 3 段每段 ≤400 时任何检查都不触发；_overlong_issue 报了又被 repair 豁免。

    补记（2026-09-21 通用纪要实测）：规则按"位置"认总述栏会认错——首栏按规范只写一段
    时定位滑到下一栏（[分段速览]）并把它合并、`##` 子标题一起删；⑤⑥⑦ 就是这次的口径。
    """
    from core.execution.gate import (
        _merge_first_column_paragraphs,
        enforce_render_output,
    )
    from core.templates.template_eval import parse_section_char_budgets

    d = _active_dir()
    # ① 三个此前无尺寸的模板现在可解析出节级预算
    for stem, col in (
        ("retrospective_session", "复盘目标与结果概况"),
        ("class_transcript", "课程概况"),
        ("site_visit_tour", "参观概况"),
    ):
        text = (d / f"{stem}.md").read_text(encoding="utf-8")
        caps = [b for b in parse_section_char_budgets(text) if b["title"] == col]
        check(f"{stem}：首栏补齐尺寸（{col} 250–400/节）",
              bool(caps) and caps[0]["lo"] == 250 and caps[0]["hi"] == 400
              and caps[0]["scope"] == "section", f"{caps}")

    # ② 合并函数：多段散文 → 一段（用真实产物形态）
    #    「首栏 3 段」＝一个 [项目概况] 栏里三个散文段；写法上必须让 `* 40` 只作用于整句，
    #    否则字面量隐式拼接（优先级高于 `*`）会把 `# 项目进度会`/`# 项目概况` 复制 40 遍，
    #    42 个一级栏的畸形稿会让断言测不到首栏（2026-09-21 修）
    tpl = (d / "project_progress.md").read_text(encoding="utf-8")
    doc = (
        "# 项目进度会\n\n# 项目概况\n"
        + "第一段总述。" * 40
        + "\n\n第二段总述。" * 30
        + "\n\n第三段收尾。" * 10
        + "\n\n# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
    )
    merged, note = _merge_first_column_paragraphs(doc, tpl)
    seg = merged.split("# 项目概况")[1].split("\n# 进度追踪")[0]
    blocks = [b for b in seg.split("\n\n") if b.strip()]
    check("总述栏 3 段合并成 1 段（文字未丢）",
          note is not None and len(blocks) == 1
          and merged.replace("\n", "").replace(" ", "") == doc.replace("\n", "").replace(" ", ""),
          f"{note} 段块={len(blocks)}")
    check("其余栏（表格）不被合并触碰", "| 模块A | 正常 |" in merged, "")
    # 已是一段 → 不动
    _same, note2 = _merge_first_column_paragraphs(
        "# 项目进度会\n\n# 项目概况\n" + "总述。" * 100 + "\n", tpl
    )
    check("已是一段的栏不产生合并记录", note2 is None, f"{note2}")

    # ③ enforce 全链路：合并后首栏不被拆段（两条规则不打架）
    text, notes, _ = enforce_render_output(tpl, doc)
    seg = text.split("# 项目概况")[1].split("\n# 进度追踪")[0]
    check("enforce 后总述栏仍是一段（拆段跳过首栏）",
          len([b for b in seg.split("\n\n") if b.strip()]) == 1
          and any("合并成一段" in n for n in notes)
          and not any("项目概况」超长段" in n for n in notes),
          f"{notes}")

    # ④ 免疫检查：非「一段写完」的模板（如 debate_forum 旧场）不受影响
    other = (d / "media_qa_session.md").read_text(encoding="utf-8")
    check("media_qa_session 无「一段写完」标记 → 合并函数不生效",
          _merge_first_column_paragraphs(doc, other)[1] is None, "")

    # ⑤ 2026-09-21 通用纪要实测：首栏按规范只写一段（1 段 < 2）时定位不能滑到下一栏。
    #    旧位置口径取"第一个含 ≥2 散文段的栏"，[全文摘要] 一段被跳过 → [分段速览]
    #    （时间轴恰好 2 段）被当总述栏合并成一段，`## 时间段` 子标题随正文一起消失，
    #    门禁仍 pass（日志只有一行 INFO：「分段速览」为总述栏（一段写完））。
    gm = (d / "general_minutes.md").read_text(encoding="utf-8")
    gm_head = "# 通用纪要\n\n# 全文摘要\n本次例会围绕端侧待办与回流展开。（一段写完）\n\n"
    gm_seg = (
        "# 分段速览\n"
        "## 08:00-12:30 现场检查\n\n第一段时间段的一段话。\n\n"
        "## 12:30-17:00 讨论\n\n第二段时间段的一段话。\n\n"
        "# 要点梳理\n\n- 条目一。\n"
    )
    same, gm_note = _merge_first_column_paragraphs(gm_head + gm_seg, gm)
    check("通用纪要：首栏已是一段 → 不拿下一栏顶替总述栏（2026-09-21 实测）",
          gm_note is None and same == gm_head + gm_seg, f"{gm_note}")
    # 首栏多段时仍合并，且合的是 [全文摘要]、不碰 [分段速览] 的时间轴子标题
    gm_multi = gm_head + "第二段摘要。\n\n" + gm_seg
    merged_gm, note_gm = _merge_first_column_paragraphs(gm_multi, gm)
    check("通用纪要：首栏多段 → 合并 [全文摘要]（时间轴栏与子标题不动）",
          note_gm is not None and "全文摘要" in note_gm
          and "## 08:00-12:30 现场检查" in merged_gm
          and "## 12:30-17:00 讨论" in merged_gm, f"{note_gm}")
    gm_text, gm_notes, _ = enforce_render_output(gm, gm_multi)
    check("通用纪要：enforce 全链路后 [分段速览] 两个时间段子标题仍在",
          "## 08:00-12:30 现场检查" in gm_text.split("# 分段速览")[1]
          and "## 12:30-17:00 讨论" in gm_text.split("# 分段速览")[1],
          f"{gm_notes}")

    # ⑥ 文档标题以 `# 一级栏` 出现时（装配稿常见），总述栏仍豁免拆段——
    #    旧实现只跳"首个一级栏"，真正的总述栏落到第二位、合并完又被拆回多段。
    titled = (
        "# 项目进度会\n\n# 项目概况\n"
        + "总述。" * 200
        + "\n\n# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
    )
    t_text, t_notes, _ = enforce_render_output(tpl, titled)
    t_seg = t_text.split("# 项目概况")[1].split("# 进度追踪")[0]
    check("文档标题在场时总述栏仍不被拆段（600 字一段原样保留）",
          len([b for b in t_seg.split("\n\n") if b.strip()]) == 1
          and not any("项目概况」超长段" in n for n in t_notes),
          f"{t_notes}")

    # ⑦ 模板栏名解析不出（标记写在序言里）→ 退回位置口径：只认第一个有散文段的栏，
    #    且首栏已是一段时不得再往后找（否则就是 ⑤ 的老毛病）
    raw_tpl = "（一段写完，约 250–400 字）\n\n# [概况]\n[概述]\n\n# [其它]\n[明细]\n"
    _r, r_note = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n第一段。\n\n第二段。\n\n# 其它\n明细一。\n", raw_tpl
    )
    check("栏名解析不出：退回位置口径仍能合并首栏", r_note is not None and "概况" in r_note, f"{r_note}")
    _r2, r_note2 = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n一段。\n\n# 其它\n明细一。\n\n明细二。\n", raw_tpl
    )
    check("栏名解析不出：首栏一段时不滑到后面的多段栏", r_note2 is None, f"{r_note2}")

def test_table_isolation_and_deduplication() -> None:
    """支柱 1 与支柱 3 验证：形态 A 纯表格栏识别、形态 B 复合栏表格隔离纪律、标量去表与表头行数据去重。"""
    from core.templates.router._base import is_table_caption
    from core.templates.router._placeholder import (
        _strip_markdown_tables,
        _section_has_table,
        _column_fill_user,
        assemble_placeholder_output,
        normalize_fill_tables,
    )

    # 1. _strip_markdown_tables 单元测试
    raw_with_trailing_table = (
        "1. **用药说明**：阿莫西林 1.2g 口服。\n"
        "2. **复诊建议**：3天后复查。\n\n"
        "| 药品 | 剂量 | 用法 |\n"
        "| --- | --- | --- |\n"
        "| 阿莫西林 | 1.2g | 口服 |\n"
    )
    stripped = _strip_markdown_tables(raw_with_trailing_table)
    check("标量末尾私自绘制的 Markdown 表格被干净剥离",
          "| 药品 |" not in stripped and "2. **复诊建议**" in stripped,
          f"{stripped}")

    # 防线 3：条目列表内部（中间）潜伏表格的物理挖除与前后正文缝合（对标 1b6b7876）
    raw_with_middle_table = (
        "1. **检查安排**：留大便查潜血。\n"
        "2. **复诊安排**：汇报医生。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 斯达舒 | — | 每日四五次 | 口服 | 初有效后效果不佳 |\n"
        "| 奥美拉唑 | — | — | 口服 | 武汉药厂生产 |\n\n"
        "3. **生活方式与饮食**：戒烟戒酒。"
    )
    stripped_mid = _strip_markdown_tables(raw_with_middle_table)
    check("标量条目中间潜伏的 Markdown 表格被物理挖除且前后条目自然缝合",
          "| 药品名称 |" not in stripped_mid
          and "2. **复诊安排**" in stripped_mid
          and "3. **生活方式与饮食**" in stripped_mid,
          f"{stripped_mid}")

    raw_with_leading_table = "| 类别 | 内容 |\n| --- | --- |\n| A | B |\n\n正文要点内容"
    stripped_lead = _strip_markdown_tables(raw_with_leading_table)
    check("标量开头私自绘制的 Markdown 表格被物理剥离",
          "| 类别 |" not in stripped_lead and stripped_lead == "正文要点内容",
          f"{stripped_lead}")

    text_with_inline_pipe = "- **责任人**：张三 | 组长\n- **说明**：普通文本含管道符"
    kept_pipe = _strip_markdown_tables(text_with_inline_pipe)
    check("正文中非表格的管道符文字完整保留",
          kept_pipe == text_with_inline_pipe.strip(),
          f"{kept_pipe}")

    only_table = "| 列1 | 列2 |\n| --- | --- |\n| 值1 | 值2 |"
    check("纯表格文本被剥离为空", _strip_markdown_tables(only_table) == "", f"{_strip_markdown_tables(only_table)}")

    # 2. 支柱 3-2：normalize_fill_tables 表头数据行过滤
    row_templates = [{
        "header_cells": ["维度", "本产品", "上代/竞品", "提升"],
        "fields": [{"hint": "维度"}, {"hint": "本产品"}, {"hint": "上代/竞品"}, {"hint": "提升"}],
    }]
    dup_header_tables = [[
        ["维度", "本产品", "上代/竞品", "提升"],  # 误输出的表头数据行
        ["机身高度", "167厘米", "洗烘套装叠放", "无需踮脚操作"],  # 真实数据行
    ]]
    norm = normalize_fill_tables(dup_header_tables, row_templates)
    check("normalize_fill_tables 成功过滤重复表头数据行",
          len(norm[0]) == 1 and norm[0][0][0] == "机身高度",
          f"{norm}")

    # 3. 支柱 1 形态 A：纯表格承载栏识别与防线 1（彻底剔除纯表格标量）
    hiring_caption = (
        "[**本栏明细由下表承载**(本栏不再另写说明文字、不要写「未提及」)："
        "**一行一个评估维度**，维度名取原文的考察要素或评价口径……评级的判据是本行的依据……]"
    )
    check("面试报告能力评估说明行被识别为纯表格栏说明",
          is_table_caption(hiring_caption),
          f"{is_table_caption(hiring_caption)}")

    court_caption = (
        "[**本栏明细由下表承载**(本栏不再另写说明文字、不要写「未提及」；二审等无原告/被告之分时按实际立场方填写)："
        "**每个立场方各一行，行数与当事方数量一致**……]"
    )
    check("庭审记录诉辩说明行被识别为纯表格栏说明",
          is_table_caption(court_caption),
          f"{is_table_caption(court_caption)}")

    with open("resources/templates/hiring_report.md", "r", encoding="utf-8") as f:
        hiring_tpl = f.read()
    hiring_plan = plan_placeholder_fill(hiring_tpl)
    check("防线1：面试报告能力评估在计划层彻底剔除纯表格标量（仅3个标量，不调模型）",
          len(hiring_plan["scalars"]) == 3
          and all("能力评估" not in s.get("hint", "") for s in hiring_plan["scalars"]),
          f"{[s.get('hint')[:20] for s in hiring_plan['scalars']]}")

    # 4. 支柱 1 形态 B：复合栏表格隔离纪律注入
    with open("resources/templates/clinical_advisory.md", "r", encoding="utf-8") as f:
        clinical_tpl = f.read()
    check("临床咨询的「治疗方案与医嘱」被识别为复合表格栏",
          _section_has_table(clinical_tpl, "治疗方案与医嘱"),
          "")
    col_user = _column_fill_user(
        "上下文",
        clinical_tpl,
        index=4,
        total=5,
        hint="医嘱清单",
        title="治疗方案与医嘱",
        others=["就诊概况", "病史与背景"],
    )
    check("复合表格栏用户提示词中成功注入【表格隔离纪律】",
          "【表格隔离纪律】" in col_user and "严禁在正文输出任何 Markdown 表格" in col_user,
          f"{col_user}")

    # 5. 拼装层去重集成验证：模拟模型在标量末尾或条目中间画了表，拼装后只有一个表
    scalar_values = [
        "就诊概况正文",
        "病史背景正文",
        "诊断检查正文",
        (
            "1. **检查安排**：留大便做检查。\n"
            "2. **用药说明**：阿莫西林与斯达舒。\n\n"
            "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 斯达舒 | — | 每日四五次 | 口服 | 初有效后效果不佳 |\n"
        ),
        "复诊预警正文",
    ]
    extracted_tables = [[
        ["斯达舒", "未提及", "每日四五次", "口服", "初有效后效果不佳"],
    ]]
    assembled = assemble_placeholder_output(
        clinical_tpl,
        scalar_values,
        tables=extracted_tables,
    )
    check("拼装结果中只包含一份表格（表头出现且仅出现一次）",
          assembled.count("| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |") == 1,
          f"{assembled}")
    check("正文清单与表格提取数据同时存在且无重复表格",
          "留大便做检查" in assembled and "| 斯达舒 | 未提及 | 每日四五次 |" in assembled,
          f"{assembled}")

    # 防线 3 集成验证：条目列表中间插表的标量在拼装时被干净挖除并自然缝合
    scalar_values_mid = [
        "就诊概况正文",
        "病史背景正文",
        "诊断检查正文",
        raw_with_middle_table,
        "复诊预警正文",
    ]
    assembled_mid = assemble_placeholder_output(
        clinical_tpl,
        scalar_values_mid,
        tables=extracted_tables,
    )
    check("条目中间潜伏表格的标量拼装后仅出现一份表格且条目1/2/3全部保留",
          assembled_mid.count("| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |") == 1
          and "1. **检查安排**" in assembled_mid
          and "2. **复诊安排**" in assembled_mid
          and "3. **生活方式与饮食**" in assembled_mid
          and "| 斯达舒 | 未提及 | 每日四五次 |" in assembled_mid,
          f"{assembled_mid}")

def test_section_pruner_adaptive_omission() -> None:
    """验证 SectionPruner 智能栏目修剪：
    1. 当某栏目正文为空串或仅含缺省词（且模板允许隐去）时，物理吃掉前置标题行；
    2. 直出快线在 0 事实时返回空串触发修剪，不产生光杆标题也不填「未提及」；
    3. 行内分组内容驱动：无条目不立组名。
    """
    from core.execution.gate import gate_render_output
    from core.templates.router._placeholder import (
        assemble_placeholder_output,
        _format_action_items_projection,
        _format_risks_projection,
    )

    tpl = (
        "# 个人视角纪要\n\n"
        "## [会议概况]\n[概况内容]\n\n"
        "## [相关行动]\n[分层看板化呈现行动项]\n\n"
        "## [相关风险]\n[分块呈现个人卡点与隐患，无风险整栏隐去]\n"
    )

    # 1. 风险栏为空串：物理剔除 ## 相关风险
    assembled_blank = assemble_placeholder_output(
        tpl,
        {"1": "会议概况内容。", "2": "**本人相关**：\n- [ ] 推进压测", "3": ""},
    )
    check("SectionPruner：空栏目物理剔除标题行",
          "## 相关风险" not in assembled_blank and "## 相关行动" in assembled_blank,
          assembled_blank)
    check("SectionPruner：空栏目不含「未提及」",
          "未提及" not in assembled_blank,
          assembled_blank)

    gate_blank = gate_render_output(tpl, assembled_blank)
    check("SectionPruner：修剪后门禁无光杆标题硬伤",
          bool(gate_blank.get("gate_ok")) and not gate_blank.get("hard_issues"),
          f"hard={gate_blank.get('hard_issues')}")

    # 2. 风险栏即便返回「未提及」，SectionPruner 亦自适应修剪
    assembled_def = assemble_placeholder_output(
        tpl,
        {"1": "会议概况内容。", "2": "**本人相关**：\n- [ ] 推进压测", "3": "未提及"},
    )
    check("SectionPruner：纯缺省词栏目物理剔除标题行",
          "## 相关风险" not in assembled_def and "未提及" not in assembled_def,
          assembled_def)

    # 3. 投影层 0 事实直出空串（不生成伪条目）
    act_empty = _format_action_items_projection([], user_name="张三")
    check("投影直出：行动项 0 事实返回空串", act_empty == "", repr(act_empty))

    risk_empty = _format_risks_projection([], user_name="张三")
    check("投影直出：风险项 0 事实返回空串", risk_empty == "", repr(risk_empty))

    # 4. 行内分组内容驱动：无本人待办时，不设立孤独的本人组名或占位词
    act_focus_only = _format_action_items_projection(
        ["**重点协同**：", "**李四**：周五前提供接口文档"],
        user_name="张三",
        focus_persons=["李四"],
    )
    check("内容驱动建组：仅保留有事项的分组",
          "**重点协同**：" in (act_focus_only or "") and "李四" in (act_focus_only or ""),
          repr(act_focus_only))
    check("内容驱动建组：无本人条目不建本人组名",
          "**本人相关**：" not in (act_focus_only or "") and "暂无本人直接待办" not in (act_focus_only or ""),
          repr(act_focus_only))

