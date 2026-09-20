# -*- coding: utf-8 -*-
import pathlib, re, openpyxl
from app.config import template_registry
from tools.template_router._base import wrap_template_requirement
from tools.execution.hard_execution import gate_render_output
from tools.templates.template_eval import parse_section_char_budgets

def han(s): return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
tpls = {}
for key, item in template_registry().items():
    t = wrap_template_requirement(str(item.get('format') or ''), str(item.get('requirement') or ''))
    tpls[item.get('template') or key] = t

wb = openpyxl.load_workbook('now.xlsx', read_only=True)
rows = list(wb['竞品对比'].iter_rows(min_row=2, values_only=True))
arts = {}
for d in sorted(pathlib.Path('data/test/output').iterdir()):
    f = d / 'result.md'
    if f.is_file():
        arts[d.name] = f.read_text(encoding='utf-8')

def sig(cell):
    ls = [l.strip() for l in str(cell or '').splitlines() if l.strip() and not l.strip().startswith('#')]
    return ls[0][:26] if ls else ''

print(f"{'条':>3} {'场景':10s} {'产物汉字':>6s} {'档位下限':>6s} {'硬伤':>4s} {'软提示':>4s}  {'超/低于下限'}")
stat = {}
for i, r in enumerate(rows, 1):
    scene = str(r[1] or '')
    cell = str(r[2] or '')
    src = str(r[0] or '')
    if not cell.strip():
        continue
    s = sig(cell)
    did = next((k for k, t in arts.items() if s and s in t), None)
    if not did:
        print(f"{i:3d} {scene:10s}  —— 未匹配"); continue
    t = arts[did]
    total = han(t)
    first_col = next((l for l in t.splitlines() if l.strip().startswith('# ')), '')
    tpl_key = next((k for k, tp in tpls.items() if f"# [{first_col[2:].strip()}]" in tp or f"# {first_col[2:].strip()}" in tp), None)
    hard = soft = '-'
    if tpl_key:
        g = gate_render_output(tpls[tpl_key], t)
        hard = len(g['hard_issues']); soft = len(g['soft_issues'])
    from tools.templates.length_budget import effective_doc_budget
    span = effective_doc_budget(han(src))
    lo = span[0] if span else 0
    flag = ''
    if lo and total < lo * 0.85: flag = f'低于下限 {total}/{lo}'
    elif span and total > span[1] * 1.2: flag = f'超上限 {total}/{span[1]}'
    stat.setdefault(scene, []).append((total, bool(flag)))
    print(f"{i:3d} {scene:10s} {total:6d} {lo:6d} {hard:>4} {soft:>4}  {flag}{' ['+str(tpl_key)+']' if tpl_key else ''}")
print()
print('==== 场景汇总（平均汉字 / 触发下限或上限比例）====')
for scene, v in sorted(stat.items(), key=lambda kv: -len(kv[1])):
    avg = sum(x for x, _ in v) // len(v)
    bad = sum(1 for _, f in v if f)
    print(f'  {scene:10s} n={len(v):2d} 平均 {avg:5d} 汉字 | 越界 {bad}/{len(v)}')
