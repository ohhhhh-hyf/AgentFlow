# -*- coding: utf-8 -*-
"""P2 改动3：公式行词元级缺失检测（OCR_FORMULA_MISS_CHECK）离线测试。

运行：python ocr_baseline/test_step6.py（零网络）。
验证点：判据本身（守恒改写不误报 / 整行丢失才触发 / 不可判类别豁免 /
上下标与粘连拆分归一 / 纯数字无判别力），及 _draft_completeness /
_still_missing_rows 的接入（absent 分类、公式行复检、正文行行为不变）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.CRITICAL)

from tools.ocr import reconstruct as rc


def row(text: str, formula: str = "", role: str = "body", conf: float | None = None,
        decision: str = "locked_body") -> dict:
    item: dict = {"text": text, "role_hint": role, "title_decision": decision}
    if formula:
        item["formula"] = formula
    if conf is not None:
        item["conf"] = conf
    return item


def main() -> None:
    def md_tokens(md: str) -> set:
        return set(rc._math_content_tokens(md))

    # ── 判据：守恒改写不误报（LaTeX 化保留内容词元）──
    md = "理想气体状态方程 $$pV = nRT$$ 其中 n 为单位体积内粒子数"
    assert rc._formula_high_conf_missing("PV = nRT", md_tokens(md)) is False, "LaTeX 改写后仍应判为存在"
    # \frac 结构改写：分子/分母/主体词元都在
    md2 = "$$\\frac{nRT}{V}=p$$ 压强表达式"
    assert rc._formula_high_conf_missing("pV = nRT", md_tokens(md2)) is False, "结构改写仍应判为存在"
    # 上下标改写（x2 ↔ x^{2}）与行内函数名：词元守恒
    md3 = "$$mv^{2}=2gh$$ 与 $$y=\\sin(2\\pi x)+\\cos(2\\pi x)$$"
    assert rc._formula_high_conf_missing("mv2 = 2gh", md_tokens(md3)) is False
    assert rc._formula_high_conf_missing("mv\u00b2 = 2gh", md_tokens(md3)) is False, "上标字符应归一"
    assert rc._formula_high_conf_missing("y = sin(2πx) + cos(2πx)", md_tokens(md3)) is False
    # 部分命中（≥1 词元在稿）→ 视为存在（防误报；改写/拆行会保留部分词元）
    assert rc._formula_high_conf_missing("pV = nkT", md_tokens("$$p=nkT$$ 平均动能公式")) is False

    # ── 判据：整行丢失 → 高置信缺失 ──
    assert rc._formula_high_conf_missing("PV = nRT", md_tokens("气体动理论压强")) is True, "整行丢失应触发"
    assert rc._formula_high_conf_missing("pV = nRT", md_tokens("$$PV=nRT$$")) is False

    # ── 不可判豁免（None = 旧行为：不参与缺失）──
    assert rc._formula_high_conf_missing("", md_tokens("x")) is None
    assert rc._formula_high_conf_missing("E = mc2", md_tokens("力学能守恒")) is None, "词元 <2 无从判断"
    assert rc._formula_high_conf_missing("x2 + y2 = z2", md_tokens("$$x^{2}+y^{2}=z^{2}$$")) is None, \
        "短字母公式不可判（上下标全拆成单字符段）"
    assert rc._formula_high_conf_missing("mv2 = 2gh", md_tokens("无任何公式的正文内容")) is True
    # 含汉字段：LLM 有权按文本口径纠错重写 → 豁免
    assert rc._formula_high_conf_missing("压强 p = nkT，n 为单位体积粒子数", md_tokens("")) is None
    # 括号不配对（OCR 缺符错读）→ 豁免
    assert rc._formula_high_conf_missing("pV = nRT (式中 n", md_tokens("")) is None
    # 纯数字/单字母构成的串无内容词元 → 豁免
    assert rc._formula_high_conf_missing("v = 3 m/s", md_tokens("")) is None

    # ── 词元提取：上下标归一 / 粘连拆分 / 纯数字剔除 ──
    assert rc._math_content_tokens("PV = nRT") == ["pv", "nrt"]
    assert rc._math_content_tokens("mv2 = 2gh") == ["mv", "gh"], "粘连串拆成字母段，2 无判别力"
    assert rc._math_content_tokens("x2+y2=z2") == []
    assert rc._math_content_tokens("x\u00b2+y\u00b2=z\u00b2") == []
    assert rc._math_content_tokens("k\u2080T") == [], "k0t 拆后全是单字符段"
    assert rc._math_content_tokens("300K") == [], "纯数字段无判别力"
    assert rc._math_content_tokens("300") == []
    assert rc._math_content_tokens("sin") == ["sin"]

    print("PASS 判据单元行为")

    # ── 接入 _draft_completeness：高置信缺失公式行进入 absent ──
    md5 = ("前置正文内容足够长用于锚点定位说明甲乙丙丁戊己庚辛壬癸。\n"
           "状态方程推导过程正文内容完整出现于稿中甲乙丙丁戊己庚辛壬癸。")
    ls = [
        row("前置正文内容足够长用于锚点定位说明甲乙丙丁戊己庚辛壬癸。"),
        row("PV = nRT", role="formula"),        # 高置信缺失（md 无词元命中）
        row("状态方程推导过程正文内容完整出现于稿中甲乙丙丁戊己庚辛壬癸。"),
        row("x2 + y2 = z2", role="formula"),    # 短字母公式 → 豁免
    ]
    os.environ["OCR_FORMULA_MISS_CHECK"] = "1"
    try:
        chk = rc._draft_completeness(ls, md5)
    finally:
        os.environ.pop("OCR_FORMULA_MISS_CHECK", None)
    assert len(chk["present"]) == 2, chk["present"]
    assert [r["line"] for r in chk["absent_rows"]] == ["PV=nRT"], chk["absent_rows"]
    print("PASS 公式行进入 absent")

    # ── 接入：正文行缺失仍走原 8 连字符判据（测试行内容与 md 无 8 连字符重叠）──
    ls2 = [
        row("第一段正文内容完整出现于稿中甲乙丙丁戊己庚辛壬癸"),
        row("被整行丢弃的正文内容足够长的一行壹贰叁肆伍陆柒捌玖拾拾壹"),
    ]
    chk2 = rc._draft_completeness(ls2, "第一段正文内容完整出现于稿中甲乙丙丁戊己庚辛壬癸")
    body_absent = [r for r in chk2["absent_rows"] if not r["formula"]]
    assert len(body_absent) == 1 and "被整行丢弃" in body_absent[0]["text"], chk2["absent_rows"]
    print("PASS 正文行判据不变")

    # ── 接入 _still_missing_rows：补写后公式行按词元复检 ──
    run_rows = [dict(r) for r in chk["rows_all"] if r["line"] == "PV=nRT"]
    still = rc._still_missing_rows(run_rows, md5 + "\n\n$$pV=nRT$$")
    assert still == [], "补写后公式词元已在稿中 → 不再缺失"
    still2 = rc._still_missing_rows(run_rows, md5)
    assert len(still2) == 1 and still2[0]["formula"], "未补写 → 复检仍缺失，转兜底"
    print("PASS 补写后公式行复检")

    # ── 开关 OCR_FORMULA_MISS_CHECK=0：公式行恢复旧豁免 ──
    os.environ["OCR_FORMULA_MISS_CHECK"] = "0"
    try:
        chk3 = rc._draft_completeness(ls, md5)
    finally:
        os.environ.pop("OCR_FORMULA_MISS_CHECK", None)
    assert not [r for r in chk3["absent_rows"] if r["formula"]], "关闭后公式行不参与缺失"
    print("PASS 开关回退旧行为")

    e2e()

    print("\nALL PASS")


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    async def text(self, *a, **k) -> str:
        self.calls += 1
        return self.reply


def e2e() -> None:
    """ensure_markdown_complete 触发接线（中段门槛 / 补写复检 / 页尾旧盲区）。"""
    from tools.ocr import engines as E

    md = "前置正文完整存在于稿中甲乙丙丁戊己庚辛壬癸。\n\n后续正文同样完整在稿中乙丙丁戊己庚辛壬癸"
    lines = [
        row("前置正文完整存在于稿中甲乙丙丁戊己庚辛壬癸。"),
        row("mv2/2 = 3nRT/2", role="formula"),   # ≥10 字符、≥2 词元 → 中段可触发
        row("后续正文同样完整在稿中乙丙丁戊己庚辛壬癸"),
    ]

    def run(md_: str, ls_: list[dict], fake) -> str:
        os.environ["OCR_COMPLETENESS_FIX"] = "1"
        os.environ["OCR_FORMULA_MISS_CHECK"] = "1"
        orig = E.get_llm_client
        E.get_llm_client = lambda: fake
        try:
            return rc.ensure_markdown_complete(md_, ls_)
        finally:
            E.get_llm_client = orig
            os.environ.pop("OCR_COMPLETENESS_FIX", None)
            os.environ.pop("OCR_FORMULA_MISS_CHECK", None)

    # 场景1：无客户端 → 原文兜底（确定性路径）
    out = run(md, lines, fake=None)
    ev = rc.take_completeness_events()[-1]
    assert "mv2/2 = 3nRT/2" in out, out
    assert ev["fallback_rows"] == 1, ev

    # 场景2：fake LLM 补写 → 词元复检通过，零兜底
    fc = _FakeClient("$$\\frac{mv^{2}}{2}=\\frac{3nRT}{2}$$")
    out2 = run(md, lines, fake=fc)
    assert fc.calls == 1 and "\\frac{mv" in out2, (fc.calls, out2[-200:])
    ev2 = rc.take_completeness_events()[-1]
    assert ev2["fired_calls"] == 1 and ev2["fallback_rows"] == 0, ev2

    # 场景3：公式已保留在稿（词元覆盖）→ 零调用，不误报
    md3 = "状态方程 $$mv^{2}/2=3nRT/2$$ 其余正文同样完整在稿中甲乙丙丁戊己庚辛壬癸"
    fc3 = _FakeClient("")
    out3 = run(md3, lines, fake=fc3)
    assert fc3.calls == 0 and out3 == md3, (fc3.calls, out3 == md3)

    # 场景4：页尾公式行丢失（旧盲区：无正文行缺失也触发续尾）
    out4 = run(md, lines[:2], fake=None)
    ev4 = rc.take_completeness_events()[-1]
    assert "mv2/2 = 3nRT/2" in out4 and ev4["fallback_rows"] >= 1, (out4, ev4)

    print("PASS 端到端：中段触发/补写复检/零误报/页尾公式盲区闭合")


if __name__ == "__main__":
    main()
