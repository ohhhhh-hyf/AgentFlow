# 拆分自原大文件，保留：test_long_generation_output_cap, test_column_fill_concurrency_and_early_stop, test_column_fill_overlong_item_rewrite…

"""tests/unit/core/templates/test_column_projection.py -- 逐栏并发填充、直出快线与模型执行单元测试。"""

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

def test_long_generation_output_cap() -> None:
    """长生成调用必须有输出上限：本地端点没有隐含上限，一次退化 = 49k token / 9 分钟。

    回归背景（2026-09-18 实测）：装配退化成"写不完"——49,074 token / 86,447 字符 / 551 秒，
    被 max_tokens 截断后 JSON 不可解析 → 四栏全空 → 整篇重填，一条纪要跑满 10 分钟。
    """
    from core.templates.length_budget import (
        OUTPUT_CAP_MAX,
        OUTPUT_CAP_MIN,
        effective_doc_budget,
        output_token_cap,
        target_han,
    )

    expect(effective_doc_budget(200) is None, "原文过短（<300 汉字）不给档位预算", "")
    expect(effective_doc_budget(12000) == (1680, 5500), "8k–20k 档：预算 1680–5500", f"{effective_doc_budget(12000)}")
    expect(effective_doc_budget(12000, "# [栏]\n[说明]") == (1680, 5500), "模板声明优先于档位（当前 30 个模板都没声明 → 全走档位）", "")
    caps = [output_token_cap(h) for h in (200, 12000, 60000)]
    expect(OUTPUT_CAP_MIN <= caps[0] <= caps[1] <= caps[2] <= OUTPUT_CAP_MAX, "输出上限随原文规模递增且夹在 1200–12000", f"{caps}")
    expect(output_token_cap(12000) == 6600, "失控量级：8k–20k 原文 → 6600 token（本地约 1 分钟，原来 49k/9 分钟）", f"{output_token_cap(12000)}")
    expect(target_han(None, "") == 4000, "无预算的短原文给中性目标 4000", "")

    # 模板说明里的「短语 20 字内」曾被解析成 hi=20 的小节上限（讲座 [核心观点与论证]，
    # 2026-09-19 实测）：每跑一次都报软提示，且该栏一旦出现散文段会被切成 20 字碎块。
    # 这里钉住"不存在可疑的小节预算"（正常栏级尺寸都在 80 字以上），防止同类写法再犯。
    from core.templates.template_eval import parse_section_char_budgets as _psb

    suspicious = []
    for md in sorted(_active_dir().glob("*.md")):
        for b in _psb(md.read_text(encoding="utf-8")):
            if (b.get("hi") or 10**9) < 80:
                suspicious.append((md.stem, b["title"], b["hi"]))
    expect(not suspicious, "没有 <80 字的「可疑小节预算」（数字+字 的说明性写法已清除）", f"{suspicious}")

    placeholder_src = Path("core/templates/router/_placeholder.py").read_text(encoding="utf-8")
    expect('"max_tokens": cap' in placeholder_src
          and "output_token_cap(source_han, template)" in placeholder_src, "装配：max_tokens 来自目标字数换算并写进两个路径", "")
    render_src = Path("core/runtime/render.py").read_text(encoding="utf-8")
    expect(render_src.count("_render_run(") >= 5
          and "output_token_cap(_doc_han(state), template)" in render_src, "渲染/压缩/展开/返工四处都经 _render_run 带上限", "")
    minutes_src = Path(
        "domains/meeting/tasks/minutes/steps/minutes_render.py"
    ).read_text(encoding="utf-8")
    expect("max_tokens=max_tokens" in minutes_src and "max_tokens: int | None = None" in minutes_src, "纪要渲染步接受并透传 max_tokens", "")


