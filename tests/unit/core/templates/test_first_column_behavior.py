# 拆分自 test_section_pruner_behavior.py，覆盖：test_paragraph_split, test_two_level_list_parent_retention, test_first_column_single_paragraph_merge…

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
from tests.support.expectations import expect
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
)

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
    expect(any(b["hi"] == 400 and b.get("scope") == "paragraph"
              for b in parse_section_char_budgets(tpl)), "拆分用模板：段落上限已识别", f"{parse_section_char_budgets(tpl)}")

    long_para = "本次会议围绕小区物业服务与业主权益展开专项讨论。" * 30  # ≈690 汉字
    doc = f"# 摘要\n{long_para}\n"
    fixed, _ = split_overlong_paragraphs(doc, tpl)
    body_only = fixed.split("\n", 1)[1] if "\n" in fixed else fixed
    parts = [p for p in body_only.split("\n\n") if p.strip()]
    han_of = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s))
    expect(len(parts) >= 2 and all(han_of(p) <= 400 for p in parts), "超长段被按句界拆开（≥2 段且每段汉字 ≤ 上限）", f"段数={len(parts)} 各段汉字={[han_of(p) for p in parts]}")
    expect(re.sub(r"\s", "", fixed) == re.sub(r"\s", "", doc), "拆分只加换行、不改文字", "")
    gate = gate_render_output(tpl, fixed)
    expect(not any("超出段落字数上限" in x for x in gate["issues"]), "拆完不再报「超出段落字数上限」", f"{gate['issues']}")

    # 段边界丢换行曾把 `# 栏名` 粘到上一栏末尾：渲染层对同一文本跑两次 enforce，
    # 第一遍把空行削成单换行、第二遍直接粘连（2026-09-22 真链路实测）。
    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    split_tpl = (
        "# 通用纪要\n\n# [背景]\n[一段话概括背景]\n\n"
        "# [要点梳理]\n[一段话列出要点，每段不超过 400 字]\n"
    )
    two = "# 背景\n背景。\n\n# 要点梳理\n" + long_para + "\n"
    once, n_once = split_overlong_paragraphs_except_first(two, split_tpl)
    twice, _ = split_overlong_paragraphs_except_first(once, split_tpl)
    expect(n_once and "\n\n# 要点梳理" in once and "\n\n# 要点梳理" in twice, "段边界换行保留（跑两次也不把 `# 要点梳理` 粘上去）", f"once={once[-26:]!r} twice={twice[-26:]!r}")
    glued_doc, gnotes, _ = enforce_render_output(gm, "# 分段速览\n正文结束。# 要点梳理\n- 乙\n")
    expect("\n# 要点梳理" in glued_doc and any("粘连" in n for n in gnotes), "已粘连的栏名由兜底步骤提回独立行", f"{gnotes} {glued_doc[-34:]!r}")

    # 回归（2026-09-22）：`## 栏名` 曾被误判为「粘在正文里的栏名」⇒ 改写成 `#` 裸行 +
    # 重复标题（knowledge_memo 的 `## 核心结论` 稳定复现）。合法子标题必须原样保留。
    keep_doc, keep_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n## 分段速览\n- 乙\n"
    )
    expect("## 分段速览" in keep_doc
          and not re.search(r"(?m)^#\s*$", keep_doc)
          and not keep_notes, "合法的 ## 子标题（与栏名同名）保持原样、不改写", f"{keep_notes} {keep_doc[-46:]!r}")
    keep2, keep2_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n### 分段速览\n- 乙\n"
    )
    expect("### 分段速览" in keep2 and not keep2_notes, "合法的 ### 子标题同样不改写", "")

    # 标题形态加固（2026-09-22）：裸标题确定性删除；同级别同名标题重复判硬伤。
    bare_doc, bare_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n#\n\n# 分段速览\n- 乙\n"
    )
    expect(not re.search(r"(?m)^#\s*$", bare_doc)
          and any("裸标题" in n for n in bare_notes), "裸标题行（只有 # 没有文字）被确定性删除并记 note", f"{bare_notes} {bare_doc[-40:]!r}")


