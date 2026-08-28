"""知识图谱任务接口请求示例：POST /api/v1/notes/graph（同步）。

用法:
    python graph.py

依赖 requests；服务端需已启动（uvicorn app.main:app --host 0.0.0.0 --port 8000）。
X-Request-Id 必填（建议 UUID，产物目录 data/{user_id}/output/{request_id}/ 以它为名）。
请求体为通用结构，不用的字段置空即可（字段说明见 API.md 第四节）。
graph 必填 docs（笔记 .txt/.md 文件）；extra.subject 传学科名可开启记忆增量（见 API.md 6.6）。
"""
import json
import uuid

import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {
    "X-User-Id": "1",
    "X-Request-Id": uuid.uuid4().hex,  # 必填：调用方追踪 ID（建议 UUID）
}

# 通用请求体：所有字段都留好，不用的置空
payload = {
    "domain": "notes",
    "task": "graph",
    "texts": {
        "transcript": "",   # graph 用 docs 传笔记文件，不用 transcript
        "teacher_focus": "",
        "keypoints": "",
        "notes": "",
    },
    "docs": ["seq_one.txt"],   # 必填：笔记 .txt/.md 文件（放 data/{user_id}/docs/ 下）
    "extra": {
        "template": "",
        "profile": "",
        "project": "",
        "subject": "数学",   # 传学科名开启记忆增量（同学科下次调用合并旧图谱，新增节点高亮）
        "style": "",
    },
}

# ── 同步请求：POST /api/v1/notes/graph ─────────────────────────
resp = requests.post(
    f"{BASE}/api/v1/notes/graph",
    headers=HEADERS,
    json=payload,
    timeout=600,
)

data = resp.json()
print(f"HTTP={resp.status_code} code={data.get('code')} message={data.get('message')}")
print(f"request_id={data.get('request_id')}")
print(f"monitor={data.get('monitor')}")
print("输出（学习地图）：")
print(((data.get("data") or {}).get("text") or ""))

# ── 流式请求：POST /api/v1/notes/graph/stream ──────────────────
# with requests.post(
#     f"{BASE}/api/v1/notes/graph/stream",
#     headers=HEADERS,
#     json=payload,
#     stream=True,
#     timeout=600,
# ) as resp:
#     for line in resp.iter_lines(decode_unicode=True):
#         if not line:
#             continue
#         event = json.loads(line)
#         etype = event["type"]
#         if etype == "phase":
#             print(f"[stage] {event['node']}")
#         elif etype == "chunk":
#             print(event["text"], end="", flush=True)
#         elif etype == "done":
#             print()
#             print(f"[done] code={event['code']} message={event['message']}")
#             print(f"[request_id] {event['request_id']}")
#             print(f"[monitor] {event['monitor']}")
#         elif etype == "error":
#             print(f"[失败] {event['message']}")
