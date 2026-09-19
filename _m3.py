# -*- coding: utf-8 -*-
import pathlib, openpyxl
from app.config import template_registry
from tools.template_router._base import wrap_template_requirement
from tools.templates.length_budget import length_budget, capped_budget

wb = openpyxl.load_workbook('now.xlsx', read_only=True)
rows = list(wb['竞品对比'].iter_rows(min_row=2, values_only=True))
def han(s): return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
arts = {d.name: (d / 'result.md').read_text(encoding='utf-8')
        for d in pathlib.Path('data/test/output').iterdir() if (d / 'result.md').is_file()}

tpl_of = {}
for key, item in template_registry().items():
    t = wrap_template_requirement(str(item.get('format') or ''), str(item.get('requirement') or ''))
    cols = [l.strip()[2:].strip() for l in t.splitlines() if l.strip().startswith('# [' )]
    tpl_of[item.get('template') or key] = (t, cols)

want = [2, 6, 8, 13, 16, 18, 22, 23, 25, 26]
for i in want:
    r = rows[i-1]
    src = str(r[0] or '')
    cell = str(r[2] or '')
    sig = next((l.strip() for l in cell.splitlines() if l.strip() and not l.strip().startswith('#')), '')[:26]
    d = next((k for k, t in arts.items() if sig and sig in t), None)
    if not d:
        continue
    t = arts[d]
    src_han = han(src)
    print(f"第{i}条 {str(r[1] or '')}  源 {len(src)} 字符/{src_han} 汉字  档位 {length_budget(src_han)}  封顶 {capped_budget(src_han)}  产物 {han(t)} 汉字  ({d[:8]})")
    for l in t.splitlines():
        s = l.strip()
        if s.startswith('# ') and not s.startswith('## '):
            body = []
            on = False
            for l2 in t.splitlines():
                if l2.strip().startswith('# '):
                    on = l2.strip() == s
                    continue
                if on: body.append(l2)
            print(f"    {s[2:]:16s} {han(chr(10).join(body)):5d} 汉字")
    print()