def test_two_level_list_parent_retention() -> None:
    """两级嵌套列表（新闻发布会、家校沟通）：独立成行的父标题节点下挂缩进子项时不能被误判为缺省词。"""
    from core.execution.hard_execution import strip_default_only_content

    text = (
        "## 官方表态\n\n"
        "- **平等有序的世界多极化（王毅）**：\n"
        '  - 多极化是历史必然，但需避免动荡失序，中国主张"推动平等有序的世界多极化"。\n'
        '  - 中国必将是多极体系中的确定性因素，将坚定做变革世界中的建设性力量。\n\n'
        "- **国际秩序与联合国作用（王毅）**：\n"
        "  - 中国是现行国际秩序的受益者，主张推动秩序向更加公正合理方向发展。\n"
        "  - 共同维护以联合国为核心的国际体系、遵守联合国宪章宗旨和原则是最大公约数。\n\n"
        "- **过敏史**：未提及。\n"
    )
    out, notes = strip_default_only_content(text)
    expect("- **平等有序的世界多极化（王毅）**：" in out, "父级议题行未被误删", out)
    expect("- **国际秩序与联合国作用（王毅）**：" in out, "第二组父级议题行未被误删", out)
    expect("- **过敏史**" not in out, "真实单行缺省项被正常删除", out)
    expect(any("已省略" in n for n in notes), "仅单行缺省项计入删除数（无误判）", f"{notes}")


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
        ("retrospective_session", "复盘概况"),
        ("class_transcript", "课程概况"),
        ("site_visit_tour", "参观概况"),
    ):
        text = (d / f"{stem}.md").read_text(encoding="utf-8")
        caps = [b for b in parse_section_char_budgets(text) if b["title"] == col]
        expect(bool(caps) and caps[0]["hi"] == 200,
              f"{stem}：首栏尺寸（{col} 200字以内）", f"{caps}")

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
    expect(note is not None and len(blocks) == 1
          and merged.replace("\n", "").replace(" ", "") == doc.replace("\n", "").replace(" ", ""), "总述栏 3 段合并成 1 段（文字未丢）", f"{note} 段块={len(blocks)}")
    expect("| 模块A | 正常 |" in merged, "其余栏（表格）不被合并触碰", "")
    # 已是一段 → 不动
    _same, note2 = _merge_first_column_paragraphs(
        "# 项目进度会\n\n# 项目概况\n" + "总述。" * 100 + "\n", tpl
    )
    expect(note2 is None, "已是一段的栏不产生合并记录", f"{note2}")

    # ③ enforce 全链路：合并后首栏不被拆段（两条规则不打架）
    text, notes, _ = enforce_render_output(tpl, doc)
    seg = text.split("# 项目概况")[1].split("\n# 进度追踪")[0]
    expect(len([b for b in seg.split("\n\n") if b.strip()]) == 1
          and any("合并成一段" in n for n in notes)
          and not any("项目概况」超长段" in n for n in notes), "enforce 后总述栏仍是一段（拆段跳过首栏）", f"{notes}")

    # ④ 免疫检查：非「一段写完」的模板（如 debate_forum 旧场）不受影响
    other = (d / "media_qa_session.md").read_text(encoding="utf-8")
    expect(_merge_first_column_paragraphs(doc, other)[1] is None, "media_qa_session 无「一段写完」标记 → 合并函数不生效", "")

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
    expect(gm_note is None and same == gm_head + gm_seg, "通用纪要：首栏已是一段 → 不拿下一栏顶替总述栏（2026-09-21 实测）", f"{gm_note}")
    # 首栏多段时仍合并，且合的是 [全文摘要]、不碰 [分段速览] 的时间轴子标题
    gm_multi = gm_head + "第二段摘要。\n\n" + gm_seg
    merged_gm, note_gm = _merge_first_column_paragraphs(gm_multi, gm)
    expect(note_gm is not None and "全文摘要" in note_gm
          and "## 08:00-12:30 现场检查" in merged_gm
          and "## 12:30-17:00 讨论" in merged_gm, "通用纪要：首栏多段 → 合并 [全文摘要]（时间轴栏与子标题不动）", f"{note_gm}")
    gm_text, gm_notes, _ = enforce_render_output(gm, gm_multi)
    expect("## 08:00-12:30 现场检查" in gm_text.split("# 分段速览")[1]
          and "## 12:30-17:00 讨论" in gm_text.split("# 分段速览")[1], "通用纪要：enforce 全链路后 [分段速览] 两个时间段子标题仍在", f"{gm_notes}")

    # ⑥ 文档标题以 `# 一级栏` 出现时（装配稿常见），总述栏仍豁免拆段——
    #    旧实现只跳"首个一级栏"，真正的总述栏落到第二位、合并完又被拆回多段。
    titled = (
        "# 项目进度会\n\n# 项目概况\n"
        + "总述。" * 200
        + "\n\n# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
    )
    t_text, t_notes, _ = enforce_render_output(tpl, titled)
    t_seg = t_text.split("# 项目概况")[1].split("# 进度追踪")[0]
    expect(len([b for b in t_seg.split("\n\n") if b.strip()]) == 1
          and not any("项目概况」超长段" in n for n in t_notes), "文档标题在场时总述栏仍不被拆段（600 字一段原样保留）", f"{t_notes}")

    # ⑦ 模板栏名解析不出（标记写在序言里）→ 退回位置口径：只认第一个有散文段的栏，
    #    且首栏已是一段时不得再往后找（否则就是 ⑤ 的老毛病）
    raw_tpl = "（一段写完，约 250–400 字）\n\n# [概况]\n[概述]\n\n# [其它]\n[明细]\n"
    _r, r_note = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n第一段。\n\n第二段。\n\n# 其它\n明细一。\n", raw_tpl
    )
    expect(r_note is not None and "概况" in r_note, "栏名解析不出：退回位置口径仍能合并首栏", f"{r_note}")
    _r2, r_note2 = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n一段。\n\n# 其它\n明细一。\n\n明细二。\n", raw_tpl
    )
    expect(r_note2 is None, "栏名解析不出：首栏一段时不滑到后面的多段栏", f"{r_note2}")


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
    expect("## 相关风险" not in assembled_blank and "## 相关行动" in assembled_blank, "SectionPruner：空栏目物理剔除标题行", assembled_blank)
    expect("未提及" not in assembled_blank, "SectionPruner：空栏目不含「未提及」", assembled_blank)

    gate_blank = gate_render_output(tpl, assembled_blank)
    expect(bool(gate_blank.get("gate_ok")) and not gate_blank.get("hard_issues"), "SectionPruner：修剪后门禁无光杆标题硬伤", f"hard={gate_blank.get('hard_issues')}")

    # 2. 风险栏即便返回「未提及」，SectionPruner 亦自适应修剪
    assembled_def = assemble_placeholder_output(
        tpl,
        {"1": "会议概况内容。", "2": "**本人相关**：\n- [ ] 推进压测", "3": "未提及"},
    )
    expect("## 相关风险" not in assembled_def and "未提及" not in assembled_def, "SectionPruner：纯缺省词栏目物理剔除标题行", assembled_def)

    # 3. 投影层 0 事实直出空串（不生成伪条目）
    act_empty = _format_action_items_projection([], user_name="张三")
    expect(act_empty == "", "投影直出：行动项 0 事实返回空串", repr(act_empty))

    risk_empty = _format_risks_projection([], user_name="张三")
    expect(risk_empty == "", "投影直出：风险项 0 事实返回空串", repr(risk_empty))

    # 4. 行内分组内容驱动：无本人待办时，不设立孤独的本人组名或占位词
    act_focus_only = _format_action_items_projection(
        ["**重点协同**：", "**李四**：周五前提供接口文档"],
        user_name="张三",
        focus_persons=["李四"],
    )
    expect("**重点协同**：" in (act_focus_only or "") and "李四" in (act_focus_only or ""), "内容驱动建组：仅保留有事项的分组", repr(act_focus_only))
    expect("**本人相关**：" not in (act_focus_only or "") and "暂无本人直接待办" not in (act_focus_only or ""), "内容驱动建组：无本人条目不建本人组名", repr(act_focus_only))


