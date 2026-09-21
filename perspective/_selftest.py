"""perspective 零 LLM 自测：偏好指令块（只调顺序与详略、不落性格原文）。

用法::

    python -m perspective._selftest
"""
from __future__ import annotations

import sys

from .preferences import BLOCK_TITLE, PREFERENCE_LINES, build_preference_block

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


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
        check(f"{label} → 不产生块（不出现空标题）", block == "", block)
    check(
        "客观视角 → 不注入个人偏好",
        build_preference_block({"perspective": "objective", "preferences": ["先写我的待办"]}) == "",
        "",
    )


def test_whitelist_mapping() -> None:
    block = build_preference_block(
        {"name": "赵衡", "preferences": ["先写我的待办和接口依赖", "整体精简一点", "风险单独写"]}
    )
    check("块头写明只调顺序与详略、不改事实", BLOCK_TITLE in block, block)
    check("待办偏好 → 映射成可执行指令", "先列「本用户命中」的待办" in block, block)
    check("精简偏好 → 映射成可执行指令", "整体精简" in block, block)
    check("风险偏好 → 映射成可执行指令", "风险与阻塞单独成段" in block, block)

    # 「口径」这类词会命中白名单 → 映射成指令，这是预期；要测"命不中"得挑真的没关键词的写法
    mapped = build_preference_block({"name": "赵衡", "preferences": ["会议纪要里请带上版本号口径"]})
    check("含关键词的偏好优先走映射（不是原样列出）",
          "关键数字与口径" in mapped and "偏好说明" not in mapped, mapped)

    free = build_preference_block({"name": "赵衡", "preferences": ["希望开头先列一下参会人名单"]})
    check(
        "命不中的偏好 → 原样列成「偏好说明」",
        "偏好说明" in free and "希望开头先列一下参会人名单" in free,
        free,
    )
    check("偏好说明也受「只调顺序与详略」约束", "只调顺序与详略" in free, free)


def test_personality_is_style_only() -> None:
    block = build_preference_block({"name": "赵衡", "personality": "务实，讨厌含糊的截止日期"})
    check("性格命中白名单 → 只出语气类指令", block.startswith(f"【{BLOCK_TITLE}】") and "语气：" in block, block)
    check(
        "性格原文不进 prompt（防被写成评价）",
        "务实，讨厌含糊的截止日期" not in block and "讨厌含糊" not in block,
        block,
    )

    unmapped = build_preference_block({"name": "赵衡", "personality": "急躁，容易发火"})
    check("性格命不中 → 整块为空（不直译成评价）", unmapped == "", unmapped)


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
    check("整块条数 ≤ 6", len(items) <= 6, str(items))
    check(
        "映射指令条数 ≤ 4（其余丢弃，不堆 prompt）",
        sum(1 for x in items if not x.startswith(("语气：", "偏好说明"))) <= 4,
        str(items),
    )

    long_note = "请" + "很长的偏好描述" * 20
    clipped = build_preference_block({"name": "赵衡", "preferences": [long_note]})
    note = next((x for x in items_of(clipped) if x.startswith("偏好说明")), "")
    check("单条偏好超长被截断（≤40 字）", 0 < len(note) <= 60, str(len(note)))

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
    check("第 4 条偏好（未命中白名单）也要读进来",
          "开头先列参会人名单" in fourth, fourth)


def test_injection_scope() -> None:
    """注入范围：只有纪要线拿偏好块（引擎侧按同一常量判断）。"""
    check(
        "注入线集合 = {minutes, minutes_styles}",
        set(PREFERENCE_LINES) == {"minutes", "minutes_styles"},
        str(sorted(PREFERENCE_LINES)),
    )
    from domain.meeting.orchestrator import MeetingAgentSystem  # noqa: F401 - 只验证可导入且条件用同一常量

    user = {"name": "赵衡", "preferences": ["先写我的待办"]}
    check("纪要线拿到非空块", bool(build_preference_block(user)), "")
    check(
        "非纪要线不入块（待办/风险线的 mode 判定与画像不参与偏好）",
        "actions" not in PREFERENCE_LINES and "risks" not in PREFERENCE_LINES,
        str(sorted(PREFERENCE_LINES)),
    )


