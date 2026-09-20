# -*- coding: utf-8 -*-
"""分段速览：单段上限 150 → 250 字（超长仍按句界自动拆分）。"""
import pathlib
import re

P = pathlib.Path("template_v3/general_minutes.md")
raw = P.read_bytes().decode("utf-8")
OLD = "（**每段最多 150 字**；不写 `- ` 分点、不铺陈、"
NEW = "（**每段最多 250 字**；不写 `- ` 分点、不铺陈、"
assert raw.count(OLD) == 1
P.write_bytes(re.sub(rb"\r?\n", b"\r\n", raw.replace(OLD, NEW).encode("utf-8")))
print("模板改完：150 → 250")

G = pathlib.Path("tools/template_router/_selftest.py")
g = G.read_bytes().decode("utf-8")
PAIRS = [
    ('    check("通用纪要：摘要为一段 250–400（节级），速览为一段 120–150（段落级）",\r\n'
     '          any(b["title"] == "全文摘要" and b["lo"] == 250 and b["hi"] == 400 and b["scope"] == "section" for b in budgets)\r\n'
     '          and any(b["title"] == "分段速览" and b["hi"] == 150 and b["scope"] == "paragraph" for b in budgets),\r\n'
     '          f"{budgets}")',
     '    check("通用纪要：摘要为一段 250–400（节级），速览为一段 200–250（段落级）",\r\n'
     '          any(b["title"] == "全文摘要" and b["lo"] == 250 and b["hi"] == 400 and b["scope"] == "section" for b in budgets)\r\n'
     '          and any(b["title"] == "分段速览" and b["hi"] == 250 and b["scope"] == "paragraph" for b in budgets),\r\n'
     '          f"{budgets}")'),
    ('    check("通用纪要：速览按议题分段 + 段数最多 8 段 + 每段一段话 ≤150 字",',
     '    check("通用纪要：速览按议题分段 + 段数最多 8 段 + 每段一段话 ≤250 字",'),
    ('          and "每段最多 150 字" in seg_spec and "每段至少一句" in seg_spec',
     '          and "每段最多 250 字" in seg_spec and "每段至少一句" in seg_spec'),
    ('    check("通用纪要：速览不声明「不拆段」（超长段由 150 字上限按句界拆分）",',
     '    check("通用纪要：速览不声明「不拆段」（超长段由 250 字上限按句界拆分）",'),
    ('    long_seg = "这是一段概览文字。" * 55  # ≈440 汉字，远超 150×1.2',
     '    long_seg = "这是一段概览文字。" * 55  # ≈440 汉字，远超 250×1.2'),
    ('    check("通用纪要：速览超 180 字的段被程序按句界拆分（150 字上限生效）",\r\n'
     '          bool(seg_notes) and len(seg_parts) >= 2 and max(sum(1 for c in q if "\\u4e00" <= c <= "\\u9fff") for q in seg_parts) <= 160,\r\n'
     '          f"段数={len(seg_parts)} {seg_notes}")',
     '    check("通用纪要：速览超 300 字的段被程序按句界拆分（250 字上限生效）",\r\n'
     '          bool(seg_notes) and len(seg_parts) >= 2 and max(sum(1 for c in q if "\\u4e00" <= c <= "\\u9fff") for q in seg_parts) <= 260,\r\n'
     '          f"段数={len(seg_parts)} {seg_notes}")'),
    ('    # 2026-09-20 方案1：速览改为「一段话 ≤150 字」，段落级预算重新生效（超 180 字按句界拆）\r\n'
     '    check("通用纪要：速览段落级预算 (120,150) 生效",\r\n'
     '          bool(gcaps) and gcaps[0]["hi"] == 150 and gcaps[0]["scope"] == "paragraph", f"{gcaps}")',
     '    # 2026-09-20：速览改为「一段话 ≤250 字」，段落级预算生效（超 300 字＝250×1.2 按句界拆）\r\n'
     '    check("通用纪要：速览段落级预算 (200,250) 生效",\r\n'
     '          bool(gcaps) and gcaps[0]["hi"] == 250 and gcaps[0]["scope"] == "paragraph", f"{gcaps}")'),
    ('    check("通用纪要：速览一段话 ≤150 字、段数最多 8 段、明细归 [要点梳理]",\r\n'
     '          "一段话描述该段" in spec_seg and "每段最多 150 字" in spec_seg',
     '    check("通用纪要：速览一段话 ≤250 字、段数最多 8 段、明细归 [要点梳理]",\r\n'
     '          "一段话描述该段" in spec_seg and "每段最多 250 字" in spec_seg'),
    ('        check(f"通用纪要：速览 440 字段按 150 字上限拆分（{label}）",\r\n'
     '              bool(notes) and len(seg_parts) >= 2\r\n'
     '              and max(sum(1 for c in q if "\\u4e00" <= c <= "\\u9fff") for q in seg_parts) <= 160,',
     '        check(f"通用纪要：速览 440 字段按 250 字上限拆分（{label}）",\r\n'
     '              bool(notes) and len(seg_parts) >= 2\r\n'
     '              and max(sum(1 for c in q if "\\u4e00" <= c <= "\\u9fff") for q in seg_parts) <= 260,'),
    ('    check("通用纪要：两栏各自按自己的上限拆（摘要节级 400 / 速览段落级 150）",',
     '    check("通用纪要：两栏各自按自己的上限拆（摘要节级 400 / 速览段落级 250）",'),
]
for old, new in PAIRS:
    n = g.count(old)
    print(("守卫 OK " if n == 1 else "守卫 SKIP(%d) " % n) + old[:46].replace("\r\n", "⏎"))
    assert n == 1, old[:70]
    g = g.replace(old, new)
G.write_bytes(g.encode("utf-8"))
print("守卫改完")