def test_meta_omission_leak_pruning() -> None:
    """测试防止'本栏隐去'等提示词黑话泄漏：SectionPruner 与 clean_template_render_text 物理剥离整节。"""
    from core.templates.router._placeholder import assemble_placeholder_output
    from core.execution.hard_execution import clean_template_render_text
    from core.execution.gate import gate_render_output

    tpl = (
        "# 专题讲座\n\n"
        "## [讲座概况]\n[概况描述]\n\n"
        "## [Q&A 环节]\n[(现场有互动问答才呈现，若全场无问答互动则本栏整体不予呈现) 一问一答]\n"
    )

    # 1. 占位装配层（SectionPruner）：模型给出了"无现场问答互动，本栏隐去。"
    assembled = assemble_placeholder_output(
        tpl,
        {"1": "本次讲座系统解析了微服务架构演进。", "2": "无现场问答互动，本栏隐去。"},
    )
    expect("## Q&A 环节" not in assembled and "本栏隐去" not in assembled, "SectionPruner：元指令泄漏句栏目被物理剔除标题行", assembled)
    expect("## 讲座概况" in assembled and "本次讲座系统解析了微服务架构演进" in assembled, "SectionPruner：保留正常概况栏目", assembled)

    # 2. 渲染后处理层（clean_template_render_text）：自由渲染路径直接输出了残留
    raw_leak = (
        "# 专题讲座\n\n"
        "## 讲座概况\n本次讲座系统解析了微服务架构演进。\n\n"
        "## Q&A 环节\n无现场问答互动，本栏隐去。\n"
    )
    cleaned, notes = clean_template_render_text(raw_leak)
    expect("## Q&A 环节" not in cleaned and "本栏隐去" not in cleaned, "clean_template_render_text：整栏物理剥离（含标题行）", cleaned)
    expect(gate_render_output(tpl, cleaned)["gate_ok"], "clean_template_render_text：门禁放行且无光杆标题硬伤", f"{gate_render_output(tpl, cleaned)}")

    # 3. 若正文是自然业务语言，则正常保留
    natural = (
        "# 专题讲座\n\n"
        "## 讲座概况\n本次讲座系统解析了微服务架构演进。\n\n"
        "## Q&A 环节\n本次讲座以主旨观点分享为主，现场未设置问答互动环节。\n"
    )
    cleaned_nat, _ = clean_template_render_text(natural)
    expect("## Q&A 环节" in cleaned_nat and "现场未设置问答互动环节" in cleaned_nat, "自然业务语言正文予以正常保留", cleaned_nat)


