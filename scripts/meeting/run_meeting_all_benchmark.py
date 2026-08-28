from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"
USER = "1"
TRANSCRIPT = (ROOT / "samples" / "meeting" / "file" / "meeting_all.txt").read_text(
    encoding="utf-8"
)


TRACE_KEYPOINTS = "\n".join(
    [
        "蒙泽厂区混凝土路面存在少量开裂，需要分析原因并在出报告前闭环整改。",
        "内业资料、人员履约资料和不可预见费证据需要进一步完善。",
        "姆皮卡点尚未完成现场验收，后续路途和雨季安全需要注意。",
    ]
)

TRACE_NOTES = "\n".join(
    [
        "蒙泽厂区混凝土路面有少量开裂 -> 关注整改方案、复核和闭环。",
        "三个厂区资料汇总到卢萨卡 -> 关注竣工资料组卷归档。",
        "不可预见费的使用和证据 -> 关注数据依据是否充分无误。",
    ]
)


def payload(task: str) -> dict:
    texts = {"transcript": TRANSCRIPT}
    extra = {
        "template": "",
        "profile": "",
        "project": "meeting_all_benchmark",
        "subject": "",
        "style": "",
    }
    if task == "minutes_trace":
        texts["keypoints"] = TRACE_KEYPOINTS
        texts["notes"] = TRACE_NOTES
    return {
        "domain": "meeting",
        "task": task,
        "texts": texts,
        "docs": [],
        "extra": extra,
    }


def call(task: str) -> dict:
    request_id = f"bench-{task}-{uuid.uuid4().hex[:8]}"
    started = time.time()
    resp = requests.post(
        f"{BASE}/api/v1/meeting/{task}",
        headers={"X-User-Id": USER, "X-Request-Id": request_id},
        json=payload(task),
        timeout=900,
    )
    elapsed = round(time.time() - started, 1)
    try:
        data = resp.json()
    except Exception:
        data = {"message": resp.text}
    out_dir = ROOT / "data" / USER / "output" / request_id
    return {
        "task": task,
        "http_status": resp.status_code,
        "elapsed": elapsed,
        "request_id": request_id,
        "response": data,
        "output_dir": str(out_dir),
    }


def main() -> None:
    tasks = ["minutes", "actions", "risks", "minutes_trace"]
    results = [call(task) for task in tasks]
    summary = []
    for item in results:
        data = item["response"]
        monitor = data.get("monitor") or {}
        text = ((data.get("data") or {}).get("text") or "").strip()
        summary.append(
            {
                "task": item["task"],
                "http_status": item["http_status"],
                "code": data.get("code"),
                "message": data.get("message"),
                "request_id": data.get("request_id") or item["request_id"],
                "elapsed": item["elapsed"],
                "monitor": monitor,
                "text_chars": len(text),
                "output_dir": item["output_dir"],
                "preview": text[:1200],
            }
        )
    out = ROOT / "data" / USER / "output" / "meeting_all_benchmark_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"SUMMARY={out}")


if __name__ == "__main__":
    main()
