"""批量跑 minutes 接口 (同步模式)：读 Excel 会议文本 + 模板名，纪要写回第三列。
完全自包含，零旧代码依赖，适配 demo 独立工程。

表格约定（默认读第一个 sheet）：
| 行 | A | B | C | D | E |
|---|---|---|---|---|---|
| 1 | 文本 | 场景 | 纪要 | 消耗时间 | 文本长度 |
| 2–56 | 会议文本 | 模板中文名（或 md 英文名） | 生成的纪要 | 接口耗时（秒） | 原文/纪要 字数 |

用法::
    python api_test/test.py --dry-run     # 只校验表格与模板名，不发请求
    python api_test/test.py --limit 1     # 先跑 1 行试水
    python api_test/test.py               # 跑待处理行
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import requests
from openpyxl import load_workbook

# 自动定位 demo 项目根目录
DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from tasks.minutes.classifier.catalog import SCENE_CATALOG

FAIL_PREFIX = "[失败]"
SKIP_PREFIX = "[跳过]"
DEFAULT_SHEET = ""


def make_template_resolver():
    """模板名合法性校验与推荐 (支持 29 种场景的英文 ID 与中文名称)."""
    id_set = {entry.id for entry in SCENE_CATALOG}
    name_set = {entry.name for entry in SCENE_CATALOG}
    id_set.add("general_minutes")
    name_set.add("通用纪要")
    name_set.add("常规纪要")

    all_tokens = sorted(id_set | name_set)

    def resolve(value: str) -> bool:
        v = (value or "").strip()
        if not v or v.lower() in ("auto", "none", "默认", "自动"):
            return True
        v_clean = v[:-3] if v.lower().endswith(".md") else v
        if v_clean.lower() in id_set or v_clean in name_set:
            return True
        if any(kw in v for kw in ("通用", "常规", "综合", "普通", "general")):
            return True
        return False

    def suggest(value: str) -> str:
        v = (value or "").strip()
        v_clean = v[:-3] if v.lower().endswith(".md") else v
        hit = difflib.get_close_matches(v_clean, all_tokens, n=1, cutoff=0.3)
        return hit[0] if hit else "general_minutes"

    return resolve, suggest


def save_workbook(wb, out: Path) -> bool:
    """安全保存工作簿."""
    try:
        wb.save(out)
        return True
    except PermissionError:
        print(f"✗ 无法写入 {out.name}：文件被其它程序占用（通常是 Excel 正打开着）。\n"
              f"  请先关闭该文件再重跑；或临时写到别处：--out {out.with_name(out.stem + '.new' + out.suffix).name}", flush=True)
        return False


def build_payload(transcript: str, template: str, date: str) -> dict:
    """构建与 demo 服务端完全对齐的严格请求体."""
    return {
        "task": "minutes",
        "texts": {
            "transcript": transcript,
            "keypoints": "",
            "notes": "",
            "vision_info": "",
            "actions_text": "",
        },
        "docs": [],
        "extra": {
            "template": template,
            "time": date,
            "agenda_plan": None,
        },
        "lang": "zh",
    }


def call_minutes(url: str, transcript: str, template: str, date: str, user: str, timeout: int) -> tuple[bool, str, str, int]:
    """通过同步接口调一次 minutes."""
    try:
        resp = requests.post(
            url,
            json=build_payload(transcript, template, date),
            headers={"X-Request-Id": uuid.uuid4().hex, "X-User-Id": user},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"请求异常：{exc}", "", 0

    try:
        body = resp.json()
    except ValueError:
        return False, f"HTTP {resp.status_code} 非 JSON 响应：{resp.text[:200]}", "", 0

    monitor = body.get("monitor") or {}
    token_usage = monitor.get("token_usage", 0)
    token_n = int(token_usage) if isinstance(token_usage, (int, float)) else 0
    stats = "耗时=%ss" % (monitor.get("cost_time"))
    data = body.get("data") or {}
    text = str(data.get("content") or data.get("text") or "").strip()

    if resp.status_code == 200 and str(body.get("code")) == "0" and text:
        return True, text, stats, token_n
    return False, f"HTTP {resp.status_code} code={body.get('code')} message={body.get('message')}", stats, token_n


def main() -> int:
    ap = argparse.ArgumentParser(description="Excel 批量同步生成会议纪要脚本")
    ap.add_argument("--file", default=str(DEMO_ROOT / "now.xlsx"), help="输入工作簿")
    ap.add_argument("--sheet", default=DEFAULT_SHEET, help="sheet 名")
    ap.add_argument("--start", type=int, default=2, help="起始行（默认 2）")
    ap.add_argument("--end", type=int, default=56, help="结束行（默认 56）")
    ap.add_argument("--col-text", type=int, default=1, help="文本列（默认 1 = A）")
    ap.add_argument("--col-template", type=int, default=2, help="模板列（默认 2 = B）")
    ap.add_argument("--col-out", type=int, default=3, help="纪要列（默认 3 = C）")
    ap.add_argument("--col-elapsed", type=int, default=4, help="消耗时间列（默认 4 = D）")
    ap.add_argument("--col-len", type=int, default=5, help="文本长度列（默认 5 = E）")
    ap.add_argument("--out", default="", help="输出工作簿")
    ap.add_argument("--base-url", default=os.getenv("AGENTFLOW_BASE_URL", "http://127.0.0.1:8000"), help="服务地址")
    ap.add_argument("--path", default="/api/agent/v1", help="接口路径")
    ap.add_argument("--user", default="test", help="X-User-Id")
    ap.add_argument("--date", default="", help="会议时间")
    ap.add_argument("--timeout", type=int, default=1800, help="单请求超时秒数")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 行")
    ap.add_argument("--force", action="store_true", help="强制覆盖已生成行")
    ap.add_argument("--dry-run", action="store_true", help="只校验不发请求")
    args = ap.parse_args()

    src = Path(args.file).resolve()
    out = Path(args.out).resolve() if args.out else src
    if not src.is_file():
        print(f"✗ 找不到输入文件：{src}", flush=True)
        return 2

    wb = load_workbook(src)
    ws = wb[args.sheet] if args.sheet else wb[wb.sheetnames[0]]
    print(f"工作簿：{src.name}（sheet={ws.title}，共 {ws.max_row} 行 × {ws.max_column} 列）", flush=True)
    print(f"接口：{args.base_url}{args.path}｜X-User-Id={args.user}｜行 {args.start}–{args.end}", flush=True)

    resolve, suggest = make_template_resolver()

    pending: list[tuple[int, str, str]] = []
    skipped_invalid: list[tuple[int, str, str]] = []
    skipped_done = 0

    for row in range(args.start, args.end + 1):
        transcript = str(ws.cell(row=row, column=args.col_text).value or "").strip()
        template = str(ws.cell(row=row, column=args.col_template).value or "").strip()
        current = str(ws.cell(row=row, column=args.col_out).value or "").strip()
        if not transcript and not template:
            continue
        if not transcript:
            skipped_invalid.append((row, template, "文本列为空"))
            continue
        if current and not current.startswith((FAIL_PREFIX, SKIP_PREFIX)) and not args.force:
            skipped_done += 1
            ws.cell(row=row, column=args.col_len, value=f"{len(transcript)}/{len(current)}")
            continue
        if not resolve(template):
            tip = suggest(template)
            skipped_invalid.append((row, template, f"模板名无效（推荐: {tip}）"))
            continue
        pending.append((row, transcript, template))

    for row, template, why in skipped_invalid:
        print(f"  {SKIP_PREFIX} 行{row} 模板={template!r}：{why}", flush=True)
    print(f"预检：待处理 {len(pending)} 行｜已完成跳过 {skipped_done} 行｜无效跳过 {len(skipped_invalid)} 行", flush=True)

    if args.dry_run:
        print("dry-run 校验完成：未发请求、未写文件。")
        return 0

    if not pending:
        print("没有待处理行。")
        return 0

    if args.limit:
        pending = pending[: args.limit]

    # 写表头并备份
    for col, title in (
        (args.col_out, "纪要"),
        (args.col_elapsed, "消耗时间"),
        (args.col_len, "文本长度"),
    ):
        if str(ws.cell(row=1, column=col).value or "").strip() != title:
            ws.cell(row=1, column=col, value=title)
    if out == src:
        backup = src.with_suffix(".bak.xlsx")
        if not backup.is_file():
            shutil.copy2(src, backup)
            print(f"已备份原表：{backup.name}", flush=True)
    save_workbook(wb, out)

    url = f"{args.base_url}{args.path}"
    ok = fail = 0

    for row, transcript, template in pending:
        t0 = time.time()
        success, text, stats, _ = call_minutes(
            url=url,
            transcript=transcript,
            template=template,
            date=args.date,
            user=args.user,
            timeout=args.timeout,
        )
        elapsed = round(time.time() - t0, 2)
        if success:
            ok += 1
            ws.cell(row=row, column=args.col_out, value=text)
            ws.cell(row=row, column=args.col_elapsed, value=elapsed)
            ws.cell(row=row, column=args.col_len, value=f"{len(transcript)}/{len(text)}")
            print(f"  ✓ 行{row} 成功｜{stats}｜{len(transcript)}字→{len(text)}字", flush=True)
        else:
            fail += 1
            ws.cell(row=row, column=args.col_out, value=f"{FAIL_PREFIX} {text}")
            ws.cell(row=row, column=args.col_elapsed, value=elapsed)
            print(f"  ✗ 行{row} 失败：{text}", flush=True)

        save_workbook(wb, out)

    print(f"\n全部处理完毕：成功 {ok} 行，失败 {fail} 行，结果已保存至 {out.name}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
