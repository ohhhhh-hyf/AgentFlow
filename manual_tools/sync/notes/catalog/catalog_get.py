"""下载 catalog 的页面产物：GET /api/agent/v1/file/{request_id}/{file_name}。

统一入口：域与任务名不再出现在路径里，下载只认 request_id + file_name
（产物目录 data/{user_id}/output/{request_id}/ 由 request_id 唯一确定）：
- request_id：POST /api/agent/v1（"domain":"notes","task":"catalog"）响应里的 request_id
- file_name ：响应中 data.file_name 即为 catalog.html；也可传 result.md 获取目录 Markdown 正文
- user_id   ：URL 参数 ?user_id= 或 X-User-Id 头，二者取一

说明：
- 产物目录 output/{request_id}/ 包含两份产物：
  1. catalog.html：带样式与交互的知识目录卡片与目录树页面（data.file_name 返回值）
  2. result.md   ：纯文本/目录树 Markdown
- 底层知识库目录 JSON 保存在 data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json，
  供系统内部/checklist 自动加载，不对用户暴露为下载文件。

用法：python catalog_get.py
"""
from pathlib import Path

import requests

BASE_URL = "http://10.33.240.226:8003"   # 换服务器时改这里
USER_ID = "1"

# ── 请求参数 ──
REQUEST_ID = ""                  # ← 自己填：POST 响应里的 request_id
FILE_NAME = "catalog.html"       # ← 响应 data.file_name（也可换成 result.md 下载 Markdown）

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
