# 拆分自 test_perspective.py，覆盖：test_empty_cases, test_whitelist_mapping, test_personality_is_style_only…

"""perspective 零 LLM 自测：偏好指令块（只调顺序与详略、不落性格原文）。

用法::

    python -m tests.test_perspective
"""

from __future__ import annotations
from domains.shared.perspective.preferences import BLOCK_TITLE, PREFERENCE_LINES, build_preference_block
from tests.support.expectations import expect

def items_of(block: str) -> list[str]:
    return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]

def test_empty_cases() -> None:
    for label, user in (
        ("无画像", None),
        ("空画像", {}),
        ("只有姓名", {"name": "赵衡"}),
        ("preferences 为空", {"name": "赵衡", "preferences": [], "personality": ""}),
        ("preferences 全空白", {"name": "赵衡", "preferences": ["   ", ""]}),
    ):
        block = build_preference_block(user)
        expect(block == "", f"{label} → 不产生块（不出现空标题）", block)
    expect(build_preference_block({"perspective": "objective", "preferences": ["先写我的待办"]}) == "", "客观视角 → 不注入个人偏好", "")


def test_whitelist_mapping() -> None:
    block = build_preference_block(
        {"name": "赵衡", "preferences": ["先写我的待办和接口依赖", "整体精简一点", "风险单独写"]}
    )
    expect(BLOCK_TITLE in block, "块头写明只调顺序与详略、不改事实", block)
    expect("先列「本用户命中」的待办" in block, "待办偏好 → 映射成可执行指令", block)
    expect("整体精简" in block, "精简偏好 → 映射成可执行指令", block)
    expect("风险与阻塞单独成段" in block, "风险偏好 → 映射成可执行指令", block)

    # 「口径」这类词会命中白名单 → 映射成指令，这是预期；要测"命不中"得挑真的没关键词的写法
    mapped = build_preference_block({"name": "赵衡", "preferences": ["会议纪要里请带上版本号口径"]})
    expect("关键数字与口径" in mapped and "偏好说明" not in mapped, "含关键词的偏好优先走映射（不是原样列出）", mapped)

    free = build_preference_block({"name": "赵衡", "preferences": ["希望开头先列一下参会人名单"]})
    expect("偏好说明" in free and "希望开头先列一下参会人名单" in free, "命不中的偏好 → 原样列成「偏好说明」", free)
    expect("只调顺序与详略" in free, "偏好说明也受「只调顺序与详略」约束", free)


def test_personality_is_style_only() -> None:
    block = build_preference_block({"name": "赵衡", "personality": "务实，讨厌含糊的截止日期"})
    expect(block.startswith(f"【{BLOCK_TITLE}】") and "语气：" in block, "性格命中白名单 → 只出语气类指令", block)
    expect("务实，讨厌含糊的截止日期" not in block and "讨厌含糊" not in block, "性格原文不进 prompt（防被写成评价）", block)

    unmapped = build_preference_block({"name": "赵衡", "personality": "急躁，容易发火"})
    expect(unmapped == "", "性格命不中 → 整块为空（不直译成评价）", unmapped)


def test_limits() -> None:
    many = build_preference_block(
        {
            "name": "赵衡",
            "preferences": [
                "先写我的待办",
                "整体精简",
                "结论先行",
                "细节写全",
                "风险单独成段",
                "数字写全",
                "少写无关的",
            ],
            "personality": "务实",
        }
    )
    items = items_of(many)
    expect(len(items) <= 6, "整块条数 ≤ 6", str(items))
    expect(sum(1 for x in items if not x.startswith(("语气：", "偏好说明"))) <= 4, "映射指令条数 ≤ 4（其余丢弃，不堆 prompt）", str(items))

    long_note = "请" + "很长的偏好描述" * 20
    clipped = build_preference_block({"name": "赵衡", "preferences": [long_note]})
    note = next((x for x in items_of(clipped) if x.startswith("偏好说明")), "")
    expect(0 < len(note) <= 60, "单条偏好超长被截断（≤40 字）", str(len(note)))

    # 2026-09-21：读入上限曾误用「偏好说明 ≤3 条」，导致第 4 条起**静默丢弃**
    # （实测 data/1/user.json 的「徐玥是我的上级…」从来没进过 prompt）
    fourth = build_preference_block(
        {
            "name": "赵衡",
            "preferences": [
                "先写我的待办",
                "整体精简",
                "风险单独成段",
                "开头先列参会人名单",
            ],
        }
    )
    expect("开头先列参会人名单" in fourth, "第 4 条偏好（未命中白名单）也要读进来", fourth)