def test_column_fill_concurrency_and_early_stop() -> None:
    """逐栏填充：一栏一次调用、栏间并发、失败只重试该栏；退化（重复/超长）流式早停。

    回归背景（2026-09-18 实测）：整篇 JSON 装配退化时写出 49,074 token / 86,447 字符，
    551 秒后才被 max_tokens 截断，JSON 不可解析 → 四栏全空 → 整篇重填。逐栏后爆炸半径
    只有一栏，流式下发现重复/超长立刻放弃，只重试那一栏。
    """
    import asyncio
    import re as _re

    from core.templates.router._placeholder import (
        _degenerate_reason,
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    expect(len(plan["scalars"]) == 4 and not plan["row_templates"], "新闻发布：4 个标量栏、无表格（走逐栏路径）", f"{len(plan['scalars'])}/{len(plan['row_templates'])}")

    class _FakeStream:
        """脚本化流式客户端：按「第 N/M 栏」分派分块，并统计并发与每栏调用次数。"""

        def __init__(self, scripts: dict) -> None:
            self.scripts = scripts
            self.users: list[str] = []
            self.counts: dict[int, int] = {}
            self.caps: list[int] = []
            self.in_flight = 0
            self.max_in_flight = 0

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            self.caps.append(max_tokens)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                chunks = self.scripts[idx]
                if callable(chunks):
                    chunks = chunks(self.counts[idx])
                for chunk in chunks:
                    await asyncio.sleep(0)
                    yield chunk
            finally:
                self.in_flight -= 1

    good = {
        1: ["发布会概况：主办方、三块板块与整体基调。"],
        2: ["- **要点**：核心信息一条。"],
        3: ["**表态**：官方口径。"],
        4: ["**主持人**：问题？\n**发言人**：回应。"],
    }
    client = _FakeStream(dict(good))
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    expect(client.counts == {1: 1, 2: 1, 3: 1, 4: 1}, "逐栏填充：四栏各一次调用", f"{client.counts}")
    expect(client.max_in_flight >= 2, "逐栏填充：栏间并发（同时在飞 ≥2）", f"{client.max_in_flight}")
    expect(bool(client.caps) and all(c == 6600 for c in client.caps), "逐栏填充：输出上限透传到每次调用（6600）", f"{client.caps}")
    expect(bool(text)
          and "# 发布会概况" in text
          and "[发布会概况]" not in text
          and all(chunks[0] in text for chunks in good.values()), "逐栏填充：拼装出四栏正文、标题由程序生成、无残留占位符", (text or "")[:80])
    expect(all("【本栏说明】" in u for u in client.users)
          and "只写第 1/4 栏（发布会概况）" in client.users[0]
          and "[核心信息]" in client.users[0], "逐栏填充：每栏只拿自己的说明 + 其它栏名（防越栏）", "")
    expect(all("【本篇目标】" in u for u in client.users), "逐栏填充：带上【本篇目标】（目标长度写进指令区）", "")

    para = "同一段话反复出现，这段特意写长一点以触发退化判据，并确保累计长度越过检查阈值。" * 3
    scripts = dict(good)
    scripts[2] = lambda attempt: (
        [para + "\n\n"] * 3 if attempt == 1 else ["- **要点**：重试后的内容。"]
    )
    client2 = _FakeStream(scripts)
    text2 = asyncio.run(
        fill_placeholder_by_columns(client2, "内容来源略。", mb, plan, source_han=12000)
    )
    expect(client2.counts == {1: 1, 2: 2, 3: 1, 4: 1}, "退化早停：重复段落被中止，且只重试该栏（其它栏一次）", f"{client2.counts}")
    expect(bool(text2) and "重试后的内容" in text2, "退化早停：最终用重试后的内容", (text2 or "")[:60])

    scripts3 = dict(good)
    scripts3[3] = lambda attempt: (
        ["这是一段用来把输出撑到上限之外的填充文字。" * 600]
        if attempt == 1
        else ["**表态**：重试内容。"]
    )
    client3 = _FakeStream(scripts3)
    text3 = asyncio.run(
        fill_placeholder_by_columns(client3, "内容来源略。", mb, plan, source_han=12000)
    )
    expect(client3.counts == {1: 1, 2: 1, 3: 2, 4: 1} and bool(text3) and "重试内容" in text3, "超长早停：输出超上限即中止并只重试该栏", f"{client3.counts}")

    long_para = "这是一段足够长的重复段落文本内容，长度要超过判据下限。"  # ≥24 字才参与判据
    expect("重复" in _degenerate_reason("\n\n".join([long_para] * 3))
          and _degenerate_reason("\n\n".join([long_para] * 2)) == ""
          and _degenerate_reason("短句。\n\n短句。\n\n短句。") == "", "退化判据：同段重复 3 次命中、2 次不命中", "")

    pp = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")

    class _TableStream:
        async def stream_text(self, system, user, **kw):
            yield "内容。"

        async def text(self, *a, **kw):
            return '{"tables": [[["模块A", "进行中"]]]}'

    table_result = asyncio.run(
        fill_placeholder_by_columns(_TableStream(), "略", pp, plan_placeholder_fill(pp))
    )
    expect(isinstance(table_result, str) and bool(table_result),
           "有表格的模板也走逐栏路径（表格由 extract_tables 补）", "")


def test_column_fill_overlong_item_rewrite() -> None:
    """逐栏填充：单条超长（`- ` 条目 >200 汉字）当硬问题 → 只重写中招那一栏，并下发具体修法。

    回归背景（2026-09-22 实测「端侧待办与现网推测问题」转写，同一输入相邻两次运行）：
    要点梳理栏把 12 条待确认 + 20 条风险各用「；」压成一条（233 字 / 519 字）原样落盘——
    审核在渲染之前（看不到栏内文字）、渲染层只把它当 advisory 记账，于是无人拦。
    现在这一栏会被定位、重写一次（一次单栏调用），渲染层行为不变。
    """
    import asyncio
    import re as _re

    from core.execution.gate import overlong_items
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    long_bullet = "- **表态**：" + "官方口径说明" * 45 + "。"
    good = {
        1: "发布会概况：主办方、三块板块与整体基调。",
        2: "- **要点**：核心信息一条。",
        4: "**主持人**：问题？\n**发言人**：回应。",
    }

    class _FakeStream:
        """脚本化流式客户端：第 3 栏首轮给一条超长条，重写轮给分条版本。"""

        def __init__(self) -> None:
            self.users: list[str] = []
            self.counts: dict[int, int] = {}

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield long_bullet if self.counts[idx] == 1 else (
                    "- **表态**：官方口径一条。\n- **口径**：另一条。"
                )
            else:
                yield good[idx]

    client = _FakeStream()
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    expect(bool(overlong_items(long_bullet)), "超长条：判据命中（>200 汉字的一条）", "")
    expect(client.counts == {1: 1, 2: 1, 3: 2, 4: 1}, "超长条：只重写中招那一栏（其余栏各一次）", f"{client.counts}")
    expect("上一版这一栏存在单条承载多项事实的长条目" in client.users[-1]
          and "二级缩进" in client.users[-1], "超长条：重写时下发分层展开修法", client.users[-1][-160:] if client.users else "")
    expect("官方口径一条" in (text or ""), "超长条：重写后的内容进了正文", (text or "")[:60])
    expect(bool(text) and overlong_items(text) == [], "超长条：最终正文不再有超长条", "")


def test_column_fill_overlong_minutes_strategies() -> None:
    """验证 minutes 策略 A（调大判定阈值）与策略 B（频次门槛）有效性。

    - 策略 A：单个条目在 230~250 字（如司法/技术详细举证），设置 overlong_han=280 时不触发重写；
    - 策略 B：单条 290 字超过 280，但只有 1 条（未达到 min_count=2），不触发重写；
    - 频次触发：达到 2 条 290 字时，触发重写；
    - 极端超长：即使只有 1 条，但达到 380 字（>=350），依然安全兜底触发重写。
    """
    import asyncio
    import re as _re
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)

    good = {
        1: "发布会概况：主办方、三块板块与整体基调。",
        2: "- **要点**：核心信息一条。",
        4: "**主持人**：问题？\n**发言人**：回应。",
    }

    # 测试 1: 策略 A + 策略 B（1 条 245 字，完全不触发重写，仅 1 次调用）
    court_evidence_bullet = "- **证据一**：" + "原告提交供货合同及对账单证明交付" * 15 + "。"  # ~240 字

    class _Client1:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield court_evidence_bullet if idx == 3 else good[idx]

    c1 = _Client1()
    asyncio.run(
        fill_placeholder_by_columns(
            c1, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c1.counts.get(3) == 1, "minutes策略A：1条245字证据条目（<=280字）不触发重写", f"{c1.counts}")

    # 测试 2: 策略 B（1 条 290 字，>280 但只有 1 条 < 2，容忍放行不触发重写）
    single_long_bullet = "- **证据一**：" + "原告提交供货合同及对账单证明交付" * 18 + "。"  # ~290 字

    class _Client2:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield single_long_bullet if idx == 3 else good[idx]

    c2 = _Client2()
    asyncio.run(
        fill_placeholder_by_columns(
            c2, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c2.counts.get(3) == 1, "minutes策略B：单条290字虽超280但仅1条（未达频次2），容忍放行不触发重写", f"{c2.counts}")

    # 测试 3: 策略 B 触发（2 条 290 字，达到频次 2，触发单栏重写）
    two_long_bullets = single_long_bullet + "\n" + single_long_bullet

    class _Client3:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield two_long_bullets if self.counts[idx] == 1 else "- **证据1**：拆分一。\n- **证据2**：拆分二。"
            else:
                yield good[idx]

    c3 = _Client3()
    asyncio.run(
        fill_placeholder_by_columns(
            c3, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c3.counts.get(3) == 2, "minutes策略B触发：2条290字达到频次门槛，触发该栏重写", f"{c3.counts}")

    # 测试 4: 极端大段挤压兜底（1 条 380 字，>=350，即使只有 1 条依然触发重写安全兜底）
    extreme_bullet = "- **表态**：" + "大段文字挤压挤压" * 48 + "。"  # ~386 字

    class _Client4:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield extreme_bullet if self.counts[idx] == 1 else "- **表态**：拆分后内容。"
            else:
                yield good[idx]

    c4 = _Client4()
    asyncio.run(
        fill_placeholder_by_columns(
            c4, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c4.counts.get(3) == 2, "极端超长兜底：单条380字（>=350）即使仅1条也触发安全重写", f"{c4.counts}")
