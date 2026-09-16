"""扫一批会议纪要产出，查两类"产品级问题"（离线评估用，不调 LLM、不改文件）:

1. **元说明句**：把模板要求/占位说明复述进正文（如「以上均未明确责任人和时间，填写"无"。」
   「某栏主题在来源中完全无信息时才「未提及」」）——已知发生过一次，靠正则兜底复查。
2. **压缩比异常**：纪要字数 ÷ 原文汉字数。中位数一般 20–30%；
   ≥50% 说明"纪要≈缩写全文"，短材料（<5000 字）上尤其要盯。

用法::

    # 扫工作簿（默认 test_sample.xlsx：A=原文、C=纪要、D=耗时、E=文本长度）
    python tools/scripts/scan_minutes_output.py
    python tools/scripts/scan_minutes_output.py --file 其它.xlsx --sheet Sheet1
    python tools/scripts/scan_minutes_output.py --col-src 1 --col-out 3 --start 2 --end 56

    # 扫纯文本（每行一条纪要；无原文时只查元说明句、不算压缩比）
    python tools/scripts/scan_minutes_output.py --text output/xxx/minutes.md

退出码：0 = 没发现问题；1 = 有命中（元说明句 / 压缩比 ≥ 阈值 / 失败标记）。
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

# 元说明句模式：正文在"讲要求本身"而不是纪要内容
META_PATTERNS = (
    r"以上.{0,24}(均|都)未",
    r"填写[「\"]?无",
    r"均无明确",
    r"未明确责任人和时间",
    r"禁止编造",
    r"不得编造",
    r"若原文未",
    r"如原文未",
    r"原文若无",
    r"无信息时才",
    r"信息不足时按",
    r"按模板(要求)?填写",
    r"按要求填写",
    r"如实填写",
    r"按上述要求",
    r"(本栏|该栏)(无内容|未提及)",
    r"占位(符)?(说明|处)",
)
META_RE = re.compile("|".join(META_PATTERNS))
FAIL_PREFIXES = ("[失败]", "[跳过]")

# 误报白名单：命中词出现在这些语境里属正常内容（如讨论 UI 占位、禁止编造类业务要求）
FALSE_POSITIVE_HINTS = ("UI 占位", "UI占位", "接口逻辑和", "图片占位", "广告位")


def scan_text(text: str) -> list[str]:
    """返回疑似元说明句（已滤掉明显误报）。"""
    hits: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or any(h in line for h in FALSE_POSITIVE_HINTS):
            continue
        if META_RE.search(line):
            hits.append(line[:120])
    return hits


def han_count(text: str) -> int:
    return sum(1 for ch in text or "" if "\u4e00" <= ch <= "\u9fff")


def scan_workbook(path: Path, sheet: str, col_src: int, col_out: int, col_elapsed: int, start: int, end: int, ratio: float) -> int:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    print(f"工作簿：{path.name}（sheet={ws.title}，行 {start}–{end}）")

    filled: dict[int, tuple[str, str]] = {}
    missing: list[int] = []
    failures: list[tuple[int, str]] = []
    meta_hits: list[tuple[int, str]] = []
    for row in range(start, end + 1):
        src = str(ws.cell(row=row, column=col_src).value or "")
        out = str(ws.cell(row=row, column=col_out).value or "").strip()
        if out.startswith(FAIL_PREFIXES):
            failures.append((row, out[:60]))
            continue
        if not out:
            missing.append(row)
            continue
        filled[row] = (src, out)
        for hit in scan_text(out):
            meta_hits.append((row, hit))

    print(f"覆盖：{len(filled)} 行有纪要；空行 {missing or '无'}；失败/跳过标记 {failures or '无'}")
    print(f"元说明句：{len(meta_hits)} 处")
    for row, hit in meta_hits:
        print(f"   行{row}：{hit}")

    ratios = [(row, len(out) / len(src), len(src), len(out)) for row, (src, out) in filled.items() if src]
    if ratios:
        vals = [r for _, r, _, _ in ratios]
        print(f"压缩比（纪要/原文）：中位数 {statistics.median(vals) * 100:.1f}%｜均值 {statistics.mean(vals) * 100:.1f}%")
        high = sorted([x for x in ratios if x[1] >= ratio], key=lambda x: -x[1])
        print(f"压缩比 ≥{ratio * 100:.0f}%：{len(high)} 行")
        for row, r, src_n, out_n in high[:10]:
            print(f"   行{row}：原文 {src_n} → 纪要 {out_n} = {r * 100:.0f}%")
    return 1 if (meta_hits or failures or (ratios and any(r >= ratio for _, r, _, _ in ratios))) else 0


def scan_plain_text(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    hits = scan_text(text)
    print(f"文本：{path}（{han_count(text)} 汉字）")
    print(f"元说明句：{len(hits)} 处")
    for hit in hits:
        print(f"   {hit}")
    return 1 if hits else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描会议纪要产出：元说明句 + 压缩比异常")
    ap.add_argument("--file", default="test_sample.xlsx", help="工作簿（默认 test_sample.xlsx）")
    ap.add_argument("--text", default="", help="改为扫单份纪要文本（md/txt）")
    ap.add_argument("--sheet", default="", help="sheet 名（默认第一个）")
    ap.add_argument("--col-src", type=int, default=1, help="原文列（默认 1 = A）")
    ap.add_argument("--col-out", type=int, default=3, help="纪要列（默认 3 = C）")
    ap.add_argument("--col-elapsed", type=int, default=4, help="耗时列（默认 4 = D）")
    ap.add_argument("--start", type=int, default=2, help="起始行（默认 2）")
    ap.add_argument("--end", type=int, default=56, help="结束行（默认 56）")
    ap.add_argument("--ratio", type=float, default=0.5, help="压缩比告警阈值（默认 0.5）")
    args = ap.parse_args()

    if args.text:
        return scan_plain_text(Path(args.text).resolve())
    path = Path(args.file).resolve()
    if not path.is_file():
        print(f"✗ 找不到文件：{path}", file=sys.stderr)
        return 2
    return scan_workbook(path, args.sheet, args.col_src, args.col_out, args.col_elapsed, args.start, args.end, args.ratio)


if __name__ == "__main__":
    raise SystemExit(main())
