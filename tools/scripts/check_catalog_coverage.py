"""目录覆盖/顺序校验（零 LLM，只读）：原文骨架 ↔ 目录节点。

口径（P2 起以**原文骨架**为参照，不再用入库标题的分数分层）：

- **覆盖**：骨架里每个 T（主题）/ P（知识点）都要在目录里找得到——
  名字出现在任意层级节点名，或出现在某个知识点的 ``knowledge_items`` 里（= 降级）都算覆盖；
  主题另外允许"其下知识点全部还在、只是被并进别的主题"（= 合并）；
- **顺序**：目录遍历顺序里，能对齐的节点的骨架 order 必须非递减（逆序对数应为 0）；
- 细碎标题（例题/易错/小结…）按口径**不建节点**，脚本单独报数量，不算缺口。

    python tools/scripts/check_catalog_coverage.py --user 1 --subject wuli
    python tools/scripts/check_catalog_coverage.py --user 1 --subject wuli \
        --md data/1/ocr/wuli/ocr_20260915_155322.md \
        --catalog data/1/knowledge/catalogs/wuli/20260915_155513_104.json

退出码：0 = 覆盖 100% 且顺序单调；1 = 有缺口/逆序；2 = 文件找不到。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.config import load_env  # noqa: E402

load_env(ROOT / ".env")

from domain.notes.tasks.catalog.skeleton import (  # noqa: E402
    catalog_quality_report as evaluate,
    parse_md_skeleton,
)
from tools.memory.store import safe_id  # noqa: E402


def _latest(pattern: str, folder: Path) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def skeleton_of(args) -> tuple[dict, Path | None]:
    """显式 --md 时用它；否则取该用户/学科下最新的合并稿。"""
    if args.md:
        path = Path(args.md)
        if not path.is_file():
            print(f"找不到合并稿：{path}")
            return {}, None
        return parse_md_skeleton(path.read_text(encoding="utf-8"), source=path.name), path
    uid, subject = safe_id(args.user), safe_id(args.subject)
    folder = ROOT / "data" / uid / "ocr" / subject
    path = _latest("ocr_*.md", folder)
    if path is None:
        print(f"找不到合并稿：data/{uid}/ocr/{subject}/ocr_*.md")
        return {}, None
    return parse_md_skeleton(path.read_text(encoding="utf-8"), source=path.name), path


def catalog_of(args, sk: dict) -> Path | None:
    if args.catalog:
        path = Path(args.catalog)
        if not path.is_file():
            print(f"找不到目录文件：{path}")
            return None
        return path
    uid, subject = safe_id(args.user), safe_id(args.subject)
    path = _latest("*.json", ROOT / "data" / uid / "knowledge" / "catalogs" / subject)
    if path is None:
        print(f"找不到目录文件：data/{uid}/knowledge/catalogs/{subject}/*.json")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="目录覆盖/顺序校验（骨架为参照）")
    ap.add_argument("--user", default="", help="user_id（与 X-User-Id 一致）")
    ap.add_argument("--subject", default="", help="学科拼音，如 wuli")
    ap.add_argument("--md", default="", help="合并稿路径（默认取最新）")
    ap.add_argument("--catalog", default="", help="catalog JSON 路径（默认取最新）")
    ap.add_argument("--limit", type=int, default=40, help="最多打印多少条未覆盖项")
    args = ap.parse_args()

    sk, md_path = skeleton_of(args)
    if not sk.get("topics"):
        print("骨架为空（原文不可读或没有标题）。")
        return 2
    cat_path = catalog_of(args, sk)
    if cat_path is None:
        return 2
    data = json.loads(cat_path.read_text(encoding="utf-8"))
    data = data.get("data") if isinstance(data.get("data"), dict) else data

    report = evaluate(sk, data)
    nodes = report["nodes"]
    print(f"合并稿 : {md_path.name}（{len(sk['topics'])} 主题 / {sk['stats']['points']} 知识点"
          f"，细碎标题忽略 {sk['stats']['dropped_item_headings']} 个）")
    print(f"目录   : {cat_path.name}（章 {sum(1 for n in nodes if n['level'] == '章')} / "
          f"主题 {sum(1 for n in nodes if n['level'] == '主题')} / "
          f"KP {sum(1 for n in nodes if n['level'] == 'KP')}）")
    print(f"\n覆盖率 : {report['total'] - report['missed']}/{report['total']} "
          f"= {100 * report['coverage']:.1f}%"
          f"（降级为 items {len(report['demoted'])} 个，主题被合并 {len(report['merged_topics'])} 个，"
          f"均计入覆盖）")
    if report["uncovered_topics"]:
        print(f"缺主题 : {len(report['uncovered_topics'])} 个（目录里完全没有，也没降级）")
        for name in report["uncovered_topics"][: args.limit]:
            print(f"  - {name}")
    if report["uncovered_points"]:
        print(f"缺知识点: {len(report['uncovered_points'])} 个")
        for name in report["uncovered_points"][: args.limit]:
            print(f"  - {name}")
    print(f"\n顺序   : 同级单调检查（章 {len([c for c in data.get('chapters') or [] if isinstance(c, dict)])} 个 / "
          f"可对齐节点 {report['aligned']} 个；原文重复名 {len(report['dup_names'])} 个不参与判定）")
    if report["level_violations"]:
        for line in report["level_violations"][:10]:
            print(f"  ✗ {line}")
    else:
        print("  ✓ 章按最早位置、章内主题按 order、主题内 KP 按 order 均单调")
    if report["cross_jumps"]:
        print(f"  跨层回退 {len(report['cross_jumps'])} 处（信息性，来自续页合并等原文结构）：")
        for prev_pos, cur_pos, name in report["cross_jumps"][:5]:
            print(f"    · {name!r}：位置 {cur_pos} 出现在位置 {prev_pos} 之后")
    content = report.get("content") or {}
    misplaced = content.get("misplaced_nodes") or []
    unverified = content.get("unverified") or []
    checked = int(content.get("checked") or 0)
    strong = int(content.get("strong") or 0)
    weak = int(content.get("weak") or 0)
    print(f"\n内容   : 核对 items {checked} 条 → 逐字命中 {strong}、概述型 {weak}"
          f"，短标签(无法逐字核对) {int(content.get('labels') or 0)}，整节串门 {len(misplaced)}，长条目存疑 {len(unverified)}")
    for entry in misplaced[: args.limit]:
        print(f"  · 串门：{entry['point']!r} 的 {entry['items']}/{entry['matched']} 条 item"
              f" 更像 {entry['belongs_to']!r} 那节")
    for entry in unverified[: args.limit]:
        print(f"  · 存疑：{entry['point']!r} 的 item {entry['item']!r}（全篇找不到依据）")
    print(f"\n一行摘要: {report['metrics']}")
    hard = "覆盖 100%、同级顺序单调 ✓" if report["ok"] else "存在缺口/乱序 ✗"
    soft = (
        f"；内容提示 {len(misplaced) + len(unverified)} 项（只报告，不删改目录内容）"
        if (misplaced or unverified) else ""
    )
    print(f"\n结论   : {hard}{soft}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
