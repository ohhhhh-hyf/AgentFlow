"""查询异步 minutes 任务状态。用法：python minutes_async_status.py"""
import json

import requests

JOB_ID = "job_637547664132538372"  # 填写 minutes_async_submit.py 返回的 job_id

if not JOB_ID:
    raise SystemExit("请先把 minutes_async_submit.py 返回的 job_id 填到 JOB_ID")

URL = f"http://127.0.0.1:8000/api/v1/tasks/{JOB_ID}"

resp = requests.get(URL, timeout=60)

print("URL :", URL)
print("HTTP", resp.status_code)
try:
    data = resp.json()
except Exception:
    print(resp.text)
    raise

print(json.dumps(data, ensure_ascii=False, indent=2))