def test_view_directive() -> None:
    """本视角纪律：装配那一轮（逐栏填充）的取舍口径，独立于渲染提示词。"""
    from .preferences import PERSONAL_VIEW_DIRECTIVE, VIEW_DIRECTIVE_TITLE

    check("块头是独立标题（正文里能一眼认出是哪条纪律）",
          PERSONAL_VIEW_DIRECTIVE.startswith(f"【{VIEW_DIRECTIVE_TITLE}】"), "")
    check("纪律管取舍不管结构：栏名与事实口径仍照模板",
          "栏名、结构与事实口径照模板不变" in PERSONAL_VIEW_DIRECTIVE, "")
    check("模板要求「客观、非人格化」时，人称与取舍以纪律为准（否则真人模式被模板按住）",
          "人称与取舍以本纪律为准" in PERSONAL_VIEW_DIRECTIVE, "")
    check("整栏与他无关时给缺省兜底，不留空栏（空栏会触发回退重写）",
          "不要留空栏" in PERSONAL_VIEW_DIRECTIVE
          and "缺省写法" in PERSONAL_VIEW_DIRECTIVE, "")
    check("纪律含硬口径：分点/表格类栏目只列他的条目（别人条目合并成一句）",
          "**分工类栏目只列他的条目**" in PERSONAL_VIEW_DIRECTIVE
          and "别人的条目一律不列" in PERSONAL_VIEW_DIRECTIVE, "")
    check("纪律不含任何人物事实（纯写作纪律，不引入可被抄进正文的名字/数字）",
          "申家坤" not in PERSONAL_VIEW_DIRECTIVE
          and "赵衡" not in PERSONAL_VIEW_DIRECTIVE, "")


def test_user_channel_block() -> None:
    """本用户称呼表：别称去噪与上限、无别称的措辞、不注入的四种情形。"""
    from .preferences import CHANNEL_TITLE, address_aliases, build_user_channel

    aliases = address_aliases(
        {
            "name": "赵衡",
            "role": "后端工程师",
            "department": "研发部",
            "name_aliases": ["小赵", "赵", "赵衡", "后端工程师", "研发部", "  ", "赵工", "小赵"],
        }
    )
    check(
        "别称去噪：单字/与姓名同值/与角色部门同值/空白/重复都丢掉",
        aliases == ["小赵", "赵工"],
        str(aliases),
    )

    many = address_aliases({"name": "赵衡", "name_aliases": [f"别称{i}" for i in range(10)]})
    check("别称条数上限 6", len(many) == 6, str(many))
    long_alias = address_aliases({"name": "赵衡", "name_aliases": ["很长很长的别称" * 5]})
    check("单条别称超长截断（≤12 字）", bool(long_alias) and len(long_alias[0]) <= 12, str(long_alias))

    plain = build_user_channel({"name": "赵衡"})
    check("块头是【本用户称呼】+ 全称", f"【{CHANNEL_TITLE}】赵衡（全称）" in plain, plain)
    check("无别称时不写「别称：」", "别称：" not in plain, plain)
    check("无别称时末句不带括号补充",
          plain.rstrip().endswith("编号不等于本用户。"), plain)

    with_alias = build_user_channel({"name": "赵衡", "name_aliases": ["小赵", "赵工"]})
    check("有别称时写在头行", "别称：小赵、赵工" in with_alias, with_alias)
    check("末句提示可用别称显式绑定编号", "除非上面的别称里显式写了它" in with_alias, with_alias)

    for label, profile in (
        ("客观视角", {"perspective": "objective", "name": "赵衡", "name_aliases": ["小赵"]}),
        ("职业模板（name 是职业通称）", {"name": "开发人员", "persona_type": "role_template"}),
        ("没有姓名", {"name": "  ", "name_aliases": ["小赵"]}),
        ("空画像", None),
    ):
        got = build_user_channel(profile)
        check(f"{label} → 不注入称呼表", got == "", got)


