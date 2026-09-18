"""探针：栏序调整后字段顺序与预算解析。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.template_router._base import (  # noqa: E402
    split_template_meta,
    wrap_template_requirement,
)
from tools.template_router._placeholder import (  # noqa: E402
    build_placeholder_fill_user,
    plan_placeholder_fill,
)
from tools.templates.template_eval import (  # noqa: E402
    parse_document_char_budget,
    parse_section_char_budgets,
)

raw = Path("template_v3/general_minutes.md").read_text(encoding="utf-8")
body, req = split_template_meta(raw)
lines = body.splitlines()
for i, line in enumerate(lines):
    if line.startswith("# "):
        lines = lines[i + 1:]
        break
tpl = wrap_template_requirement("\n".join(lines).strip(), req)

plan = plan_placeholder_fill(tpl)
print("字段顺序:")
for s in plan["scalars"]:
    hint = str(s.get("hint") or "")
    print(f"  {s.get('title') or s.get('name') or s}  [{len(hint)} 字]")
print("doc_budget:", parse_document_char_budget(tpl).get("limit"))
print("budgets:", [(b["title"], b["lo"], b["hi"], b["scope"]) for b in parse_section_char_budgets(tpl)])
user = build_placeholder_fill_user("【占位上下文】", tpl)
print("速览在 prompt:", "不写 `- ` 分点" in user, "| 摘要先于速览:", user.find("关键数字进摘要") < user.find("不写 `- ` 分点") if "关键数字进摘要" in user else None)