def test_topic_major_negative_generation_leak_pruning() -> None:
    """topic_major：子栏照抄「没有对应事实的，不生成该子栏标题与正文」时同样物理剥离。"""
    from core.execution.hard_execution import clean_template_render_text

    raw = (
        "# 团队例会\n\n"
        "## 例会概况\n本周例会围绕支付链路上线推进。\n\n"
        "## 议题梳理\n\n"
        "### 一. 支付链路优化\n\n"
        "#### 工作进展\n本次完成灰度发布。\n\n"
        "#### 落实安排\n没有对应事实的，不生成该子栏标题与正文。\n\n"
        "#### 未决风险\n该子栏无对应事实，不生成。\n"
    )
    cleaned, notes = clean_template_render_text(raw)
    expect("#### 落实安排" not in cleaned, "「不生成」元指令泄漏：整栏含标题物理剥离", cleaned)
    expect("#### 未决风险" not in cleaned, "无对应事实句式的子栏同样剥离", cleaned)
    expect("#### 工作进展" in cleaned and "本次完成灰度发布" in cleaned, "有效子栏保留", cleaned)
    expect(any("落实安排" in n for n in notes), "剥离动作写入日志", str(notes))


def test_placeholder_pruner_negative_generation_leak() -> None:
    """占位符装配层：栏目正文照抄「没有对应事实…不生成」时同样剔除标题行。"""
    from core.templates.router._placeholder import assemble_placeholder_output

    tpl = (
        "# 团队例会\n\n"
        "## [例会概况]\n[概况描述]\n\n"
        "## [议题梳理]\n[议题描述]\n"
    )
    assembled = assemble_placeholder_output(
        tpl,
        {"1": "本周例会围绕支付链路上线推进。", "2": "没有对应事实的，不生成该子栏标题与正文。"},
    )
    expect("## 议题梳理" not in assembled and "不生成" not in assembled, "装配层：元指令栏目连标题剔除", assembled)
    expect("## 例会概况" in assembled and "支付链路上线" in assembled, "装配层：正常栏目保留", assembled)