def test_hit_table() -> None:
    """命中表：强/弱命中、全称无边界 vs 别称要边界、编号不绑、带依据。"""
    from .hits import build_hit_table

    user = {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    understanding = {
        "speakers": [{"name": "赵衡"}, {"name": "武思华"}],
        "action_hints": [
            {
                "text": "接口联调周五前给测试",
                "owner": "赵衡",
                "timing": "周五前",
                "risk": "联调环境版本未定",
            },
            {"text": "端侧版本下发", "owner": "武思华", "timing": "下周"},
            {"text": "提单给赵工", "owner": "", "timing": ""},
        ],
        "decisions": ["现网待办拨测报错已修复"],
        "risks": ["赵衡那边的双录还没确认", "现网流量报表不稳定"],
        "open_questions": ["小赵的权限单要不要一起提"],
        "topics": [{"title": "端侧联调", "participants": ["赵衡", "武思华"]}],
    }
    table = build_hit_table(user, understanding)
    check("置信=high（有 owner/speakers 强命中）", table.confidence == "high", table.confidence)
    check("我的待办只取 owner 命中的那条",
          table.my_actions == ["接口联调周五前给测试（周五前）"], str(table.my_actions))
    check("强命中带字段路径依据",
          any(h.where == "action_hints[0].owner" and h.strength == "strong" for h in table.hits),
          str([(h.where, h.strength) for h in table.hits]))
    check("全称在文本里出现即算（无边界要求）：risks",
          any(h.where.startswith("risks[") for h in table.hits) and len(table.my_risks) == 2,
          str(table.my_risks))
    check("他的风险：条目自带 risk 也算（不必在文本里点他名）",
          table.my_risks[0] == "联调环境版本未定", str(table.my_risks))
    check("别称带边界才认：小赵的权限单",
          any("小赵" in h.matched for h in table.hits), str([(h.where, h.matched) for h in table.hits]))
    check("参与议题命中", table.my_topics == ["端侧联调"], str(table.my_topics))
    check("依据串可读（snippet==matched 时不重复括号）",
          "speakers[0].name：赵衡" in table.evidence(), str(table.evidence()))

    negative = build_hit_table(
        user,
        {
            "speakers": [{"name": "发言者1"}],
            "action_hints": [{"text": "那个小组赵工对接", "owner": "小组赵工", "timing": ""}],
            "risks": ["小组赵工那边忙"],
            "decisions": [],
            "open_questions": [],
            "topics": [],
        },
    )
    check("编号发言人不绑定 + 「小组赵工」不算他（别称要边界）",
          not negative.matched, str([(h.where, h.snippet) for h in negative.hits]))
    check("未命中时置信=none", negative.confidence == "none", negative.confidence)

    explicit = build_hit_table(
        {"name": "赵衡", "name_aliases": ["发言者1"]},
        {"speakers": [{"name": "发言者1"}], "action_hints": [], "decisions": [], "risks": [],
         "open_questions": [], "topics": []},
    )
    check("别称表里显式写了编号 → 才允许绑定", explicit.matched, str(explicit.hits))

    for label, profile in (
        ("客观", {"perspective": "objective", "name": "赵衡"}),
        ("职业模板", {"name": "开发人员", "persona_type": "role_template"}),
        ("无姓名", {"name": ""}),
    ):
        check(f"{label} → 空命中表", not build_hit_table(profile, understanding).matched, "")


def test_transcript_slice() -> None:
    """按人裁原文：他发言/被点名的段留下，别人的折叠；裁不动或裁太少就退回整篇。"""
    from .hits import slice_transcript_for_person

    t = (
        "项目会\n"
        "赵衡 00:00:01\n我们先过接口。\n"
        "武思华 00:00:10\n这个问题我来跟。\n"
        "赵衡 00:00:20\n小赵那边的权限单我提了。\n"
        "武思华 00:00:30\n好的，我明天找他要数据。\n"
        "李梦甜 00:00:40\n赵衡那边的双录还没确认。\n"
        "武思华 00:00:50\n我记一下。\n"
    )
    # 夹具很短，放宽"裁完太少"的保底阈值（真实运行是 200 字，见下面的 scarce 用例）
    out, stats = slice_transcript_for_person(
        t, ["赵衡", "小赵"], full_name="赵衡", min_keep_chars=50
    )
    check("他发言的段全留（3 段：含被别称指代的那段）", stats["kept"] == 3, str(stats))
    check("别人的段被折叠 + 省略标记带段数", stats["dropped"] == 3 and "省略 1 段" in out, out)
    check("块内提到他的也留（李梦甜那段）", "双录还没确认" in out, out)
    check("题头保留（首个发言行之前）", out.startswith("项目会"), out)

    relabel, _ = slice_transcript_for_person(
        t, ["赵衡", "小赵"], full_name="赵衡", self_label="你", min_keep_chars=50
    )
    check("self_label：他自己的块首换成「你」（原文满屏真名会把模型拽回第三人称）",
          relabel.count("你 00:") == 2, relabel[:60])
    check("self_label：别人的块首仍是真名（分工/引语要保真）",
          "李梦甜 00:00:40" in relabel, relabel)

    no_struct, st1 = slice_transcript_for_person("没有任何发言行的一段自由文本。", ["赵衡"], full_name="赵衡")
    check("没有发言行结构 → fallback（退回整篇）",
          st1["fallback"] and no_struct == "没有任何发言行的一段自由文本。", str(st1))

    scarce = "赵衡 00:00:01\n好的。\n武思华 00:00:10\n" + "我来处理这件事的细节。" * 20 + "\n"
    _, st2 = slice_transcript_for_person(scarce, ["赵衡"], full_name="赵衡", min_keep_chars=200)
    check("裁完太少 → fallback（不让正文没料）", st2["fallback"], str(st2))

    empty, st3 = slice_transcript_for_person(t, [], full_name="赵衡")
    check("没有可用称呼 → fallback 且原样返回", st3["fallback"] and empty == t, str(st3))


def test_foreign_only() -> None:
    """素材裁判断据：别人为主语、且完全没提到他 → True（真人装配轮用它裁理解条目）。"""
    from .hits import foreign_only

    addrs, others = ["赵衡", "小赵"], ["武思华", "徐玥"]
    check("点名到他 → 不是别人的（即使同时点了别人名）",
          not foreign_only("问题单由赵衡找武思华核对，中测时带上中测版本", addrs, others, full_name="赵衡"), "")
    check("别称也算提到他",
          not foreign_only("小赵那边的权限单我提了，武思华帮忙看下", addrs, others), "")
    check("别人为主语 → 裁掉",
          foreign_only("武思华明天找他们要数据，看能不能要到", addrs, others, full_name="赵衡"), "")
    check("无人称的全局事实 → 保留（数字/结论不能丢）",
          not foreign_only("长文本实测 8~9 万字不行，手头最大 40 多秒", addrs, others, full_name="赵衡"), "")
    check("空串不算", not foreign_only("", addrs, others, full_name="赵衡"), "")
    # 已知边界（刻意不改）：理解层的 key_points 是纯文本、不带 owner，"他做的事但只写了别人名"
    # 与"别人的事"在程序里无法区分 → 会被裁掉；这类条目在草稿的执行要点里有归属，靠草稿兜住。
    check("边界：他的事、但文本里只有别人名 → 按别人为主语裁（由草稿兜住）",
          foreign_only("问题单找武思华核对，中测时带上中测版本", addrs, others, full_name="赵衡"), "")


def test_skip_and_synthesize() -> None:
    """跳过判定（保守口径）+ 合成：schema 一致性与六种画像形态。"""
    from .hits import build_hit_table
    from .models import PerspectiveModeling
    from .synth import skip_reason, synthesize_perspective_profile

    # 极简画像：只有姓名/别称/角色，没给任何关注域 → agent 对它只能"标记姓名"（命中表的活）
    lean = {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    # 有关注域：挂职业底、或自写职责/关注领域 → "没点名但落在关注域"的条目只有建模能捞
    with_role = {"name": "赵衡", "name_aliases": ["小赵"], "role_template": "developer",
                 "focus_areas": ["需求、验收标准与技术实现方案"]}
    self_role = {"name": "赵衡", "name_aliases": ["小赵"], "focus_areas": ["接口契约与依赖"]}
    rich = {**lean, "responsibilities": ["接口实现与联调", "排期与阻塞上报"]}
    hit = {
        "speakers": [{"name": "赵衡"}],
        "action_hints": [{"text": "接口联调周五前给测试", "owner": "赵衡", "timing": "周五前"}],
        "decisions": [], "risks": [], "open_questions": [], "topics": [],
    }
    empty = {"speakers": [], "action_hints": [], "decisions": [], "risks": [], "open_questions": [], "topics": []}

    check("极简画像 + 命中非空 + 单线 → 跳过（命中非空）",
          skip_reason(lean, build_hit_table(lean, hit), ["minutes"]) == "命中非空", "")
    check("只跑 minutes_styles 也算单线",
          skip_reason(lean, build_hit_table(lean, hit), ["minutes", "minutes_styles"]) == "命中非空", "")
    check("极简画像 + 未命中 → 跳过（合成「本场未点到你」）",
          skip_reason(lean, build_hit_table(lean, empty), ["minutes"]) == "未命中且无关注域", "")
    check("挂职业底 + 命中非空 → 仍跑建模（保守口径：关注域只有它扫）",
          skip_reason(with_role, build_hit_table(with_role, hit), ["minutes"]) is None, "")
    check("自写关注域 + 命中非空 → 仍跑建模",
          skip_reason(self_role, build_hit_table(self_role, hit), ["minutes"]) is None, "")
    check("自写职责 + 命中非空 → 仍跑建模",
          skip_reason(rich, build_hit_table(rich, hit), ["minutes"]) is None, "")
    check("多线（含 actions）→ 不跳，交回建模",
          skip_reason(lean, build_hit_table(lean, hit), ["minutes", "actions"]) is None, "")
    check("客观/职业模板 → 交原路径判定（不是合并路径的职责）",
          skip_reason({"perspective": "objective", "name": "赵衡"},
                      build_hit_table({"perspective": "objective", "name": "赵衡"}, hit), ["minutes"]) is None,
          "")

    synthesized = synthesize_perspective_profile(rich, build_hit_table(rich, hit))
    PerspectiveModeling.validate(synthesized)  # 全字段必填：缺键会在这里炸
    check("合成结果过 schema（全字段齐、四个字符串非空）", True, "")
    check("合成：name/inferred_role 取画像",
          synthesized["name"] == "赵衡" and synthesized["inferred_role"] == "后端工程师", "")
    check("合成：attention_points = 命中条目（不含空壳发言人名）",
          synthesized["attention_points"] == ["接口联调周五前给测试"], str(synthesized["attention_points"]))
    check("合成：possible_actions 标「原文承诺」",
          synthesized["possible_actions"] == ["原文承诺：接口联调周五前给测试（周五前）"], "")
    check("合成：responsibilities = 职责 ∩ 命中",
          synthesized["responsibilities"] == ["接口实现与联调"], str(synthesized["responsibilities"]))
    check("合成：evidence 逐条带依据", bool(synthesized["evidence"]), str(synthesized["evidence"]))

    none_hit = synthesize_perspective_profile(lean, build_hit_table(lean, empty))
    PerspectiveModeling.validate(none_hit)
    check("未命中合成：明确写「本场未点到」，不给条目",
          "未点到" in none_hit["personal_summary"] and not none_hit["attention_points"], "")


def test_tolerant_field_forms() -> None:
    """画像字段容错：personality / preferences / name_aliases 都允许"单串或数组"。

    为什么容错：手写 JSON 时很容易把"一串短句"写成单字符串；旧实现会按字符迭代
    （"家坤" → ['家','坤'] 全被短于 2 字丢掉）或 str(list) 成 "['务实', …]"（脏但碰巧命中）。
    """
    from .preferences import address_aliases, as_text_list, build_preference_block

    check("as_text_list：None → 空", as_text_list(None, cap=6) == [], "")
    check("as_text_list：单字符串 → 单元素", as_text_list("家坤", cap=6) == ["家坤"], "")
    check("as_text_list：数组去空去重截断",
          as_text_list(["小赵", "  ", "小赵", "赵工"], cap=2) == ["小赵", "赵工"], "")
    check("name_aliases 单字符串不再被按字符切碎",
          address_aliases({"name": "申家坤", "name_aliases": "家坤"}) == ["家坤"], "")
    check("preferences 单字符串也认",
          "先列「本用户命中」的待办" in build_preference_block({"name": "申家坤", "preferences": "先写我负责的待办"}),
          "")

    trait_block = build_preference_block(
        {"name": "申家坤", "personality": ["务实，讨厌含糊的截止日期", "喜欢先看结论"]}
    )
    check("personality 数组：多条性格各匹配一次语气白名单",
          trait_block.count("语气：") == 2, trait_block)
    check("personality 字符串：旧写法仍有效",
          build_preference_block({"name": "申家坤", "personality": "务实"}).count("语气：") == 1, "")
    check("性格里命不中的短句被丢弃、原文不进 prompt",
          build_preference_block({"name": "申家坤", "personality": ["急躁", "喜欢先看结论"]}) == "", "")
    check("性格里的写作偏好要写进 preferences（否则按设计丢弃）",
          "先给结论" in build_preference_block({"name": "申家坤", "preferences": ["喜欢先看结论"]}), "")


def main() -> int:
    test_empty_cases()
    test_whitelist_mapping()
    test_personality_is_style_only()
    test_limits()
    test_injection_scope()
    test_view_directive()
    test_user_channel_block()
    test_hit_table()
    test_transcript_slice()
    test_foreign_only()
    test_skip_and_synthesize()
    test_tolerant_field_forms()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
