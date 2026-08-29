"""资料入库任务接口请求示例：POST /api/v1/notes/library（同步）。

用法:
    python library.py

依赖 requests；服务端需已启动（uvicorn app.main:app --host 0.0.0.0 --port 8000）。
X-Request-Id 必填（建议 UUID）；X-User-Id 必填（入库资料按用户隔离）。
请求体为通用结构，不用的字段置空即可（字段说明见 API.md 第四节）。
docs 里的文件需先放入 data/{user_id}/docs/ 下：
- 图片（.png/.jpg/.jpeg）走 OCR 后入库，其余（.pdf/.pptx/.docx/.xlsx/.txt/.md）直接解析入库
- extra.subject 建议填写，按学科分类入库资料
data.text 为入库报告（如「入库成功，导入图片2张，文档1份，数学新增知识单元 8 个。」）；
data.file_name 恒为空串（library 不落请求产物文件）。
"""
import uuid

import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {
    "X-User-Id": "1",
    "X-Request-Id": uuid.uuid4().hex,  # 必填：调用方追踪 ID（建议 UUID）
}

# 通用请求体：所有字段都留好，不用的置空
payload = {
    "texts": {
        "transcript": "",   # library 的输入只有 docs，texts 不参与
        "keypoints": "",
        "notes": "",
    },
    "docs": ["20260829_125749_438.json"],   # 必填：待入库文件（放 data/{user_id}/docs/ 下；图片自动 OCR）
    "extra": {
        "template": "",
        "profile": "",
        "project": "",
        "subject": "物理",   # 建议填写：按学科分类入库资料
        "style": "",
    },
}

# ── 同步请求：POST /api/v1/notes/library ───────────────────────
resp = requests.post(
    f"{BASE}/api/v1/notes/checklist",
    headers=HEADERS,
    json=payload,
    timeout=900,   # 图片 OCR 较慢（3-10 分钟属正常），按需调整
)

data = resp.json()
print(f"HTTP={resp.status_code} code={data.get('code')} message={data.get('message')}")
print(f"request_id={data.get('request_id')}")
print(f"monitor={data.get('monitor')}")
print("入库报告（data.text）：")
print(((data.get("data") or {}).get("file_name") or ""))
print(((data.get("data") or {}).get("text") or ""))


# ── 流式请求：POST /api/v1/notes/library/stream ────────────────
# with requests.post(
#     f"{BASE}/api/v1/notes/library/stream",
#     headers=HEADERS,
#     json=payload,
#     stream=True,
#     timeout=900,
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
