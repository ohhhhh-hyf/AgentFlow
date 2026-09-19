# -*- coding: utf-8 -*-
import openpyxl, pathlib, re
wb = openpyxl.load_workbook('now.xlsx', read_only=True)
rows = list(wb['竞品对比'].iter_rows(min_row=2, values_only=True))
arts = {}
for d in pathlib.Path('data/test/output').iterdir():
    f = d / 'result.md'
    if f.is_file():
        t = f.read_text(encoding='utf-8')
        first = next((l.strip() for l in t.splitlines() if l.strip()), '')
        arts[d.name] = (first, t)
want = [2, 6, 8, 13, 16, 18, 22, 23, 25, 26]
for i, r in enumerate(rows, start=1):
    if i not in want:
        continue
    text = str(r[2] or '')
    first = next((l.strip() for l in text.splitlines() if l.strip()), '')
    hit = next((k for k, (f2, _t) in arts.items() if f2 == first), None)
    print(f"{i:3d} {str(r[1] or ''):8s} dir={hit}  首行={first[:40]}")
