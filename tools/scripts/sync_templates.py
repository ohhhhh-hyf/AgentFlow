"""模板副本同步：以 YAML 为权威源，生成/校验 ``template/*.md`` 与 README 表。

权威源：项目根 ``cm_template_v2_changed_0722.yaml`` 的 ``cm-template-v2.templates``
（``visible: true`` 的条目 = 对外可填模板；``extra.template`` 取 **md 英文名**
（= 模板 ID，可带 ``.md``）或 **中文名**（``name``），见 ``app/config.template_key``）。

``template/`` 下的 ``.md`` 是各模板 ``format`` 的**可读副本**（文件名 = 模板 ID），
内容格式固定为：

    # {中文名}

    <!-- requirement
    {写作要求}
    -->

    {format 正文}

本脚本只做"结构对齐"：副本 = YAML 的 name + requirement + format 逐字渲染，
**不额外增补任何说法**（需要补充内容时改 YAML 的 ``detail``，再重跑本脚本）。

用法::

    python tools/scripts/sync_templates.py --check   # 只校验（CI/自测用；有漂移退出码 1）
    python tools/scripts/sync_templates.py --write    # 按 YAML 重写 template/*.md

``--check`` 同时校验 ``template/README.md`` 的 29 行模板表（order/场景/模板/中文名/API 值）
是否与 YAML 一致；不一致会打印差异但**不自动改 README**（避免动到文档正文，按提示手工同步）。
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_YAML = ROOT / "cm_template_v2_changed_0722.yaml"
TEMPLATE_DIR = ROOT / "template"
README_PATH = TEMPLATE_DIR / "README.md"

_TABLE_ROW_RE = re.compile(
    r"\|\s*(\d+)\s*\|\s*([a-z_]+)\s*\|\s*([a-z_]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*`([a-z_]+)`\s*\|"
)


def _leaf(value: object) -> str:
    """``${…template-ids.meeting-minutes.team-meeting}`` → ``team_meeting``。"""
    return str(value or "").rsplit(".", 1)[-1].rstrip("}").replace("-", "_")


def load_templates() -> list[dict[str, object]]:
    """读权威 YAML → 可见模板列表（按 order 升序，带 API 取值 key）。"""
    try:
        import yaml
    except Exception as exc:  # noqa: BLE001 - 缺 pyyaml 时给出可执行的提示
        raise SystemExit(f"需要 pyyaml 解析 {TEMPLATE_YAML.name}：{exc}")
    if not TEMPLATE_YAML.is_file():
        raise SystemExit(f"权威源不存在：{TEMPLATE_YAML}")
    raw = yaml.safe_load(TEMPLATE_YAML.read_text(encoding="utf-8")) or {}
    root = raw.get("cm-template-v2") or {}
    items: list[dict[str, object]] = []
    for tpl in root.get("templates") or []:
        if not tpl.get("visible", True):
            continue
        scenario = _leaf(tpl.get("scenario-id"))
        template = _leaf(tpl.get("id"))
        items.append(
            {
                "order": int(tpl.get("order") or 0),
                "scenario": scenario,
                "template": template,
                "key": f"{scenario}_{template}",
                "name": str(tpl.get("name") or "").strip(),
                "description": str(tpl.get("description") or "").strip(),
                "requirement": str(tpl.get("requirement") or "").strip(),
                "format": str(tpl.get("format") or "").strip(),
            }
        )
    items.sort(key=lambda item: int(item["order"] or 0))
    return items


def render_copy(item: dict[str, object]) -> str:
    """模板副本的完整内容（与既有 29 个副本逐字一致；不要在这里加额外说法）。"""
    return (
        f"# {item['name']}\n\n"
        f"<!-- requirement\n{item['requirement']}\n-->\n\n"
        f"{item['format']}\n"
    )


def check_copies(items: list[dict[str, object]]) -> list[str]:
    """校验 29 个副本与 YAML 渲染结果逐字一致；返回问题列表（空 = 一致）。"""
    problems: list[str] = []
    for item in items:
        path = TEMPLATE_DIR / f"{item['template']}.md"
        if not path.is_file():
            problems.append(f"{path.name}：副本缺失")
            continue
        current = path.read_text(encoding="utf-8")
        want = render_copy(item)
        if current == want:
            continue
        diff = [
            line
            for line in difflib.unified_diff(
                current.splitlines(), want.splitlines(), "现有副本", "按 YAML 生成", lineterm="", n=0
            )
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        head = "；".join(d.strip()[:40] for d in diff[:2]) or "内容不同"
        problems.append(f"{path.name}：{head}")
    return problems


def check_readme(items: list[dict[str, object]]) -> list[str]:
    """校验 README 的模板表与 YAML 一致（order / 场景ID / 模板ID / 中文名 / API 可填值）。

    最后一列 = ``extra.template`` 可填的 **md 英文名**（= 模板 ID），与 YAML ``id`` 一致。
    """
    if not README_PATH.is_file():
        return [f"{README_PATH.name}：不存在"]
    rows = {
        int(m.group(1)): {
            "scenario": m.group(2),
            "template": m.group(3),
            "name": m.group(4).strip(),
            "api": m.group(6),
        }
        for m in _TABLE_ROW_RE.finditer(README_PATH.read_text(encoding="utf-8"))
    }
    problems: list[str] = []
    if len(rows) != len(items):
        problems.append(f"README 表 {len(rows)} 行 vs YAML {len(items)} 条")
    for item in items:
        row = rows.get(int(item["order"] or 0))
        if not row:
            problems.append(f"README 缺 order {item['order']}（{item['key']}）")
            continue
        if (row["name"], row["api"], row["scenario"], row["template"]) != (
            item["name"], item["template"], item["scenario"], item["template"]
        ):
            problems.append(
                f"order {item['order']}：README={row['api']} {row['name']!r} vs YAML={item['template']} {item['name']!r}"
            )
    return problems


def write_copies(items: list[dict[str, object]]) -> int:
    """按 YAML 重写副本；返回改动文件数。"""
    changed = 0
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        path = TEMPLATE_DIR / f"{item['template']}.md"
        want = render_copy(item)
        if path.is_file() and path.read_text(encoding="utf-8") == want:
            continue
        path.write_text(want, encoding="utf-8")
        print(f"[write] {path.relative_to(ROOT)}")
        changed += 1
    return changed


def _expired_pairs() -> list[tuple[str, str]]:
    """YAML 里"已过期 → 建议替代"的映射（供排查旧客户端用了过期 template 值）。"""
    import yaml

    root = yaml.safe_load(TEMPLATE_YAML.read_text(encoding="utf-8"))["cm-template-v2"]
    pairs: list[tuple[str, str]] = []
    for row in root.get("expired-templates") or []:
        if isinstance(row, dict):
            pairs.append((_leaf(row.get("expired-id")), _leaf(row.get("replaced-id"))))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="按权威 YAML 同步/校验 template/*.md 与 README 表")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只校验，不写文件（有漂移退出码 1）")
    group.add_argument("--write", action="store_true", help="按 YAML 重写 template/*.md")
    args = ap.parse_args()

    items = load_templates()
    print(f"权威源：{TEMPLATE_YAML.name} → 可见模板 {len(items)} 条")
    expired = _expired_pairs()
    if expired:
        print("已过期（旧客户端传入会 400，建议改用替代项）：")
        for old, new in expired:
            print(f"  - {old or '(空)'} → {new or '(空)'}")

    if args.write:
        changed = write_copies(items)
        print(f"OK：副本已同步（改动 {changed} 个文件）")
        problems = check_copies(items) + check_readme(items)
        for problem in problems:
            print(f"  仍不一致：{problem}", file=sys.stderr)
        return 1 if problems else 0

    problems = check_copies(items) + check_readme(items)
    if not problems:
        print("OK：template/*.md 与 README 表均与 YAML 一致")
        return 0
    print(f"发现 {len(problems)} 处漂移（跑 --write 同步副本；README 需手工同步）：", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
