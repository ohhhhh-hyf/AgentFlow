"""下载 catalog 的 Markdown 产物：GET /api/agent/v1/file/{request_id}/{file_name}。

统一入口：域与任务名不再出现在路径里，下载只认 request_id + file_name
（产物目录 data/{user_id}/output/{request_id}/ 由 request_id 唯一确定）：
- request_id：POST /api/agent/v1（"domain":"notes","task":"catalog"）响应里的 request_id
- file_name ：用 result.md（产物目录里的正文存档名；响应 data.file_name 是 json 名，取不到）
- user_id   ：URL 参数 ?user_id= 或 X-User-Id 头，二者取一

**注意 data.file_name 不是可下载的文件名**：catalog 的响应 data.file_name 指向知识目录
json（如 20260907_201649_443.json），它落在 data/{user_id}/knowledge/catalogs/{学科拼音}/，
**不在产物目录里**，用下载端点取会 404。要取它请走静态路径（无鉴权）：
    /data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}
产物目录里另有 result.md（正文存档；部分运行还会有 catalog.html）。

catalog 没有预览端点（tasklines.py 里 files=False，预览按线注册）。

用法：python catalog_get.py
"""
from pathlib import Path

import requests

BASE_URL = "http://10.33.240.226:8003"   # 换服务器时改这里
USER_ID = "1"

# ── 请求参数 ──
REQUEST_ID = ""                  # ← 自己填：POST 响应里的 request_id
FILE_NAME = "result.md"          # ← 目录树 Markdown 的存档名（data.file_name 是 json 名，取不到）

if not REQUEST_ID:
    print("请先把 REQUEST_ID 填成 POST catalog 响应里的 request_id")
    raise SystemExit(1)

URL = f"{BASE_URL}/api/agent/v1/file/{REQUEST_ID}/{FILE_NAME}?user_id={USER_ID}"

resp = requests.get(URL, timeout=60)

print("URL       :", URL)
print("HTTP", resp.status_code, "|", resp.headers.get("content-type"))
print("attachment:", resp.headers.get("content-disposition", "无（该端点应为 attachment）"))
if resp.status_code == 200:
    out = Path(__file__).resolve().parent / "downloads" / Path(FILE_NAME).name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    print("已保存    :", out, f"（{len(resp.content)} bytes）")
else:
    print("失败      :", resp.text[:300])
