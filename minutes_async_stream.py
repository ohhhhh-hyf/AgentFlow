"""查看异步 minutes 任务事件流。用法：python minutes_async_stream.py"""
import json

import requests

JOB_ID = "job_637547664132538372"  # 填写 minutes_async_submit.py 返回的 job_id
CURSOR = 0

if not JOB_ID:
    raise SystemExit("请先把 minutes_async_submit.py 返回的 job_id 填到 JOB_ID")

URL = f"http://127.0.0.1:8000/api/v1/tasks/{JOB_ID}/stream?cursor={CURSOR}"

print("URL :", URL)
with requests.get(URL, stream=True, timeout=3600) as resp:
    print("HTTP", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        raise SystemExit(1)
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            print(raw)
            continue
        etype = event.get("type")
        if etype == "chunk":
            text = event.get("text") or ""
            print(f"[chunk] {event.get('line')} {event.get('title')} {text[:120]!r}")
        elif etype == "phase":
            print("[phase]", event.get("node"))
        elif etype == "done":
            print("[done]", json.dumps(event, ensure_ascii=False)[:2000])
        elif etype == "error":
            print("[error]", event.get("message"))
        else:
            print(json.dumps(event, ensure_ascii=False))
