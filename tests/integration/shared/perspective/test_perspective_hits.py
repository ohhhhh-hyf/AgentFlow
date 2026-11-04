# 拆分自 test_perspective.py，覆盖：test_hit_table, test_transcript_slice, test_foreign_only…

"""perspective 零 LLM 自测：偏好指令块（只调顺序与详略、不落性格原文）。

用法::

    python -m tests.test_perspective
"""

from __future__ import annotations
from domains.shared.perspective.preferences import BLOCK_TITLE, PREFERENCE_LINES, build_preference_block
from tests.support.expectations import expect
import pytest

pytestmark = pytest.mark.integration

def items_of(block: str) -> list[str]:
    return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]

def test_hit_table() -> None:
    """命中表：强/弱命中、全称无边界 vs 别称要边界、编号不绑、带依据。"""
    from domains.shared.perspective.hits import build_hit_table

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
    expect(table.confidence == "high", "置信=high（有 owner/speakers 强命中）", table.confidence)
    expect(table.my_actions == ["接口联调周五前给测试（周五前）"], "我的待办只取 owner 命中的那条", str(table.my_actions))
    expect(any(h.where == "action_hints[0].owner" and h.strength == "strong" for h in table.hits), "强命中带字段路径依据", str([(h.where, h.strength) for h in table.hits]))
    expect(any(h.where.startswith("risks[") for h in table.hits) and len(table.my_risks) == 2, "全称在文本里出现即算（无边界要求）：risks", str(table.my_risks))
    expect(table.my_risks[0] == "联调环境版本未定", "他的风险：条目自带 risk 也算（不必在文本里点他名）", str(table.my_risks))
    expect(any("小赵" in h.matched for h in table.hits), "别称带边界才认：小赵的权限单", str([(h.where, h.matched) for h in table.hits]))
    expect(table.my_topics == ["端侧联调"], "参与议题命中", str(table.my_topics))
    expect("speakers[0].name：赵衡" in table.evidence(), "依据串可读（snippet==matched 时不重复括号）", str(table.evidence()))

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
    expect(not negative.matched, "编号发言人不绑定 + 「小组赵工」不算他（别称要边界）", str([(h.where, h.snippet) for h in negative.hits]))
    expect(negative.confidence == "none", "未命中时置信=none", negative.confidence)

    explicit = build_hit_table(
        {"name": "赵衡", "name_aliases": ["发言者1"]},
        {"speakers": [{"name": "发言者1"}], "action_hints": [], "decisions": [], "risks": [],
         "open_questions": [], "topics": []},
    )
    expect(explicit.matched, "别称表里显式写了编号 → 才允许绑定", str(explicit.hits))

    for label, profile in (
        ("客观", {"perspective": "objective", "name": "赵衡"}),
        ("职业模板", {"name": "开发人员", "persona_type": "role_template"}),
        ("无姓名", {"name": ""}),
    ):
        expect(not build_hit_table(profile, understanding).matched, f"{label} → 空命中表", "")


def test_transcript_slice() -> None:
    """按人裁原文：他发言/被点名的段留下，别人的折叠；裁不动或裁太少就退回整篇。"""
    from domains.shared.perspective.hits import slice_transcript_for_person

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
    expect(stats["kept"] == 3, "他发言的段全留（3 段：含被别称指代的那段）", str(stats))
    expect(stats["dropped"] == 3 and "省略 1 段" in out, "别人的段被折叠 + 省略标记带段数", out)
    expect("双录还没确认" in out, "块内提到他的也留（李梦甜那段）", out)
    expect(out.startswith("项目会"), "题头保留（首个发言行之前）", out)

    relabel, _ = slice_transcript_for_person(
        t, ["赵衡", "小赵"], full_name="赵衡", self_label="你", min_keep_chars=50
    )
    expect(relabel.count("你 00:") == 2, "self_label：他自己的块首换成「你」（原文满屏真名会把模型拽回第三人称）", relabel[:60])
    expect("李梦甜 00:00:40" in relabel, "self_label：别人的块首仍是真名（分工/引语要保真）", relabel)

    no_struct, st1 = slice_transcript_for_person("没有任何发言行的一段自由文本。", ["赵衡"], full_name="赵衡")
    expect(st1["fallback"] and no_struct == "没有任何发言行的一段自由文本。", "没有发言行结构 → fallback（退回整篇）", str(st1))

    scarce = "赵衡 00:00:01\n好的。\n武思华 00:00:10\n" + "我来处理这件事的细节。" * 20 + "\n"
    _, st2 = slice_transcript_for_person(scarce, ["赵衡"], full_name="赵衡", min_keep_chars=200)
    expect(st2["fallback"], "裁完太少 → fallback（不让正文没料）", str(st2))

    empty, st3 = slice_transcript_for_person(t, [], full_name="赵衡")
    expect(st3["fallback"] and empty == t, "没有可用称呼 → fallback 且原样返回", str(st3))


