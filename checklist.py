"""请求 notes 域 checklist（基于 catalog 生成复习清单）接口并解析返回字段。

用法：python checklist.py

checklist 必填：X-User-Id + extra.subject + docs（data/{USER_ID}/knowledge/catalogs/{学科拼音}/ 下的
catalog 文件名 .json）。请先运行 catalog 生成目录，再跑本脚本生成复习清单。
可选：docs 里追加老师重点 .txt（须在 data/{USER_ID}/docs/ 下）；不加则按目录全量复习。
"""
import json
import uuid
from pathlib import Path

import requests

# ── Catalog 参数 ──
USER_ID = "1"
SUBJECT = "wuli"                      # 学科（物理 → wuli，与 catalog 生成时一致）
CATALOG_FILE = "20260906_233457_685.json"                     # catalog json 文件名；留空自动取本地该学科最新
TEACHER_FILE = ""                     # 可选：老师重点 .txt 文件名（data/{USER_ID}/docs/ 下）

URL = "http://127.0.0.1:8000/api/v1/notes/checklist"


def _latest_catalog_name() -> str:
    """本地自动取该学科目录下最新的 catalog json 名（学科先转拼音，与接口一致）。"""
    from tools.knowledge.config import subject_to_pinyin

    folder = Path("data") / USER_ID / "knowledge" / "catalogs" / subject_to_pinyin(SUBJECT)
    if not folder.is_dir():
        return ""
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].name if files else ""


if not CATALOG_FILE:
    CATALOG_FILE = _latest_catalog_name()
if not CATALOG_FILE:
    print("请先填写 CATALOG_FILE（catalog json 文件名），或先运行 catalog 接口生成目录")
    raise SystemExit(1)

docs = [CATALOG_FILE]
if TEACHER_FILE:
    docs.append(TEACHER_FILE)

print(f"catalog    : {SUBJECT}/{CATALOG_FILE}", "| 老师重点:", TEACHER_FILE or "（无）")
resp = requests.post(
    URL,
    json={
        "time": "",
        "texts": {
            "transcript": "",
            "keypoints": "",
            "notes": "",
        },
        "docs": docs,
        "extra": {
            "template": "",
            "profile": "",
            "project": "",
            "subject": SUBJECT,
            "style": "",
            "memory": False,
        },
    },
    headers={"X-Request-Id": uuid.uuid4().hex, "X-User-Id": USER_ID},
    timeout=600,
)
data = resp.json()

print("HTTP", resp.status_code)
print("code       :", data.get("code"))
print("request_id :", data.get("request_id"))
print("message    :", data.get("message"))
monitor = data.get("monitor") or {}
print("token      :", monitor.get("token_usage"), "| cache:", monitor.get("cache_hit"), "| cost:", monitor.get("cost_time"), "s")
d = data.get("data") or {}
print("file_name  :", d.get("file_name"))
print("text       :")
print(d.get("text"))
Path("data_checklist_response.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
