"""方式一：GET /data 静态路径，浏览器直接展示 minutes.html。

与下载版的区别：/data 是静态文件挂载（app/main.py），响应不带
Content-Disposition: attachment → 浏览器拿到 text/html 直接渲染页面，
不会弹下载框。产物 html 为自包含单文件（样式内联），展示效果完整。
缺点：/data 暴露整棵 data 目录（docs/memory 等也能被 GET）。

用法：python minutes_view_static.py
"""
import json
import webbrowser
from pathlib import Path

import requests

# ── 请求参数 ──
REQUEST_ID = "8159654c537e4ceab2b569eb42f17d1a"   # ← 自己填：POST minutes 响应里的 request_id（留空则自动读取）
USER_ID = "1"     # POST 时 X-User-Id 传的谁就填谁（产物在 data/{user_id}/output/ 下）

URL = f"http://127.0.0.1:8000/data/{USER_ID}/output/{REQUEST_ID}/minutes.html"

if not REQUEST_ID:
    saved = Path("data_minutes_response.json")
    if saved.exists():
        REQUEST_ID = json.loads(saved.read_text(encoding="utf-8"))["request_id"]
        URL = f"http://127.0.0.1:8000/data/{USER_ID}/output/{REQUEST_ID}/minutes.html"
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
        webbrowser.open(URL, new=2)   # 在默认浏览器打开，看渲染效果
        print("已在浏览器打开，请查看页面效果")
    except Exception:  # noqa: BLE001 - 无浏览器环境时不影响
        print("请在浏览器手动打开上面的 URL")
else:
    print("失败      :", resp.text[:300])
