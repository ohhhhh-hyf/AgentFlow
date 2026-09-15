"""获取异步 minutes 任务结果。用法：python minutes_async_result.py

结果接口与状态接口返回同一份"任务快照"，只是成功时会带上 text（正文）与 file_name。
任务未完成或失败同样返回 200 + 该快照（status=queued/running/failed），不再是 409。
"""
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

if data.get("code") != 0:                      # 调用失败：只有 code + message
    raise SystemExit(f"调用失败：{data.get('message')}")

monitor = data.get("monitor") or {}
print("code       :", data.get("code"))
print("job_id     :", data.get("job_id"))
print("request_id :", data.get("request_id"))
print("status     :", data.get("status"))       # succeeded 时下面才有正文
print("message    :", data.get("message"))
print("token      :", monitor.get("token_usage"), "| cache:", monitor.get("cache_hit"),
      "| cost:", monitor.get("cost_time"), "s")
print("file_name  :", data.get("file_name"))
print("preview    :")
print((data.get("text") or "")[:2000])

request_id = data.get("request_id") or ""
file_name = data.get("file_name") or ""
if request_id and file_name:
    print("preview_url:")
    print(f"http://127.0.0.1:8000/api/v1/meeting/minutes/preview?request_id={request_id}&user_id={USER_ID}")
    print("download_url:")
    print(f"http://127.0.0.1:8000/api/v1/meeting/minutes/file/{request_id}/{file_name}?user_id={USER_ID}")
