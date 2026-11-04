# 拆分自原大文件，保留：test_personal_perspective_modeling_pruning_and_projection, test_unified_meeting_tree_perspective_modeling, test_personal_perspective_dual_track…

"""perspective 零 LLM 自测：偏好指令块（只调顺序与详略、不落性格原文）。

用法::

    python -m tests.test_perspective
"""

from __future__ import annotations
from domains.shared.perspective.preferences import BLOCK_TITLE, PREFERENCE_LINES, build_preference_block
from tests.support.expectations import expect

def items_of(block: str) -> list[str]:
    return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]

def test_personal_perspective_modeling_pruning_and_projection() -> None:
    from domains.shared.perspective.synth import synthesize_perspective_profile
    from domains.shared.perspective.hits import build_hit_table
    from core.templates.router._placeholder import _prune_context_for_column, project_column_from_draft

    # 1. 建模层产出验证：高管任务简报范式，彻底消除系统内部日志腔
    table = build_hit_table({"name": "申家坤"}, {"decisions": ["申家坤负责压测报告"]})
    profile = synthesize_perspective_profile({"name": "申家坤"}, table)
    summary = profile["personal_summary"]
    expect("核心承接目标与事项" in summary and "按既定节点推进交付" in summary, "建模层产出：承接目标事实块升级", summary)
    expect("本场与申家坤直接相关" not in summary, "建模层产出：彻底消灭内部机器日志腔", summary)

    # 2. 栏目靶向瘦身验证（Targeted Column Context Pruning）
    context = (
        "视角模式：personal\n"
        "objective_perspective：False\n\n"
        "用户画像：\n"
        '{"name": "申家坤", "focus_thing": ["demo落地", "模型压测"], "focus_person": ["张工"]}\n\n'
        "会议理解：\n"
        '{"topics": [{"topic": "demo落地方案", "key_points": ["完成第一轮测试"], "discussion": "张工和申家坤讨论了很久..."}, {"topic": "财务报销规范", "key_points": ["发票规定"], "discussion": "财务详细汇报了发票流程..."}], "decisions": ["拍板demo落地本周上线"], "action_hints": ["申家坤完成压测报告"], "risks": ["压测显存超限"]}\n\n'
        "已审核用户视角：\n"
        '{"personal_summary": "核心承接目标与事项：完成压测。"}\n\n'
        "会议原文（真人模式·已按人裁剪）：\n"
        "张工：明天把测试环境搞好。\n"
        "申家坤：我周五前出压测报告。\n"
        "财务：报销流程必须在每月25日前提交。\n\n"
        "已批准纪要草稿：\n"
        '{"headline": "技术对齐会", "executive_summary": ["本场讨论了demo落地。"], "key_decisions": ["拍板demo落地本周上线"], "personally_relevant_points": ["**与我相关**：", "完成demo落地压测（周五前 ｜ 报告 ｜ P99<50ms）", "**协同输入**：", "**张工**：明天就绪测试环境（明天下午）"], "risks_and_blockers": ["**与我相关**：", "【阻塞】显存不足待协调机器"]}\n\n'
        "纪要审核结论：\n"
        '{"decision": "approve"}\n\n'
        "【本用户命中】\n"
        "命中申家坤 2 处"
    )

    # 待办栏瘦身：切除长篇会议原文，保留 action_hints 与 decisions
    act_pruned = _prune_context_for_column(context, "", title="相关行动", hint="")
    expect("会议原文" not in act_pruned, "待办栏瘦身：切除会议原文", act_pruned[:100])
    expect("action_hints" in act_pruned and "decisions" in act_pruned, "待办栏瘦身：保留action_hints与decisions", act_pruned[:100])
    expect("财务详细汇报" not in act_pruned, "待办栏瘦身：剔除长篇topics讨论", act_pruned)

    # 业务决策栏瘦身：仅注入与 focus_thing 相关议题切片
    biz_pruned = _prune_context_for_column(context, "", title="重点关注与业务进展", hint="")
    expect("张工和申家坤讨论了很久" in biz_pruned, "业务决策栏瘦身：保留focus_thing相关讨论", biz_pruned)
    expect("财务详细汇报了发票流程" not in biz_pruned, "业务决策栏瘦身：剔除无关议题讨论", biz_pruned)

    # 4. 草稿直出快线验证（Direct Projection）
    proj_act = project_column_from_draft(context, "personal_minutes.md", title="相关行动", hint="")
    expect(bool(proj_act), "草稿直出：行动项直出成功", str(proj_act))
    expect("**本人相关**：" in (proj_act or "") and "- **完成demo落地压测**（周五前 ｜ 报告 ｜ P99<50ms）" in (proj_act or ""), "草稿直出：格式标准化为看板与清单", str(proj_act))
    expect("**重点协同**：" in (proj_act or "") and "- **张工**：明天就绪测试环境（明天下午）" in (proj_act or ""), "草稿直出：协同输入分组保留", str(proj_act))

    proj_risk = project_column_from_draft(context, "personal_minutes.md", title="相关风险", hint="")
    expect(bool(proj_risk) and "**本人相关**：" in (proj_risk or ""), "草稿直出：风险卡点直出成功", str(proj_risk))

    # 非个人模式平滑回退
    obj_context = context.replace("视角模式：personal", "视角模式：objective")
    proj_obj = project_column_from_draft(obj_context, "general_minutes.md", title="行动项与分工", hint="")
    expect(proj_obj is None, "草稿直出：客观模式平滑回退None走LLM", str(proj_obj))


