# -*- coding: utf-8 -*-
import pathlib, re, openpyxl
def han(s): return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
def sec(t, head):
    out, on = [], False
    for l in t.splitlines():
        if l.strip().startswith('# '):
            on = l.strip()[2:].strip() == head; continue
        if on: out.append(l)
    return '\n'.join(out).strip()
wb = openpyxl.load_workbook('now.xlsx', read_only=True)
rows = list(wb['竞品对比'].iter_rows(min_row=2, values_only=True))
arts = {d.name: (d/'result.md').read_text(encoding='utf-8') for d in sorted(pathlib.Path('data/test/output').iterdir()) if (d/'result.md').is_file()}
def sig(cell):
    ls = [l.strip() for l in str(cell or '').splitlines() if l.strip() and not l.strip().startswith('#')]
    return ls[0][:26] if ls else ''
print('==== 超原文 70% 天花板 的产物 ====')
over = []
for i, r in enumerate(rows, 1):
    cell = str(r[2] or '')
    if not cell.strip(): continue
    src_han = han(str(r[0] or ''))
    s = sig(cell)
    did = next((k for k, t in arts.items() if s and s in t), None)
    if not did: continue
    out = han(arts[did])
    if src_han and out > src_han * 0.7:
        over.append((i, str(r[1] or ''), out, src_han, out / src_han))
for i, scene, out, src, ratio in sorted(over, key=lambda x: -x[4]):
    print(f'  第{i:2d}条 {scene:10s} 产物 {out:5d} 汉字 / 原文 {src:5d} = {ratio:.0%}')
print(f'  共 {len(over)}/{len(rows)} 份越过 70% 天花板')
print()
print('==== 金句格式核查 ====')
for head in ('金句总结', '关键引语与金句', '关键原话'):
    for did, t in arts.items():
        if f'# {head}' not in t: continue
        b = sec(t, head)
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        pairs = [(lines[i], lines[i+1] if i+1 < len(lines) else '') for i in range(0, min(len(lines)-1, 8), 2)]
        print(f'  [{head}] {did[:8]}:')
        for q, bg in pairs[:3]:
            print(f'      {q[:40]}  ||  {bg[:40]}')
print()
print('==== 团队例会 工作进展 是否出现同名标题 ====')
for did, t in arts.items():
    if '# 例会概况' not in t: continue
    b = sec(t, '工作进展')
    print('  ', did[:8], '| 同名标题:', '## 工作进展' in b, '| 组标题:', re.findall(r'## (.+)', b)[:4])
