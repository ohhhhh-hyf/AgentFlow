# -*- coding: utf-8 -*-
import pathlib, re
def han(s): return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
def sec(t, head):
    out, on = [], False
    for l in t.splitlines():
        if l.strip().startswith('# '):
            on = l.strip()[2:].strip() == head; continue
        if on: out.append(l)
    return '\n'.join(out).strip()
def grams(s, n=4):
    s = re.sub(r'[^\u4e00-\u9fff]', '', s)
    return {s[i:i+n] for i in range(max(0, len(s)-n+1))}

arts = {d.name: (d/'result.md').read_text(encoding='utf-8')
        for d in sorted(pathlib.Path('data/test/output').iterdir()) if (d/'result.md').is_file()}
by_first = {}
for k, t in arts.items():
    h = next((l.strip()[2:].strip() for l in t.splitlines() if l.strip().startswith('# ')), '')
    by_first.setdefault(h, []).append((k, t))

print('==== 新闻发布（2 份）====')
for k, t in by_first.get('发布会概况', []):
    ov, gb, ci, qa = sec(t,'发布会概况'), sec(t,'官方表态'), sec(t,'核心信息'), sec(t,'Q&A环节')
    ov = ov.split('# 核心信息')[0]
    print(f"  {k[:8]} 概况 {han(ov)} 汉字 | 官方表态 {han(gb)} | 核心信息 {han(ci)} | Q&A {han(qa)}"
          f" | 表态栏首行: {gb.splitlines()[0][:26] if gb else '—'!r}")
    print(f"        核心信息分组数 {ci.count(chr(10)+'## ')+(1 if ci.startswith('## ') else 0)} | 表态分组数 {gb.count(chr(10)+'## ')+(1 if gb.startswith('## ') else 0)}"
          f" | 两栏 4-gram 重合 {len(grams(ci)&grams(gb))/max(1,len(grams(ci))):.0%} | 括号身份行: {'（' in gb.splitlines()[0][:30] if gb else False}")

print('==== 团队例会（1 份）====')
for k, t in by_first.get('例会概况', []):
    print('  栏位:', [l.strip()[2:].strip() for l in t.splitlines() if l.strip().startswith('# ')])
    for h in ('工作进展','决定与待办','协作需求','待确认与风险'):
        b = sec(t,h)
        print(f"    {h:8s} {han(b):5d} 汉字 | 分点 {b.count(chr(10)+'- ')+(1 if b.startswith('- ') else 0)} | 组(##) {b.count(chr(10)+'## ')}")

print('==== 就医咨询（3 份）====')
for k, t in by_first.get('就诊概况', []):
    cols = {h: sec(t,h) for h in ('就诊概况','病史与背景','诊断与检查结果','治疗方案与医嘱','病情说明与沟通','复诊与预警信号')}
    print(f"  {k[:8]} " + " | ".join(f"{h[:4]}={han(b) if not isinstance(b,str) else han(b)}" for h, b in cols.items()))
    tbl = [l.strip() for l in t.splitlines() if l.strip().startswith('| 药品名称') or (l.strip().startswith('|') and '剂量' in l)]
    print('        药表头:', tbl[0] if tbl else '（无表）', '| 沟通栏在:', '病情说明与沟通' in t)

print('==== 辩论会 / 面试报告 / 项目进度会 ====')
for k, t in by_first.get('辩论内容概述', []):
    tables = [l.strip() for l in sec(t,'核心论点').splitlines() if l.strip().startswith('| 正') or l.strip().startswith('| 反')]
    print(f"  辩论 {k[:8]} 论点表行序: {[x[:6] for x in tables]} | 争议焦点 {han(sec(t,'争议焦点'))} 汉字")
for k, t in by_first.get('候选人概况与面试岗位', []):
    ov = sec(t,'候选人概况与面试岗位')
    tbl = [l.strip() for l in sec(t,'能力评估').splitlines() if l.strip().startswith('|')]
    print(f"  面试 {k[:8]} 首栏 {han(ov)} 汉字 | 能力评估表头: {tbl[0][:60] if tbl else '（无表）'} | 维度行: {[x.split('|')[1].strip() for x in tbl[2:]][:6]}")
for k, t in by_first.get('项目概况', []):
    b = sec(t,'后续计划')
    print(f"  项目 {k[:8]} 后续计划 {han(b)} 汉字 | 分点 {b.count(chr(10)+'- ')+(1 if b.startswith('- ') else 0)} 条")

print('==== 沟通交流会 / 知识笔记 / 金句类 ====')
for k, t in by_first.get('沟通背景与目的', []):
    ov = sec(t,'沟通背景与目的')
    print(f"  沟通 {k[:8]} 首栏 {han(ov)} 汉字 | 数字个数 {len(re.findall(r'[0-9]+', ov))}")
for k, t in by_first.get('知识主题与概述', []):
    cc = sec(t,'核心概念')
    print(f"  知识 {k[:8]} 概述 {han(sec(t,'知识主题与概述'))} 汉字 | 概念组 {cc.count(chr(10)+'## ')+(1 if cc.startswith('## ') else 0)} | 条 {cc.count(chr(10)+'- ')} | 自我省略: {'未详细展开' in t}")
for head in ('金句总结','关键引语与金句','关键原话'):
    for k, t in by_first.get(head, []):
        b = sec(t, head)
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        ok = all((l.startswith('> “') or l.startswith('- 背景：')) for l in lines[:6]) if lines else False
        print(f"  金句[{head}] {k[:8]} 行样例 {lines[:3]} | 格式合规 {ok}")