def test_unified_meeting_tree_perspective_modeling() -> None:
    """测试统一议题树 (UnifiedMeetingTree) 原生结构在个人视角建模中的全流程：
    1. build_hit_table 深度扫描 decisions / key_metrics / actions / risks / participants / debate
    2. synthesize_perspective_profile 结构化投影与关键指标填充
    3. _prune_context_for_column 三档梯次剪裁 (Tier 1 深潜, Tier 2 协同, Tier 3 大局高密结论)
    4. 待办与风险栏上下文剪裁保留 topics 内原生 actions 与 risks
    5. project_column_from_draft 方案 A 复选框格式对齐
    """
    import json
    from domains.shared.perspective.hits import build_hit_table
    from domains.shared.perspective.synth import synthesize_perspective_profile
    from core.templates.router._placeholder import _prune_context_for_column, project_column_from_draft

    user = {
        "name": "申家坤",
        "name_aliases": ["家坤"],
        "role": "算法工程师",
        "focus_thing": ["demo落地"],
        "focus_person": ["徐玥"],
        "preferences": ["先写我负责的待办", "关键数字与口径优先保留"],
    }
    understanding = {
        "topics": [
            {
                "title": "demo落地推进与性能压测",
                "module": "算法工程",
                "summary": "推进demo落地与显存优化",
                "decisions": ["申家坤周四前输出压测报告"],
                "key_metrics": ["P99≤50ms", "显存≤4.5GB"],
                "context_and_debate": "张工与申家坤讨论了显存限制",
                "actions": [
                    {"owner": "申家坤", "text": "完成demo落地模型压测", "timing": "周四18:00前"}
                ],
                "risks": [
                    {"owner": "申家坤", "text": "压测机器GPU显存受限", "level": "阻塞"}
                ],
                "participants": ["申家坤", "徐玥", "张工"]
            },
            {
                "title": "风控引擎沙箱对接",
                "module": "安全合规",
                "summary": "风控接口联调",
                "decisions": ["徐玥确认周五下班前提供沙箱测试用例"],
                "actions": [
                    {"owner": "徐玥", "text": "提供风控引擎测试用例", "timing": "周五前"}
                ],
                "participants": ["徐玥"]
            },
            {
                "title": "市场部首批公测推广",
                "module": "市场运营",
                "summary": "下月启动首批公测",
                "decisions": ["确认下月启动首批公测"],
                "actions": [],
                "participants": ["市场"]
            }
        ]
    }

    # 1. 深度扫描验证
    table = build_hit_table(user, understanding)
    expect(any("topics[0].actions[0].owner" in h.where for h in table.hits), "统一议题树命中：命中本人待办", str(table.hits))
    expect(any("topics[0].participants" in h.where for h in table.hits), "统一议题树命中：命中参会人", str(table.hits))
    expect(any("demo落地" in s for s in table.focus_thing_mentions), "统一议题树命中：命中focus_thing", str(table.focus_thing_mentions))
    expect(any("徐玥" in s for s in table.focus_person_statements), "统一议题树命中：命中focus_person", str(table.focus_person_statements))

    # 2. 合成 Profile 验证
    profile = synthesize_perspective_profile(user, table)
    expect("demo落地推进与性能压测" in profile.get("relevant_topics", []), "Profile合成：提取相关议题", str(profile.get("relevant_topics")))
    expect(any("显存" in c for c in profile.get("concerns", [])), "Profile合成：提取本人风险关注点", str(profile.get("concerns")))
    expect(any("输出压测报告" in c or "demo落地" in c for c in profile.get("attention_points", [])), "Profile合成：提取关注要点", str(profile.get("attention_points")))

    # 3. 三档梯次剪裁验证
    context = (
        "视角模式：personal\n"
        "objective_perspective：False\n\n"
        f"用户画像：\n{json.dumps(user, ensure_ascii=False)}\n\n"
        f"会议理解：\n{json.dumps(understanding, ensure_ascii=False)}\n\n"
        f"已审核用户视角：\n{json.dumps(profile, ensure_ascii=False)}\n\n"
        "已批准纪要草稿：\n"
        '{"headline": "技术对齐会", "executive_summary": ["本场讨论了demo落地。"], "key_decisions": ["拍板周四前输出压测报告"], "personally_relevant_points": ["### 与我相关行动项", "- [ ] **完成demo落地模型压测**：于周四18:00前输出报告，确保P99≤50ms", "### 关注人定调与协同输入", "- [ ] **徐玥**：于周五前提供沙箱测试用例"], "risks_and_blockers": ["### 本人关注的风险与阻碍", "- [ ] **【阻塞】压测机器GPU显存受限**：当前单卡无法模拟50并发", "### 待确认事项汇总", "- 商品版本测试报告待确认"]}\n\n'
        "纪要审核结论：\n"
        '{"decision": "approve"}\n'
    )

    # 业务进展栏 (决策/进展)
    pruned_biz = _prune_context_for_column(context, "", title="业务进展", hint="")
    expect("张工与申家坤讨论了显存限制" in pruned_biz and "P99≤50ms" in pruned_biz, "三档剪裁：Tier 1 保留讨论与关键量化指标", pruned_biz)
    expect("徐玥确认周五下班前提供沙箱测试用例" in pruned_biz, "三档剪裁：Tier 2 保留关注人决议", pruned_biz)
    expect("市场部首批公测推广" in pruned_biz and "确认下月启动首批公测" in pruned_biz, "三档剪裁：Tier 3 外围议题仅保留标题与决议", pruned_biz)

    # 会议概况栏（宏观背景剪裁）
    pruned_ov = _prune_context_for_column(context, "", title="会议概况", hint="")
    expect("张工与申家坤讨论了显存限制" not in pruned_ov and "本场讨论了demo落地" in pruned_ov, "会议概况剪裁：精简topics讨论细节", pruned_ov)

    # 行动项栏（相关行动）
    pruned_act = _prune_context_for_column(context, "", title="相关行动", hint="")
    expect("完成demo落地模型压测" in pruned_act and "提供风控引擎测试用例" in pruned_act, "待办栏剪裁：保留topics原生actions", pruned_act)

    # 4. 方案 A 草稿直出验证
    proj_act = project_column_from_draft(context, "personal_minutes.md", title="相关行动", hint="")
    expect("**本人相关**：" in (proj_act or "") and "**重点协同**：" in (proj_act or ""), "草稿直出：组名规范为本人相关与重点协同", str(proj_act))
    expect("- [ ] **完成demo落地模型压测**" in (proj_act or ""), "草稿直出：自然句式流保留复选框", str(proj_act))
    expect("**徐玥**" in (proj_act or "") and "沙箱测试用例" in (proj_act or ""), "草稿直出：关注人输入保留", str(proj_act))

    proj_risk = project_column_from_draft(context, "personal_minutes.md", title="相关风险", hint="")
    expect("**本人相关**：" in (proj_risk or ""), "草稿直出：风险组名规范为本人相关", str(proj_risk))
    expect("- [ ] **压测机器GPU显存受限**" in (proj_risk or "") and "【阻塞】" not in (proj_risk or "") and "待确认" not in (proj_risk or ""), "草稿直出：风险剔除级别标签且剔除待确认事项", str(proj_risk))