def test_injection_scope() -> None:
    """注入范围：只有纪要线拿偏好块（引擎侧按同一常量判断）。"""
    expect(set(PREFERENCE_LINES) == {"minutes", "minutes_styles"}, "注入线集合 = {minutes, minutes_styles}", str(sorted(PREFERENCE_LINES)))
    from domains.meeting.orchestrator import MeetingAgentSystem  # noqa: F401 - 只验证可导入且条件用同一常量

    user = {"name": "赵衡", "preferences": ["先写我的待办"]}
    expect(bool(build_preference_block(user)), "纪要线拿到非空块", "")
    expect("actions" not in PREFERENCE_LINES and "risks" not in PREFERENCE_LINES, "非纪要线不入块（待办/风险线的 mode 判定与画像不参与偏好）", str(sorted(PREFERENCE_LINES)))


def test_action_groups_block() -> None:
    """分栏分组骨架：把"要出现哪些组名行"变成可照抄的清单（模型只复制、不重排）。"""
    from domains.shared.perspective import render_action_groups_block
    from domains.shared.perspective.preferences import SELF_GROUP_ROW

    user = {"name": "申家坤", "name_aliases": ["家坤"]}
    understanding = {
        "action_hints": [
            {"owner": "申家坤"},
            {"owner": "武思华"},
            {"owner": "徐玥"},
            {"owner": "武思华"},
            {},
        ],
        "speakers": [{"name": "申家坤"}, {"name": "武思华"}, {"name": "徐玥"}],
    }
    block = render_action_groups_block(user, understanding)
    expect(SELF_GROUP_ROW in block, f"分组骨架：本人那一行固定 `{SELF_GROUP_ROW}`", block[:80])
    expect("「结论与决定」「行动项与分工」「待确认与风险」" in block, "分组骨架：点明末尾三栏共用（结论与决定 / 行动项与分工 / 待确认与风险）", block[:120])
    expect("**武思华**：" in block and "**徐玥**：" in block
          and block.count("**武思华**") == 1, "分组骨架：他人按待办 owner 去重各一行", block)
    expect("**家坤**：" not in block, "分组骨架：别名识别为自己，不列成他人", block)
    # 三栏共用骨架 ⇒ 结论/风险里的条目可能挂在任何一位发言人名下（不只是有待办的人），
    # 所以他人组名取 owner ∪ speakers，否则会出现"有归属却没有可用组名行"。
    union = render_action_groups_block(
        user,
        {
            "action_hints": [{"owner": "武思华"}],
            "speakers": [{"name": "武思华"}, {"name": "徐玥"}],
        },
    )
    expect("**武思华**：" in union and "**徐玥**：" in union and union.count("**武思华**") == 1, "分组骨架：他人组名取 owner ∪ 与会发言人（待办之外的人也有组名行可用）", union)
    fallback = render_action_groups_block(
        user, {"action_hints": [], "speakers": [{"name": "家坤"}, {"name": "武思华"}]}
    )
    expect("**武思华**：" in fallback and "**家坤**：" not in fallback, "分组骨架：待办线索被裁掉时退回与会发言人（别名仍算自己）", fallback)
    expect(render_action_groups_block({}, understanding) == "", "分组骨架：无姓名（客观/无档案）不注入", "")
    # 当显式指定 focus_person 时，过滤掉无关发言人
    user_with_focus = {"name": "申家坤", "focus_person": ["徐玥"]}
    focused_block = render_action_groups_block(user_with_focus, understanding)
    expect("**与我相关**：" in focused_block and "**徐玥**：" in focused_block and "**武思华**：" not in focused_block, "分组骨架：显式 focus_person 时仅保留重点关注人，彻底过滤外围人员", focused_block)


