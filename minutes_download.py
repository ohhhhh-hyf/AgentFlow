"""下载 minutes 产物文件（GET）。用法：python minutes_download.py

先跑 minutes.py 生成纪要，把响应里的 request_id 填到下方 REQUEST_ID；
运行后把 minutes.html（页面版）以附件形式下载到当前目录。
FILE_NAME 换成 minutes.md 可下载 Markdown 文本版。
"""
import json
from pathlib import Path

import requests

# ── 请求参数 ──
REQUEST_ID = "8159654c537e4ceab2b569eb42f17d1a"   # ← 自己填：POST /api/v1/meeting/minutes 响应里的 request_id
USER_ID = "1"     # 产物按用户隔离（POST 时 X-User-Id 传的谁就填谁）
FILE_NAME = "minutes.html"   # minutes.html（页面版）/ minutes.md（Markdown 文本），二选一

# 下载端点（GET，附件返回，见 app/routes/meeting.py）
URL = (
    "http://127.0.0.1:8000/api/v1/meeting/minutes/file"
    f"?request_id={REQUEST_ID}&user_id={USER_ID}"
)

if not REQUEST_ID:
    # 留空时自动取最近一次 minutes 响应里保存的 request_id（先跑 minutes.py 才有）
    saved = Path("data_minutes_response.json")
    if saved.exists():
        REQUEST_ID = json.loads(saved.read_text(encoding="utf-8"))["request_id"]
        print("request_id : 自动读取 ->", REQUEST_ID)
    else:
        print("请先在 REQUEST_ID 填入 POST minutes 响应的 request_id（或先跑 minutes.py）")
        raise SystemExit(1)
else:
    print("request_id :", REQUEST_ID)

resp = requests.get(URL, timeout=60)

print("HTTP", resp.status_code, "|", resp.headers.get("content-type"))
if resp.status_code == 200:
    out = Path(FILE_NAME)
    out.write_bytes(resp.content)
    print("已下载     :", out.resolve(), f"（{len(resp.content)} bytes）")
else:
    print("失败       :", resp.text)
