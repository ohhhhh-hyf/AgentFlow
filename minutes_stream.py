"""流式请求 minutes 接口（NDJSON 事件流）。用法：python minutes_stream.py

请求体与 minutes.py（同步）完全一致，只是端点换成 /stream；
响应为逐行 NDJSON，每行一个事件：
  {"type": "phase", "node": ...}                      编排节点（如 生成/审核/渲染）
  {"type": "chunk", "line": ..., "title": ..., "text": ...}   渲染文本增量（按行追加显示）
  {"type": "done", "code": 0, "request_id": ..., "quality_warning": ...,
     "monitor": {...}, "data": {...}}                 最终结果（与同步响应同构）
  {"type": "error", "code": 500, "message": ...}       运行失败
校验失败（缺必填字段等）不走流，直接返回 HTTP 错误。
"""
import json
import sys
import uuid
from pathlib import Path

import requests

# ── 会议转写文本（三引号内直接粘贴）──
TRANSCRIPT = """
"""

URL = "http://127.0.0.1:8000/api/v1/meeting/minutes/stream"
USER_ID = "1"

if not TRANSCRIPT.strip():
    print("请先把会议转写文本粘贴到 TRANSCRIPT（与 minutes.py 用法一致）")
    raise SystemExit(1)

resp = requests.post(
    URL,
    json={
        "time": "",
        "texts": {
            "transcript": TRANSCRIPT,
            "keypoints": "",
            "notes": "",
        },
        "docs": [],
        "extra": {
            "template": "",
            "profile": "",
            "project": "",
            "subject": "",
            "style": "",
            "memory": False,
        },
    },
    headers={"X-Request-Id": uuid.uuid4().hex, "X-User-Id": USER_ID},
    stream=True,
    timeout=600,
)

print("HTTP", resp.status_code)
if resp.status_code != 200:
    print(resp.text[:500])
    raise SystemExit(1)

done = None
text_parts: list[str] = []
for raw in resp.iter_lines(decode_unicode=True):
    if not raw:
        continue
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        continue
    etype = event.get("type")
    if etype == "phase":
        print(f"\n[节点] {event.get('node') or ''}")
    elif etype == "chunk":
        piece = event.get("text") or ""
        if piece:
            text_parts.append(piece)
            print(piece, end="", flush=True)
    elif etype == "done":
        done = event
        monitor = event.get("monitor") or {}
        d = event.get("data") or {}
        print()
        print("code       :", event.get("code"))
        print("request_id :", event.get("request_id"))
        print("message    :", event.get("message"))
        print("quality    :", event.get("quality_warning") or "无")
        print("token      :", monitor.get("token_usage"), "| cache:", monitor.get("cache_hit"),
              "| cost:", monitor.get("cost_time"), "s")
        print("file_name  :", d.get("file_name"))
    elif etype == "error":
        print(f"\n[失败] code={event.get('code')} message={event.get('message')}")
        raise SystemExit(1)

if done is not None:
    d = done.get("data") or {}
    if text_parts:
        Path("data_minutes_stream_response.json").write_text(
            json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已保存完整响应：data_minutes_stream_response.json（正文 {len(''.join(text_parts))} 字符）")
    else:
        print("响应中没有渲染增量（任务可能被降级），data.text 见保存文件")
else:
    print("连接提前结束，未收到 done 事件")