def test_personal_perspective_dual_track() -> None:
    """个人视角纪要双轨制落地验证（借鉴 agenda_minutes 架构设计）。

    涵盖 personal_minutes_dual_track_guide.md 规范的全部核心用例：
    - TC-TRK-01: 经典理想场景（Track A 强人名锚定）
    - TC-TRK-02: 全场匿名+点名应答握手（Track B 正文穿透反向声纹绑定）
    - TC-TRK-03: 全场匿名+自报家门（Track B 正文自报家门绑定与代号清洗）
    - TC-TRK-04: 全场匿名+无点名纯阵地（Track B 业务标的/阵地共振）
    - TC-TRK-05: 格式完全崩塌（极端容错回退 fallback=True）
    - Channel 模式感知：Track B 理解层提示词注入
    - 终稿公文化包装：清洗匿名编号与第一人称冗余代词
    """
    from domains.shared.perspective import (
        detect_personal_perspective_track,
        resolve_anonymous_speakers_by_handshake,
        slice_transcript_for_person,
        build_user_channel,
        is_anonymous_speaker,
        DialogueBlock,
    )
    user = {
        "name": "赵衡",
        "name_aliases": ["小赵", "赵工"],
        "focus_thing": ["支付网关", "字典表"],
        "focus_person": ["徐玥"],
    }

    # 1. 匿名代号探测函数验证
    expect(is_anonymous_speaker("发言人 1"), "匿名探测：发言人 1 是匿名", "")
    expect(is_anonymous_speaker("发言者 A"), "匿名探测：发言者 A 是匿名", "")
    expect(is_anonymous_speaker("Speaker 3"), "匿名探测：Speaker 3 是匿名", "")
    expect(is_anonymous_speaker("现场发言人"), "匿名探测：现场发言人 是匿名", "")
    expect(not is_anonymous_speaker("赵衡"), "匿名探测：赵衡 不是匿名", "")
    expect(not is_anonymous_speaker("张总"), "匿名探测：张总 不是匿名", "")

    # TC-TRK-01: 经典理想场景（Track A 强人名锚定）
    t_trk_01 = (
        "赵衡 00:00:01\n我们先过一下网关接口。\n"
        "张总 00:00:15\n好的，周五前务必封板。\n"
        "李工 00:00:30\n测试用例已准备完毕。\n"
    )
    track_01 = detect_personal_perspective_track(t_trk_01, addresses=["赵衡", "小赵", "赵工"], user_profile=user)
    expect(track_01 == "NAMED", "TC-TRK-01: 经典理想场景命中 Track A (NAMED)", track_01)
    sliced_01, stats_01 = slice_transcript_for_person(
        t_trk_01,
        ["赵衡", "小赵", "赵工"],
        full_name="赵衡",
        self_label="你",
        user_profile=user,
        min_keep_chars=20,
    )
    expect(not stats_01["fallback"] and stats_01.get("track") == "NAMED", "TC-TRK-01: Track A 执行成功且无 fallback", str(stats_01))
    expect("你 00:00:01" in sliced_01, "TC-TRK-01: 本人块首重标为「你」", sliced_01)

    # TC-TRK-02: 全场匿名+点名应答握手（Track B 正文穿透反向声纹绑定）
    t_trk_02 = (
        "发言人 1 00:00:01\n赵工你汇报一下网关改造的进展。\n"
        "发言人 2 00:00:10\n网关已提测，周五18点前完成接口封板。\n"
        "发言人 4 00:00:20\n支付网关联调已完成，回归通过。\n"
        "发言人 3 00:00:30\n下周团建活动安排在周六，大家按时提交报名表。\n"
    )
    track_02 = detect_personal_perspective_track(t_trk_02, addresses=["赵衡", "小赵", "赵工"], user_profile=user)
    expect(track_02 == "CONTENT", "TC-TRK-02: 全场匿名代号命中 Track B (CONTENT)", track_02)
    sliced_02, stats_02 = slice_transcript_for_person(
        t_trk_02,
        ["赵衡", "小赵", "赵工"],
        full_name="赵衡",
        self_label="你",
        user_profile=user,
        focus_persons=user["focus_person"],
        focus_things=user["focus_thing"],
        min_keep_chars=20,
    )
    expect(not stats_02["fallback"] and stats_02.get("track") == "CONTENT", "TC-TRK-02: Track B 成功切片", str(stats_02))
    expect("你 00:00:10" in sliced_02 and "网关已提测" in sliced_02, "TC-TRK-02: 发言人2 通过时序握手反向绑定为本人并标为「你」", sliced_02)
    expect("发言人 1 00:00:01" in sliced_02 and "赵工你汇报一下" in sliced_02, "TC-TRK-02: 发言人1 点名发言块作为协同上下文予以保留", sliced_02)
    expect("团建" not in sliced_02 and "省略 1 段" in sliced_02, "TC-TRK-02: 发言人3 无关团建发言被成功折叠剔除", sliced_02)

    # TC-TRK-03: 全场匿名+自报家门（Track B 正文自报家门绑定与代号清洗）
    t_trk_03 = (
        "Speaker 3 00:00:05\n我是赵衡，我说两句。支付网关核心模块已全量上线。\n"
        "Speaker 1 00:00:25\n收到，辛苦小赵。\n"
        "Speaker 2 00:00:50\n另外行政部门下周升级门禁系统，记得带工卡。\n"
    )
    track_03 = detect_personal_perspective_track(t_trk_03, addresses=["赵衡", "小赵", "赵工"], user_profile=user)
    expect(track_03 == "CONTENT", "TC-TRK-03: 命中 Track B (CONTENT)", track_03)
    sliced_03, stats_03 = slice_transcript_for_person(
        t_trk_03,
        ["赵衡", "小赵", "赵工"],
        full_name="赵衡",
        self_label="你",
        user_profile=user,
        min_keep_chars=20,
    )
    expect("你 00:00:05" in sliced_03 and "我是赵衡" in sliced_03, "TC-TRK-03: 自报家门成功绑定并重标为「你」", sliced_03)
    expect("Speaker 3" not in sliced_03, "TC-TRK-03: 原文 Speaker 3 代号已被清洗替换", sliced_03)
    expect("收到，辛苦小赵" in sliced_03 and "门禁系统" not in sliced_03, "TC-TRK-03: 紧邻协同确认留存，无关门禁通知被剔除", sliced_03)

    # TC-TRK-04: 全场匿名+无点名纯阵地（Track B 业务标的/阵地共振）
    t_trk_04 = (
        "发言人 1 00:00:01\n支付网关本周进行高并发压测，确保核心链路高可用。\n"
        "发言人 2 00:00:20\n字典表重构工作已完成初审，周三同步DDL。\n"
        "发言人 4 00:00:40\n园区食堂下月增加夜宵供应，注意用餐纪律。\n"
    )
    track_04 = detect_personal_perspective_track(t_trk_04, addresses=["赵衡", "小赵", "赵工"], user_profile=user)
    expect(track_04 == "CONTENT", "TC-TRK-04: 无人名全场匿名命中 Track B", track_04)
    sliced_04, stats_04 = slice_transcript_for_person(
        t_trk_04,
        ["赵衡", "小赵", "赵工"],
        full_name="赵衡",
        self_label="你",
        focus_things=["支付网关", "字典表"],
        user_profile=user,
        min_keep_chars=20,
    )
    expect("支付网关本周进行高并发压测" in sliced_04 and "字典表重构工作" in sliced_04, "TC-TRK-04: 标的共振保留支付网关与字典表", sliced_04)
    expect("食堂" not in sliced_04 and "省略 1 段" in sliced_04, "TC-TRK-04: 无关食堂讨论被剔除", sliced_04)

    # TC-TRK-05: 格式完全崩塌（极端容错回退 fallback=True）
    t_trk_05 = "这是一段没有任何发言行结构也没有冒号的纯散文，记录了技术会议的若干讨论内容，模型不应报错崩盘。"
    sliced_05, stats_05 = slice_transcript_for_person(
        t_trk_05,
        ["赵衡"],
        full_name="赵衡",
        user_profile=user,
    )
    expect(stats_05["fallback"] and sliced_05 == t_trk_05, "TC-TRK-05: 格式完全崩塌触发 fallback=True 且安全回退", str(stats_05))

    # 验证 build_user_channel 在 Track B 模式下的感知
    channel_track_b = build_user_channel(user, track="CONTENT")
    expect("Track B 模式" in channel_track_b and "我是赵衡" in channel_track_b, "Channel Track B: 包含代号指引与正文解密规则", channel_track_b)
    expect("严禁凭空将所有发言人1机械推断为赵衡" in channel_track_b, "Channel Track B: 严禁凭空推断发言人1", channel_track_b)