def test_speaker_attribution() -> None:
    """发言行切块 + 条目归属判定（A2：把「这条是谁的」变成可照抄的事实，不让模型推理）。"""
    from domains.shared.perspective import attribute_to_speaker, speaker_blocks

    transcript = (
        "申家坤 00:00:05\n今天过长文本线。\n"
        "徐玥 00:00:20\n我这边还有一个风险：合规材料还没批下来，审批拖着会影响你的报告交付。\n"
        "武思华 00:00:45\n我的风险是接口权限没批，可能影响我这边的测试进度。\n"
    )
    blocks = speaker_blocks(transcript)
    expect([b[0] for b in blocks] == ["申家坤", "徐玥", "武思华"], "发言行切块：按「姓名 HH:MM:SS」切、题头不入块", str([b[0] for b in blocks]))
    item_risk = "合规材料还没批下来，审批拖着会影响你的报告交付"
    got = attribute_to_speaker(
        transcript, [item_risk, "930 窗口期不多了"],
        self_addresses=["申家坤", "家坤"], self_name="申家坤",
    )
    expect(got.get(item_risk) == "徐玥" and "930 窗口期不多了" not in got, "归属判定：原文能对上的给出发言人、对不上的不给", str(got))
    mine = attribute_to_speaker(
        transcript, ["今天过长文本线"],
        self_addresses=["申家坤", "家坤"], self_name="申家坤",
    )
    expect(mine.get("今天过长文本线") == "申家坤", "归属判定：块首是他的别称时归一成全称", str(mine))


def test_user_channel_block() -> None:
    """本用户称呼表：别称去噪与上限、无别称的措辞、不注入的四种情形。"""
    from domains.shared.perspective.preferences import CHANNEL_TITLE, address_aliases, build_user_channel

    aliases = address_aliases(
        {
            "name": "赵衡",
            "role": "后端工程师",
            "department": "研发部",
            "name_aliases": ["小赵", "赵", "赵衡", "后端工程师", "研发部", "  ", "赵工", "小赵"],
        }
    )
    expect(aliases == ["小赵", "赵工"], "别称去噪：单字/与姓名同值/与角色部门同值/空白/重复都丢掉", str(aliases))

    many = address_aliases({"name": "赵衡", "name_aliases": [f"别称{i}" for i in range(10)]})
    expect(len(many) == 6, "别称条数上限 6", str(many))
    long_alias = address_aliases({"name": "赵衡", "name_aliases": ["很长很长的别称" * 5]})
    expect(bool(long_alias) and len(long_alias[0]) <= 12, "单条别称超长截断（≤12 字）", str(long_alias))

    plain = build_user_channel({"name": "赵衡"})
    expect(f"【{CHANNEL_TITLE}】赵衡（全称）" in plain, "块头是【本用户称呼】+ 全称", plain)
    expect("别称：" not in plain, "无别称时不写「别称：」", plain)
    expect(plain.rstrip().endswith("编号不等于本用户。"), "无别称时末句不带括号补充", plain)

    with_alias = build_user_channel({"name": "赵衡", "name_aliases": ["小赵", "赵工"]})
    expect("别称：小赵、赵工" in with_alias, "有别称时写在头行", with_alias)
    expect("除非上面的别称里显式写了它" in with_alias, "末句提示可用别称显式绑定编号", with_alias)

    for label, profile in (
        ("客观视角", {"perspective": "objective", "name": "赵衡", "name_aliases": ["小赵"]}),
        ("职业模板（name 是职业通称）", {"name": "开发人员", "persona_type": "role_template"}),
        ("没有姓名", {"name": "  ", "name_aliases": ["小赵"]}),
        ("空画像", None),
    ):
        got = build_user_channel(profile)
        expect(got == "", f"{label} → 不注入称呼表", got)
