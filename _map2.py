# -*- coding: utf-8 -*-
import openpyxl, pathlib, re
wb = openpyxl.load_workbook('now.xlsx', read_only=True)
rows = list(wb['竞品对比'].iter_rows(min_row=2, values_only=True))
arts = {}
for d in pathlib.Path('data/test/output').iterdir():
    f = d / 'result.md'
    if f.is_file():
        arts[d.name] = f.read_text(encoding='utf-8')

def sig(text):
    ls = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith('#')]
    return ls[0][:26] if ls else ''

def han(s):
    return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')

targets = {}
for i, r in enumerate(rows, start=1):
    if i not in (2, 6, 8, 13, 16, 18, 22, 23, 25, 26):
        continue
    s = sig(str(r[2] or ''))
    hit = next((k for k, t in arts.items() if s and s in t), None)
    targets[i] = (str(r[1] or ''), str(r[4] or ''), hit)
    print(f"{i:3d} {str(r[1] or ''):8s} {str(r[4] or ''):>13s} dir={hit} sig={s[:20]}")

print()
def section(text, head):
    lines = text.splitlines()
    out, on = [], False
    for l in lines:
        if l.strip().startswith('# '):
            on = l.strip()[2:].strip() == head
            continue
        if on:
            out.append(l)
    return "\n".join(out).strip()

checks = {
    2: ("沟通背景与目的",),
    6: ("庭审概况", "举证与法庭调查", "事实认定与判决", "证人"),
    8: ("官方表态",),
    13: ("知识主题与概述",),
    16: ("就诊概况",), 18: ("候选人概况与面试岗位", "能力评估", "综合素质"),
    22: ("例会概况",), 25: ("辩论内容概述",),
}
for i, heads in checks.items():
    scene, ln, d = targets[i]
    if not d:
        continue
    t = arts[d]
    print(f"==== 第{i}条 {scene} {ln} ({d[:8]}) 全篇 {han(t)} 汉字")
    heads_all = [l.strip()[2:].strip() for l in t.splitlines() if l.strip().startswith('# ')]
    print("   栏位:", heads_all)
    for h in heads:
        for hh in heads_all:
            if h in hh:
                body = section(t, hh)
                print(f"   [{hh}] {han(body)} 汉字")
    print()
