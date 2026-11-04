# 拆分自 test_meeting_memory.py，覆盖：test_personal_minutes_html_rendering, test_personal_minutes_v2_template_rendering, test_review_panel_ledger_group…

"""会议记忆零 LLM 衡约：身份、不传 project 接续、状态机、时间/场次。

用法::

    python -m tests.test_meeting_memory
"""

from __future__ import annotations
import json
from pathlib import Path
from domains.meeting.memory.bind import (
    bind_meeting,
    is_strong_anchor,
    is_weak_project_name,
    pick_project_name,
    project_core,
)
from domains.meeting.memory.extract import MeetingFact, extract_meeting_fact
from domains.meeting.memory.inject import build_memory_context, preview_comparison
from domains.meeting.memory.render import parse_memory_items
from domains.meeting.memory.runtime import persist_after_run, resolve_bind
from domains.meeting.memory.state import rebuild_state, session_index, session_label, update_state
from domains.meeting.memory.store import list_meetings, load_registry, load_state
from tests.support.expectations import expect

def _fact(**kwargs) -> MeetingFact:
    data = {
        "meeting_id": "m_1",
        "time": "2026-09-01",
        "time_source": "user",
        "title": "小艺慧记Agent开发进展阶段复盘",
        "summary": "复盘小艺慧记Agent第一阶段",
        "anchors": ["小艺慧记Agent"],
        "project_candidates": ["小艺慧记Agent"],
        "decisions": ["8月18日前优化 minutes_trace"],
        "open_items": ["是否默认开启记忆引用"],
        "action_items": [{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": "8月19日前"}],
        "risks": ["记忆可解释性不足"],
        "closed_items": [],
        "quotes": [],
    }
    data.update(kwargs)
    return MeetingFact.from_dict(data)

def test_personal_minutes_html_rendering() -> None:
    from domains.meeting.memory.render import render_minutes_html

    md = (
        "# 个人视角纪要\n\n"
        "## [本场概况与本人定调]\n"
        "本场讨论了模型压测与demo落地。\n\n"
        "## [重点关注与业务进展]\n"
        "1. **【demo落地】进展与方案**（本周内 ｜ 联调 ｜ 压测通过）\n"
        "2. **【占位符防护】测试项**(交付时限 ｜ 核心交付物/状态)\n"
        "  - 完成第一轮测试；\n\n"
        "## [行动项与协同依赖]\n"
        "### 与我相关行动项\n"
        "- [ ] **完成demo落地压测**（周五前 ｜ 报告 ｜ P99<50ms）\n"
        "- [x] **修复现网待办问题**（周三前 ｜ 补丁）\n\n"
        "### 关注人定调与协同输入\n"
        "- **[环境依赖] 张工**：明天就绪测试环境（明天下午）\n\n"
        "### 协同人员主要分工\n"
        "- **武思华**：负责权限开通\n\n"
        "## [待确认事项与风险卡点]\n"
        "### 本人及关注事项卡点\n"
        "- [ ] **【阻塞】数据表权限未开通**：无法回流\n"
        "- [ ] **【高风险】显存压力**：需额外压测\n\n"
        "### 全局重大风险与未决争议\n"
        "- **跨团队对齐延后**：可能影响整体排期\n"
    )

    html = render_minutes_html("个人视角纪要", md)
    content = html.split('<div class="ck-doc-content">')[1].split('</div>\n    </div>')[0]
    expect('<input type="checkbox"' in content, "个人模式单栏页包含交互式复选框", "")
    expect('[ ]' not in content, "个人模式无字面量 [ ]", "")
    expect("ck-self-block" in content, "个人模式生成本人待办卡片 ck-self-block", "")
    expect("ck-dep-block" in content, "个人模式生成协同输入卡片 ck-dep-block", "")
    expect("ck-risk-block" in content, "个人模式生成全局风险卡片 ck-risk-block", "")
    expect("ck-task-list" in content, "个人模式生成任务列表 ck-task-list", "")
    expect("ck-tag-blocker" in content, "个人模式生成阻塞状态徽章 ck-tag-blocker", "")
    expect("ck-tag-dep" in content, "个人模式生成依赖标签 ck-tag-dep", "")
    expect("ck-param-capsule" in content, "个人模式生成参数胶囊 ck-param-capsule", "")
    expect("核心交付物" not in content and "交付时限" not in content, "个人模式过滤占位符泄漏", "")
    expect("[本场概况与本人定调]" not in content and "本场概况与本人定调" in content, "个人模式标题方括号剔除", "")


def test_personal_minutes_v2_template_rendering() -> None:
    """验证 personal_minutes.md 标准四栏看板在 HTML 渲染中的卡片语义、徽章与单行紧凑排版。"""
    from domains.meeting.memory.render import render_minutes_html, memory_review_html

    md = (
        "# 个人视角纪要\n\n"
        "## [会议概况]\n"
        "本次会议围绕网关鉴权改造和Token缓存保护展开讨论，明确本周五前完成上线。\n\n"
        "## [业务进展]\n"
        "**网关鉴权模块**：\n"
        "- 完成第一轮接口压测，P99延迟稳定在15ms以内；\n"
        "- 技术选型拍板采用Redis集群作为缓存介质。\n\n"
        "## [相关行动]\n"
        "**本人相关**：\n"
        "- 完成网关鉴权改造压测（周三前 ｜ 报告 ｜ P99<50ms）\n"
        "- 修复现网缓存击穿Bug（周四前 ｜ 补丁）\n"
        "**重点协同**：\n"
        "- 张工：周五前完成鉴权SDK交付\n"
        "- 李工：周四前开通测试环境权限\n\n"
        "## [相关风险]\n"
        "**本人相关**：\n"
        "- [阻塞] 压测环境显存压力较大，需协调GPU资源\n"
        "**重点关注**：\n"
        "- [高风险] 跨团队联调进度滞后，可能导致周五发版延期\n"
    )

    html = render_minutes_html("个人视角纪要", md)
    content = html.split('<div class="ck-doc-content">')[1].split('</div>\n    </div>')[0]

    # 1. 行动栏验证：本人待办卡 (蓝) 与 重点协同卡 (琥珀)
    expect("ck-self-block" in content, "V2个人模板生成本人待办卡 ck-self-block", "")
    expect('<span class="ck-self-badge">本人</span>' in content, "V2个人模板包含本人徽章", "")
    expect("ck-dep-block" in content, "V2个人模板生成协同卡 ck-dep-block", "")
    expect('<span class="ck-dep-badge">重点协同</span>' in content, "V2个人模板包含重点协同徽章", "")
    dep_content = content.split('class="ck-dep-block"')[1].split("相关风险")[0]
    expect("ck-person-group" not in dep_content, "V2协同事项单行内嵌不产生人名断行", dep_content)
    expect("张工：周五前完成鉴权SDK交付" in dep_content, "V2协同事项包含张工条目", dep_content)
    expect("李工：周四前开通测试环境权限" in dep_content, "V2协同事项包含李工条目", dep_content)

    # 2. 风险栏验证：本人卡点 (红卡) 与 重点关注 (红卡)，绝对不可错套蓝色待办卡
    risk_section = content.split("相关风险")[1]
    expect("ck-self-block" not in risk_section, "V2风险栏不包含任何蓝色待办卡", risk_section)
    expect('<span class="ck-risk-badge">本人卡点</span>' in risk_section, "V2风险栏包含本人卡点红色徽章", risk_section)
    expect('<span class="ck-risk-badge">重点关注</span>' in risk_section, "V2风险栏包含重点关注红色徽章", risk_section)

    # 3. 业务进展验证：模块大盘独立呈现，不产生待办卡
    progress_section = content.split("业务进展")[1].split("相关行动")[0]
    expect("ck-self-block" not in progress_section and "ck-dep-block" not in progress_section, "V2业务进展不产生待办卡", progress_section)
    expect("网关鉴权模块" in progress_section, "V2业务进展包含模块标题", progress_section)

    # 4. 双栏 review HTML 同样验证
    rev_html = memory_review_html(md, title="个人视角纪要")
    expect("ck-dep-block" in rev_html, "V2双栏HTML生成协同卡", "")
    expect('<span class="ck-dep-badge">重点协同</span>' in rev_html, "V2双栏HTML协同包含重点协同徽章", "")
    rev_risk_part = rev_html.split("相关风险")[1]
    expect("ck-self-block" not in rev_risk_part, "V2双栏HTML风险栏无蓝色待办卡", "")
    expect('<span class="ck-risk-badge">本人卡点</span>' in rev_risk_part, "V2双栏HTML风险栏本人卡点红徽章", "")
    expect('<span class="ck-risk-badge">重点关注</span>' in rev_risk_part, "V2双栏HTML风险栏重点关注红徽章", "")


def test_review_panel_ledger_group() -> None:
    """双栏右栏分两段：本场证据（带 [n]）+ 历史台账（无 [n]，灰底）；左栏不再重复台账。

    零锚点时退回单栏页，台账留在正文小节（那是记忆唯一的可见通道）。
    """
    from domains.meeting.memory.render import render_minutes_html

    body = "# 纪要\n会上过了长文本时延。内部WeLink打标完成201、还差300多。\n"
    ledger = (
        "\n## 历史对照\n\n"
        "- 新增决策：主干侧主动锻炼由己方做处理\n"
        "- 新增决策（商品版本）：商品版本需求包括录音机命名字数、仿写流失\n"
        "- 延续事项（现网流量｜自第1场·2026-09-01）：范炳杰下来找他们拆现网流量数据\n"
        "- 已闭环（双录信号｜第1场·2026-09-01）：范炳杰这周更新一个版本把双录信号问题刷掉\n"
        "- 已闭环：解决了端侧麦克风加媒体音播报幻觉问题\n"
        "- 风险演变（WeLink标注｜持续，第1场·2026-09-01）：内部WeLink标注还差400min\n"
        "- 本场历史对照合计：新增决策 2 条、延续未决 1 条、已闭环 2 条、风险演变 1 条\n"
    )
    appendix = (
        "\n## 历史记忆引用\n\n#### 溯源 memory-1\n> WeLink标注进度\n"
        "状态：持续中\n来源会议：某会\n会议时间：2026-09-01\n"
    )
    anchored = body.replace("内部WeLink", "内部[WeLink](#memory-1)") + ledger + appendix
    html = render_minutes_html("会议纪要", anchored)
    left = html.split('class="ck-review-left"', 1)[1].split("ck-review-rule", 1)[0]
    right = html.split('class="ck-review-right"', 1)[1]
    expect("历史对照" not in left, "左栏不再出现「历史对照」（改由右栏承载）", left[-300:])
    expect('<summary class="ck-proof-toggle">状态演进（' in right, "右栏下段标题是「状态演进」", right[-400:])
    expect('ck-ev-group' not in right and 'ck-ledger-note' not in right
          and '本场证据 · 正文可点' not in right and '台账取自记忆状态' not in right, "不再输出分组标签与台账注记", "")
    ledger_part = right.split("ck-ledger", 1)[1]
    expect("ck-ev-cite-tag" not in ledger_part, "状态演进灰底无 [n] 序号", "")
    expect(ledger_part.count('class="ck-ledger-card"') == 3
          and ledger_part.count('<ol class="ck-ledger-list">') == 3
          and ledger_part.count("<li>") == 5, "每类一张卡、卡内各自编号（延续1+闭环2+新增2 → 3 张卡 3 个 <ol>）", "")
    expect('ck-ledger-count">（1）' in ledger_part and 'ck-ledger-count">（2）' in ledger_part, "卡头带类别与条数", "")
    expect(ledger_part.index('data-kind="延续事项"') < ledger_part.index('data-kind="已闭环"')
          < ledger_part.index('data-kind="新增决策"'), "卡片顺序固定 延续事项 → 已闭环 → 新增决策", "")
    expect("风险演变" not in ledger_part and "内部WeLink标注还差400min" not in ledger_part, "右栏不出现风险演变（只在正文对照里）", "")
    expect("现网流量" in right and "自第1场·2026-09-01" in right, "演进条目带主题与场次", "")
    expect("（本场）" not in right and "· 本场" not in right, "不写无信息量的「本场」", "")
    expect("ck-ev ck-mem-card" in right, "证据卡片仍在（带行内锚点）", "")

    plain = body + ledger
    html2 = render_minutes_html("会议纪要", plain)
    expect("历史对照" in html2, "零锚点单栏页保留正文里的对照小节", "")


def test_h_tag_mechanism_and_dynamic_gating() -> None:
    """相关度门禁、注入不带代号、正文 [Hn] 只删除、字面重合才挂载。"""
    from domains.meeting.memory.inject import _rank, build_memory_context
    from domains.meeting.memory.render import apply_memory_citations, parse_memory_items, memory_review_html

    # 1. 动态信噪比门禁：有相关度的入选，0分无关项不凑数
    fact = _fact(
        title="网关鉴权改造评审会",
        summary="讨论鉴权接口与Token缓存",
        decisions=["通过Token方案"],
        open_items=["网关鉴权接口联调"],
        risks=[],
    )
    items = [
        {"item_id": "a1", "text": "完成网关鉴权接口编写", "status": "open", "since": "m1"},
        {"item_id": "a2", "text": "优化Token缓存策略", "status": "open", "since": "m1"},
        {"item_id": "a3", "text": "完全不相干的前端CSS样式重构", "status": "open", "since": "m1"},
        {"item_id": "a4", "text": "人事招聘进度同步", "status": "open", "since": "m1"},
    ]
    ranked = _rank(items, fact, cap=10)
    expect(len(ranked) == 2, "TC-H-01: 仅命中事实的待办入选 (2条)", str(ranked))
    expect(all("前端" not in r["text"] and "招聘" not in r["text"] for r in ranked), "TC-H-01: 无关0分项不滥竽充数", str(ranked))

    # 2. 弹性安全天花板：超过 10 条时严格截断至 10 条
    many_items = [
        {"item_id": f"a{i}", "text": f"网关鉴权任务{i}", "status": "open", "since": "m1", "owner": "小张"}
        for i in range(15)
    ]
    ranked_10 = _rank(many_items, fact, cap=10)
    expect(len(ranked_10) == 10, "TC-H-02: 超过10条时熔断至天花板10条", str(len(ranked_10)))

    # 3. 注入是自然语言背景，不带代号
    state = {"open_items": items[:2], "actions": [], "recent_meetings": ["m1"]}
    ctx, comp = build_memory_context(
        project_id="p1",
        project={"name": "网关项目"},
        state=state,
        bind=type("B", (), {"evidence": []})(),
        meetings=[],
        current_fact=fact,
    )
    expect("【项目推进背景】" in ctx, "TC-H-03: 注入块是【项目推进背景】", ctx)
    expect("历史事项代号表" not in ctx and "[H1]" not in ctx and "[H2]" not in ctx, "TC-H-03: 注入不含代号表与 [H1]", ctx)
    parsed = parse_memory_items(ctx)
    expect(len(parsed) == 2 and parsed[0].text.startswith("完成网关鉴权") and not hasattr(parsed[0], "tag"), "TC-H-03: 解析出条目且不带代号", str(parsed))

    # 4. 正文不写代号，字面重合才挂链接
    body = (
        "# 纪要\n"
        "团队针对核心模块进行复盘，网关鉴权接口已全量完成联调，后续继续优化Token缓存策略。\n"
    )
    out = apply_memory_citations(body, ctx, comparison=comp)
    expect("(#memory-1)" in out, "TC-H-04: 网关鉴权接口挂上第一条", out)
    expect("(#memory-2)" in out, "TC-H-04: Token缓存策略挂上第二条", out)
    expect("#### 溯源 memory-1" in out and "#### 溯源 memory-2" in out, "TC-H-04: 文末生成对应数量的溯源卡片", out)
    expect("[H1]" not in out and "[H2]" not in out, "TC-H-04: 挂载不靠 [Hn]", out)

    # 5. 模型打出的代号只删除，不换成链接
    body_hallucinated = (
        "# 纪要\n"
        "现场讨论了未提及的外部模块 [H99] 以及正常待办 [H1]。\n"
    )
    out_hallucinated = apply_memory_citations(body_hallucinated, ctx)
    expect("[H99]" not in out_hallucinated and "[H1]" not in out_hallucinated, "TC-H-05: [H99] 与 [H1] 都被删除", out_hallucinated)
    expect("(#memory-" not in out_hallucinated, "TC-H-05: 代号本身不产生溯源链接", out_hallucinated)

    # 6. 圆括号与中文括号里的代号同样删除
    body_flexible = (
        "# 纪要\n"
        "接口已完成联调 (H1)，Token策略已对齐 【h2】。\n"
    )
    out_flexible = apply_memory_citations(body_flexible, ctx)
    expect("(H1)" not in out_flexible and "【h2】" not in out_flexible and "【H2】" not in out_flexible, "TC-H-06: (H1) 与 【h2】 被删除", out_flexible)
    expect("(#memory-2)" in out_flexible, "TC-H-06: Token 字面仍可挂上第二条", out_flexible)
    expect(out_flexible.count("(#memory-") == 1, "TC-H-06: 没有 Token 以外的代号链接", out_flexible)

    # 7. HTML 渲染：字面挂载后仍是双栏 review HTML
    html = memory_review_html(out, title="网关会议纪要")
    expect('class="ck-cite-entity"' in html, "TC-H-07: HTML 生成带高亮实体 ck-cite-entity", html[:500])
    expect('class="ck-ev ck-mem-card"' in html, "TC-H-07: HTML 生成右侧卡片 ck-mem-card", html[:500])
    expect('class="ck-ledger"' in html or '状态演进' in html, "TC-H-07: HTML 生成状态演进看板", html[:500])

    # 8. 句子里夹了代号也不走代号通道；没写到的条目不硬挂
    body_hybrid = (
        "# 纪要\n"
        "现场确认网关鉴权接口已全量完成联调 [H1]。\n"
        "关于下周排期，团队将再开一次会。\n"
    )
    out_hybrid = apply_memory_citations(body_hybrid, ctx)
    expect("[H1]" not in out_hybrid, "TC-H-08: 正文代号被删除", out_hybrid)
    expect("(#memory-1)" in out_hybrid, "TC-H-08: 网关鉴权接口按字面挂上", out_hybrid)
    expect("(#memory-2)" not in out_hybrid, "TC-H-08: 未讨论的 Token 条目不硬挂", out_hybrid)
