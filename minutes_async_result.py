"""获取异步 minutes 任务结果。用法：python minutes_async_result.py"""
import json

import requests

JOB_ID = "job_637547664132538372"  # 填写 minutes_async_submit.py 返回的 job_id
USER_ID = "1"

if not JOB_ID:
    raise SystemExit("请先把 minutes_async_submit.py 返回的 job_id 填到 JOB_ID")

URL = f"http://127.0.0.1:8000/api/v1/tasks/{JOB_ID}/result"

resp = requests.get(URL, timeout=60)

print("URL :", URL)
print("HTTP", resp.status_code)
try:
    data = resp.json()
except Exception:
    print(resp.text)
    raise

print("type       :", data.get("type"))
print("code       :", data.get("code"))
print("request_id :", data.get("request_id"))
print("message    :", data.get("message"))
monitor = data.get("monitor") or {}
print("token      :", monitor.get("token_usage"), "| cache:", monitor.get("cache_hit"), "| cost:", monitor.get("cost_time"), "s")
payload = data.get("data") or {}
print("file_name  :", payload.get("file_name"))
print("preview    :")
print((payload.get("text") or "")[:2000])

request_id = data.get("request_id") or ""
file_name = payload.get("file_name") or ""
if request_id and file_name:
    print("preview_url:")
    print(f"http://127.0.0.1:8000/api/v1/meeting/minutes/preview?request_id={request_id}&user_id={USER_ID}")