def test_foreign_only() -> None:
    """素材裁判断据：别人为主语、且完全没提到他 → True（真人装配轮用它裁理解条目）。"""
    from domains.shared.perspective.hits import foreign_only

    addrs, others = ["赵衡", "小赵"], ["武思华", "徐玥"]
    expect(not foreign_only("问题单由赵衡找武思华核对，中测时带上中测版本", addrs, others, full_name="赵衡"), "点名到他 → 不是别人的（即使同时点了别人名）", "")
    expect(not foreign_only("小赵那边的权限单我提了，武思华帮忙看下", addrs, others), "别称也算提到他", "")
    expect(foreign_only("武思华明天找他们要数据，看能不能要到", addrs, others, full_name="赵衡"), "别人为主语 → 裁掉", "")
    expect(not foreign_only("长文本实测 8~9 万字不行，手头最大 40 多秒", addrs, others, full_name="赵衡"), "无人称的全局事实 → 保留（数字/结论不能丢）", "")
    expect(not foreign_only("", addrs, others, full_name="赵衡"), "空串不算", "")
    # 已知边界（刻意不改）：理解层的 key_points 是纯文本、不带 owner，"他做的事但只写了别人名"
    # 与"别人的事"在程序里无法区分 → 会被裁掉；这类条目在草稿的执行要点里有归属，靠草稿兜住。
    expect(foreign_only("问题单找武思华核对，中测时带上中测版本", addrs, others, full_name="赵衡"), "边界：他的事、但文本里只有别人名 → 按别人为主语裁（由草稿兜住）", "")


def test_skip_and_synthesize() -> None:
    """跳过判定（保守口径）+ 合成：schema 一致性与六种画像形态。"""
    from domains.shared.perspective.hits import build_hit_table
    from domains.shared.perspective.models import PerspectiveModeling
    from domains.shared.perspective.synth import skip_reason, synthesize_perspective_profile

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

    expect(skip_reason(lean, build_hit_table(lean, hit), ["minutes"]) == "命中非空", "极简画像 + 命中非空 + 单线 → 跳过（命中非空）", "")
    expect(skip_reason(lean, build_hit_table(lean, hit), ["minutes", "minutes_styles"]) == "命中非空", "只跑 minutes_styles 也算单线", "")
    expect(skip_reason(lean, build_hit_table(lean, empty), ["minutes"]) == "未命中且无关注域", "极简画像 + 未命中 → 跳过（合成「本场未点到你」）", "")
    expect(skip_reason(with_role, build_hit_table(with_role, hit), ["minutes"]) is None, "挂职业底 + 命中非空 → 仍跑建模（保守口径：关注域只有它扫）", "")
    expect(skip_reason(self_role, build_hit_table(self_role, hit), ["minutes"]) is None, "自写关注域 + 命中非空 → 仍跑建模", "")
    expect(skip_reason(rich, build_hit_table(rich, hit), ["minutes"]) is None, "自写职责 + 命中非空 → 仍跑建模", "")
    expect(skip_reason(lean, build_hit_table(lean, hit), ["minutes", "actions"]) is None, "多线（含 actions）→ 不跳，交回建模", "")
    expect(skip_reason({"perspective": "objective", "name": "赵衡"},
                      build_hit_table({"perspective": "objective", "name": "赵衡"}, hit), ["minutes"]) is None, "客观/职业模板 → 交原路径判定（不是合并路径的职责）", "")

    synthesized = synthesize_perspective_profile(rich, build_hit_table(rich, hit))
    PerspectiveModeling.validate(synthesized)  # 全字段必填：缺键会在这里炸
    expect(True, "合成结果过 schema（全字段齐、四个字符串非空）", "")
    expect(synthesized["name"] == "赵衡", "合成：name 取画像", "")
    expect(set(synthesized.keys()) == {
              "confidence", "name", "personal_summary", "attention_points",
              "possible_actions", "concerns", "evidence", "responsibilities",
              "relevant_topics", "open_questions", "data_gaps",
          }, "合成：精炼至 11 核心字段（无僵尸字段）", str(list(synthesized.keys())))
    expect(synthesized["attention_points"] == ["接口联调周五前给测试"], "合成：attention_points = 命中条目（不含空壳发言人名）", str(synthesized["attention_points"]))
    expect(synthesized["possible_actions"] == ["原文承诺：接口联调周五前给测试（周五前）"], "合成：possible_actions 标「原文承诺」", "")
    expect(synthesized["responsibilities"] == ["接口实现与联调"], "合成：responsibilities = 职责 ∩ 命中", str(synthesized["responsibilities"]))
    expect(bool(synthesized["evidence"]), "合成：evidence 逐条带依据", str(synthesized["evidence"]))

    none_hit = synthesize_perspective_profile(lean, build_hit_table(lean, empty))
    PerspectiveModeling.validate(none_hit)
    expect("未点到" in none_hit["personal_summary"] and not none_hit["attention_points"], "未命中合成：明确写「本场未点到」，不给条目", "")