def test_first_column_single_paragraph_synergy() -> None:
    """首栏单段控制与 Prefix Caching 协同优化完整闭环验证：
    1. 安全气囊正则：_FIRST_COL_PARA_RE 覆盖全库 31 个散文单段总述模板（100% 覆盖）；
    2. 契约生成层：总述类栏位统一生成【形态要求：必须且只写一段完整概括，严禁换行分段】；
    3. 后处理折叠：模拟 LLM 输出 4 段式长篇概览，物理合并为恰好 1 个自然段。
    """
    from core.execution.gate import (
        _FIRST_COL_PARA_RE,
        _merge_first_column_paragraphs,
    )
    from core.templates.router._base import _describe_field
    from core.templates.router._detect import parse_placeholder_template, split_template_meta

    d = _active_dir()
    templates = list(d.glob("*.md"))
    assert len(templates) >= 29, f"模板数量不足: {len(templates)}"

    # 1. 验证全库模板正则覆盖率
    matched = []
    unmatched = []
    for tpl_file in templates:
        content = tpl_file.read_text(encoding="utf-8")
        if _FIRST_COL_PARA_RE.search(content):
            matched.append(tpl_file.name)
        else:
            unmatched.append(tpl_file.name)

    # 移出任务专有模板后，全部 30 个场景模板 100% 覆盖首栏单段正则
    expect(len(matched) == len(templates) and not unmatched, "安全气囊正则覆盖全部散文单段总述模板", f"matched={len(matched)}, unmatched={unmatched}")

    # 2. 验证典型模板的首栏契约生成
    gm_path = d / "general_minutes.md"
    clean, req = split_template_meta(gm_path.read_text(encoding="utf-8"))
    segs = parse_placeholder_template(clean)
    fields = [s for s in segs if s.get("kind") == "field"]
    assert fields, "通用纪要字段解析失败"
    desc1 = _describe_field(1, fields[0])
    expect("【形态要求】：必须且只写一段完整概括，严禁换行分段" in desc1
        and "200字以内" in desc1, "通用纪要首栏生成显式单段契约", desc1)

    # 3. 验证典型多段输出的物理级合并折叠
    multi_summary = (
        "## 全文摘要\n\n"
        "本次例会围绕数字化平台升级开展研讨，第一阶段由技术组汇报架构演进。\n\n"
        "第二阶段针对高并发场景下的链路可用性进行重点评估，各方就降级方案达成一致。\n\n"
        "第三阶段讨论了跨部门协同机制，明确了下周一启动联合联调测试。\n\n"
        "第四阶段由管理层总结定调，强调按既定里程碑推进交付，确保按时上线。\n\n"
        "## 要点梳理\n\n"
        "- **议题一**：架构升级细节。\n"
        "- **议题二**：可用性评估。\n"
    )
    merged, note = _merge_first_column_paragraphs(multi_summary, clean)
    expect(note is not None and "全文摘要" in note, "多段摘要被成功检测并记录合并 note", f"{note}")

    summary_part = merged.split("## 全文摘要")[1].split("## 要点梳理")[0].strip()
    paras = [p for p in summary_part.split("\n\n") if p.strip()]
    expect(len(paras) == 1, "多段摘要被确定性合并为恰好 1 个自然段", f"paras={len(paras)}")
    expect(all(k in summary_part for k in ["第一阶段", "第二阶段", "第三阶段", "第四阶段"]), "合并后正文字符完整无丢失", summary_part)
