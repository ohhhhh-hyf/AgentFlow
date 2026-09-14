"""方式三：GET /api/v1/meeting/minutes/preview，受控预览 minutes 页面版。

与方式一（/data 静态）的区别：走 API 路由，只允许定位产物目录内的
{task}.html（resolve_output_file 校验），不暴露 /data 整树；
同样不带 attachment 头（text/html inline）→ 浏览器直接渲染展示。

用法：python minutes_view_preview.py
"""
import json
import webbrowser
from pathlib import Path

import requests

# ── 请求参数 ──
REQUEST_ID = ""   # ← 自己填：POST minutes 响应里的 request_id（留空则自动读取）
USER_ID = "1"

URL = (
    "http://10.33.240.226:8003/api/v1/meeting/risks/preview"
    f"?request_id={REQUEST_ID}&user_id={USER_ID}"
)

if not REQUEST_ID:
    saved = Path("data_minutes_response.json")
    if saved.exists():
        REQUEST_ID = json.loads(saved.read_text(encoding="utf-8"))["request_id"]
        URL = (
            "http://127.0.0.1:8000/api/v1/meeting/minutes/preview"
            f"?request_id={REQUEST_ID}&user_id={USER_ID}"
        )
        print("request_id : 自动读取 ->", REQUEST_ID)
    else:
        print("请先在 REQUEST_ID 填入 POST minutes 响应的 request_id（或先跑 minutes.py）")
        raise SystemExit(1)
else:
    print("request_id :", REQUEST_ID)

resp = requests.get(URL, timeout=60)

print("URL       :", URL)
print("HTTP", resp.status_code, "|", resp.headers.get("content-type"))
print("attachment:", resp.headers.get("content-disposition", "无（→ 浏览器直接渲染展示）"))
if resp.status_code == 200:
    print("体长      :", len(resp.content), "bytes（即页面 html 源码）")
    try:
        webbrowser.open(URL, new=2)
        print("已在浏览器打开，请查看页面效果")
    except Exception:  # noqa: BLE001 - 无浏览器环境时不影响
        print("请在浏览器手动打开上面的 URL")
else:
    print("失败      :", resp.text[:300])
