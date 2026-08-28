"""meeting_all.txt 真实调用基准：minutes / actions / risks / minutes_trace。

对比：monitor.token_usage / cost_time / 待办条数 / 风险条数。
minutes_trace 补 keypoints/notes（从原文提取相关句）。
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
USER = "1"

transcript = Path("samples/meeting/file/meeting_all.txt").read_text(encoding="utf-8").strip()
print(f"meeting_all.txt 长度: {len(transcript)} 字\n")

KEYPOINTS = "关注会议纪要、待办提取、风险分析这几条主线的输出质量，以及记忆溯源是否可解释"
NOTES = "小艺慧记Agent内测前要收口的事项和风险，特别是支付模块联调阻塞、检索服务并发延迟"

CASES = [
    ("minutes", "/api/v1/meeting/minutes",
     {"texts": {"transcript": transcript}}),
    ("actions", "/api/v1/meeting/actions",
     {"texts": {"transcript": transcript}}),
    ("risks", "/api/v1/meeting/risks",
     {"texts": {"transcript": transcript}}),
    ("minutes_trace", "/api/v1/meeting/minutes_trace",
     {"texts": {"transcript": transcript, "keypoints": KEYPOINTS, "notes": NOTES}}),
]

results = {}
for name, path, body in CASES:
    start = time.time()
    resp = requests.post(f"{BASE}{path}", headers={"X-User-Id": USER, "X-Request-Id": f"bench-{name}"}, json=body, timeout=600)
    wall = round(time.time() - start, 1)
    data = resp.json()
    monitor = data.get("monitor") or {}
    text = (data.get("data") or {}).get("text") or ""
    print(f"[{name}] HTTP {resp.status_code} | code={data.get('code')} | 墙钟 {wall}s")
    print(f"    monitor: token_usage={monitor.get('token_usage')} cache_hit={monitor.get('cache_hit')} cost_time={monitor.get('cost_time')}s")
    print(f"    data 长度: {len(text)}")
    if name == "actions":
        # 数待办条目（编号行或含负责人/截止的行）
        items = [l for l in text.splitlines() if l.strip() and (l.strip()[0].isdigit() or "负责" in l or "截止" in l)]
        print(f"    待办条目数(粗): {len(items)}")
    if name == "risks":
        # 数风险条目（严重度关键词）
        sev = sum(1 for kw in ["高", "中", "低"] for _ in [0])
        lines = [l for l in text.splitlines() if any(k in l for k in ["严重", "风险", "高", "中", "低"])]
        print(f"    风险相关行数(粗): {len(lines)}")
    results[name] = {
        "http": resp.status_code, "code": data.get("code"),
        "monitor": monitor, "wall": wall, "text_len": len(text),
    }
    print()

out = Path("bench_meeting_all.json")
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已保存: {out}")
