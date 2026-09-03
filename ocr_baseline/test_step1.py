# -*- coding: utf-8 -*-
"""Step1（P0~P4 收敛版）离线单元测试：显式缺失分类 / 触发纪律 / 事件观测。

运行：python ocr_baseline/test_step1.py（零网络，LLM 用假实现）。
口径提醒：判定"整行缺失"用字符保留率 <0.25，测试语料各行使用互不重叠的措辞，
避免"行被删但字都还在"的假阳性。
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
from tools.ocr import engines as eng_mod

# 互不重叠的正文措辞（供缺失/存在判定使用）
P_A = "连续函数在闭区间上必有界且能取得最大最小值"
P_B = "导数零点定理断言两零点之间存在驻点且该点导数为零"
P_C = "介值定理保证函数可取到介于端点数值之间的任意值"
P_D = "罗尔定理需要区间端点函数值相等这一前提条件才成立"
P_E = "拉格朗日中值定理给出平均变化率等于区间内某点的导数值"
P_F = "柯西中值定理把两个函数的变化率比值推广到参数形式"


class FakeClient:
    """可编程假 LLM：text() 返回预设片段并记录调用。"""

    provider, model = "fake", "fake"
    def __init__(self, fragment: str = ""):
        self.fragment = fragment
        self.calls: list[dict] = []

    async def text(self, system, user, **kw):
        self.calls.append({"system": system, "label": kw.get("label"), "max_tokens": kw.get("max_tokens")})
        return self.fragment


def reset(fragment: str = ""):
    rc.take_completeness_events()
    client = FakeClient(fragment)
    eng_mod.get_llm_client = lambda: client
    return client


def body(text: str) -> dict:
    return {"text": text, "conf": 0.95}


def md_of(parts: list[str]) -> str:
    return "\n\n".join(parts)


def absent_indexes(lines, md) -> list[int]:
    return [r["index"] for r in rc.check_markdown_completeness(lines, md)["absent_rows"]]


def main() -> None:
    os.environ["OCR_COMPLETENESS_FIX"] = "1"
    os.environ.pop("OCR_CONTINUE_MAX_CALLS", None)

    # ── 分类：公式行/编号标题行永不进 absent；正文整行缺失才进 ──
    lines = [
        body("F(x)=∫ f(t) dt 连续积累量表达"),      # 0 公式行
        body("第一节 标题性内容与记号约定"),           # 1 编号标题行
        body(P_A),                                    # 2 正文（在稿）
        body(P_B),                                    # 3 正文整行缺失
        body(P_C),                                    # 4 正文（在稿）
    ]
    md = md_of([lines[0]["text"], lines[2]["text"], lines[4]["text"]])
    assert absent_indexes(lines, md) == [3], absent_indexes(lines, md)
    print("PASS classify 正文整行缺失才触发")

    lines2 = [
        body("G(x)=∫ g(t) dt 表达"),                 # 公式行（不在稿中）
        body("第二节 另一个标题行"),                   # 编号标题行（不在稿中）
        body(P_A),                                    # 正文（在稿）
    ]
    md2 = md_of([lines2[2]["text"]])
    assert absent_indexes(lines2, md2) == [], absent_indexes(lines2, md2)
    print("PASS classify 公式/编号标题行不触发")

    # ── 完整稿：零调用、事件 fired=0 ──
    client = reset()
    rows = [body(P_A), body(P_B), body(P_C)]
    full_md = md_of([r["text"] for r in rows])
    assert rc.ensure_markdown_complete(full_md, rows) == full_md and not client.calls
    ev = rc.take_completeness_events()
    assert len(ev) == 1 and ev[0]["fired_calls"] == 0 and ev[0]["gate"] == "on"
    print("PASS 完整稿零调用")

    # ── 开关关闭：原样返回 + 事件 gate=off ──
    os.environ["OCR_COMPLETENESS_FIX"] = "0"
    client = reset()
    out = rc.ensure_markdown_complete(md_of([P_A]), [body(P_A)])
    assert out == md_of([P_A]) and not client.calls
    assert rc.take_completeness_events() == [{"gate": "off"}]
    os.environ["OCR_COMPLETENESS_FIX"] = "1"
    print("PASS gate=off 旁路")

    # ── 中段整行缺失 → 补中调用 + 锚点插入 + 独立 label ──
    client = reset("补回：" + P_B + "（完整）")
    lines3 = [body(P_A), body(P_B), body("H(x)=x^2+1 二次函数式"), body(P_C)]
    md3 = md_of([lines3[0]["text"], lines3[3]["text"]])
    out3 = rc.ensure_markdown_complete(md3, lines3)
    assert client.calls and client.calls[0]["label"] == "ocr/reconstruct/fix", client.calls
    ia, ix, ib = out3.index(P_A), out3.index(P_B), out3.index(P_C)
    assert ia < ix < ib, (ia, ix, ib)
    ev = rc.take_completeness_events()
    assert ev[0]["modes"] == ["mid"] and ev[0]["fired_calls"] == 1, ev[0]
    print("PASS 补中插入 + label=fix")

    # ── 噪声纪律：短小/低信息缺失不触发 ──
    client = reset()
    lines4 = [body(P_A), body("零星字"), body(P_C)]
    md4 = md_of([lines4[0]["text"], lines4[2]["text"]])
    assert rc.ensure_markdown_complete(md4, lines4) == md4 and not client.calls
    rc.take_completeness_events()
    print("PASS 噪声不触发")

    # ── 稿尾结构信号 + 尾部缺失 → 续尾调用、残片被裁、内容回归 ──
    client = reset("$$x=\\int f\\,dt$$ " + P_D)
    lines5 = [body(P_A), body(P_E), body(P_D)]
    md5 = md_of([lines5[0]["text"], lines5[1]["text"], "\\$\\$[\\hat{l}_x 残片"])
    out5 = rc.ensure_markdown_complete(md5, lines5)
    assert client.calls and client.calls[0]["label"] == "ocr/reconstruct/fix"
    assert "残片" not in out5 and P_D in out5
    ev = rc.take_completeness_events()
    assert ev[0]["modes"] == ["tail"] and ev[0]["tail_cut_signal"] is True, ev[0]
    print("PASS 续尾 + 残片裁除")

    # ── 片段定界不平衡 → 拒绝片段、原文兜底（不留半截公式）──
    client = reset("$$x$")  # 3 个 $ → 不平衡
    lines6 = [body(P_A), body(P_D)]
    md6 = md_of([lines6[0]["text"], "\\$\\$[ 残片"])
    out6 = rc.ensure_markdown_complete(md6, lines6)
    assert "残片" not in out6 and P_D in out6  # 原文兜底
    ev = rc.take_completeness_events()
    assert ev[0]["fired_calls"] == 0 and ev[0]["fallback_rows"] >= 1, ev[0]
    print("PASS 不平衡片段回退兜底")

    # ── 预算外中段（两段不相邻缺失，预算 1）→ 第二段原文兜底，内容不丢 ──
    os.environ["OCR_CONTINUE_MAX_CALLS"] = "1"
    client = reset("补回：" + P_B + "（完整）")
    lines7 = [body(P_A), body(P_B), body(P_E), body(P_C), body(P_F)]
    md7 = md_of([lines7[0]["text"], lines7[2]["text"], lines7[4]["text"]])
    out7 = rc.ensure_markdown_complete(md7, lines7)
    assert P_B in out7 and P_C in out7  # 一段补中插入、一段兜底追加
    ev = rc.take_completeness_events()
    assert ev[0]["fired_calls"] == 1 and ev[0]["fallback_rows"] == 1, ev[0]
    os.environ.pop("OCR_CONTINUE_MAX_CALLS", None)
    print("PASS 预算外余段兜底")

    # ── 无 LLM 客户端 → 全部原文兜底 ──
    eng_mod.get_llm_client = lambda: None
    lines8 = [body(P_A), body(P_D)]
    out8 = rc.ensure_markdown_complete(md_of([P_A]), lines8)
    assert P_D in out8
    ev = rc.take_completeness_events()
    assert ev[0]["fallback_rows"] >= 1
    print("PASS 无 LLM 原文兜底")

    # ── 事件 1:1 且可取空 ──
    reset()
    rc.ensure_markdown_complete(P_A, [body(P_A)])
    ev = rc.take_completeness_events()
    assert len(ev) == 1 and ev[0]["gate"] == "on" and rc.take_completeness_events() == []
    print("PASS 事件配对与清空")

    print("ALL_STEP1_TESTS_OK")


if __name__ == "__main__":
    main()