def test_tolerant_field_forms() -> None:
    """画像字段容错：personality / preferences / name_aliases 都允许"单串或数组"。

    为什么容错：手写 JSON 时很容易把"一串短句"写成单字符串；旧实现会按字符迭代
    （"家坤" → ['家','坤'] 全被短于 2 字丢掉）或 str(list) 成 "['务实', …]"（脏但碰巧命中）。
    """
    from domains.shared.perspective.preferences import address_aliases, as_text_list, build_preference_block

    expect(as_text_list(None, cap=6) == [], "as_text_list：None → 空", "")
    expect(as_text_list("家坤", cap=6) == ["家坤"], "as_text_list：单字符串 → 单元素", "")
    expect(as_text_list(["小赵", "  ", "小赵", "赵工"], cap=2) == ["小赵", "赵工"], "as_text_list：数组去空去重截断", "")
    expect(address_aliases({"name": "申家坤", "name_aliases": "家坤"}) == ["家坤"], "name_aliases 单字符串不再被按字符切碎", "")
    expect("先列「本用户命中」的待办" in build_preference_block({"name": "申家坤", "preferences": "先写我负责的待办"}), "preferences 单字符串也认", "")

    trait_block = build_preference_block(
        {"name": "申家坤", "personality": ["务实，讨厌含糊的截止日期", "喜欢先看结论"]}
    )
    expect(trait_block.count("语气：") == 2, "personality 数组：多条性格各匹配一次语气白名单", trait_block)
    expect(build_preference_block({"name": "申家坤", "personality": "务实"}).count("语气：") == 1, "personality 字符串：旧写法仍有效", "")
    expect(build_preference_block({"name": "申家坤", "personality": ["急躁", "喜欢先看结论"]}) == "", "性格里命不中的短句被丢弃、原文不进 prompt", "")
    expect("先给结论" in build_preference_block({"name": "申家坤", "preferences": ["喜欢先看结论"]}), "性格里的写作偏好要写进 preferences（否则按设计丢弃）", "")


def test_personal_grouping_and_normalization() -> None:
    """测试真人视角建模的分组保留、上级感知与确定性格式化。"""
    from domains.shared.perspective.preferences import extract_supervisors
    from domains.shared.perspective.hits import render_action_groups_block
    from core.execution.gate import subset_upstream_items

    # 1. extract_supervisors
    u1 = {
        "name": "申家坤",
        "preferences": ["徐玥是我的上级，关注她的指示与行动", "关键数字优先保留"],
    }
    expect(extract_supervisors(u1) == ["徐玥"], "上级提取：偏好句式匹配", str(extract_supervisors(u1)))

    u2 = {"name": "申家坤", "supervisor": "徐总"}
    expect(extract_supervisors(u2) == ["徐总"], "上级提取：显式字段", str(extract_supervisors(u2)))

    # 2. render_action_groups_block 上级置顶
    pack = {
        "speakers": [{"name": "张三"}, {"name": "徐玥"}, {"name": "申家坤"}],
        "action_hints": [{"owner": "张三", "text": "排期"}, {"owner": "徐玥", "text": "审批"}],
    }
    block = render_action_groups_block(u1, pack)
    expect("**与我相关**：" in block, "骨架块：本人排首位", block)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip().startswith("**")]
    expect(lines[:2] == ["**与我相关**：", "**徐玥**："], "骨架块：上级排在他人第一位", str(lines))

    # 3. subset_upstream_items 组名保留与上游原句对齐
    up = ["长文本回去改配置，明天给结论。", "周五前完成接口联调。", "双录还没确认。"]
    draft = [
        "**与我相关**：",
        "长文本回去改配置，明天给结论",
        "**徐玥**：",
        "周五前完成接口联调",
        "**张三**：",
        "完全无关的条目",
    ]
    res = subset_upstream_items(up, draft, fallback_full=False, preserve_groups=True)
    expect(res == ["**与我相关**：", "长文本回去改配置，明天给结论。", "**徐玥**：", "周五前完成接口联调。"], "草稿下采（真人）：保留组名行且按上游原文对齐", str(res))
