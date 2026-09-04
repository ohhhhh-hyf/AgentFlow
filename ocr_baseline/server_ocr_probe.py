# -*- coding: utf-8 -*-
"""ServerOCR 原始响应取证（S2：确认服务端是否返回 per-line 置信度字段）。

与生产 OCR 完全同路径：tools/ocr/server_ocr.ServerOcrClient.get_ocr + 同一
base64 构造（_image_base64_for_request），不做任何解析改造；只额外把**原始
响应 JSON** 落盘，并对"行节点"做字段盘点，回答三个问题：
  1) 服务端行节点上有哪些字段（key 全集 / 交集）；
  2) 是否存在置信度类字段（confidence/conf/score/prob/probability/accuracy…），
     若存在：字段名、类型、数值范围、是否为 0/缺失；
  3) 生产 extract_lines 映射后每行是否带 conf（现状 None 的原因）。

用法（服务器上执行，需 .env 的 SERVER_OCR_* 就位）：
    python ocr_baseline/server_ocr_probe.py --images /path/a.jpg /path/b.jpg
    python ocr_baseline/server_ocr_probe.py --images /path/a.jpg --out-dir /tmp/probe
    python ocr_baseline/server_ocr_probe.py --images /path/a.jpg --dry   # 不发起请求，只验证参数

产物：<out-dir>/<时间戳>_<图片名>_raw_response.json（原始响应全文）+ 控制台盘点摘要。
默认 out-dir 为 ocr_baseline/records（已 gitignore，随基线记录一起拉回）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = Path(__file__).resolve().parent / "records"

_CONF_LIKE_RE = re.compile(r"conf|score|prob|accu|置信", re.I)


def load_env() -> None:
    from client.config import load_env

    load_env(ROOT / ".env")


def _field_inventory(nodes: list[dict]) -> dict:
    """行节点字段盘点：全集 / 交集 / 每字段类型与样例。"""
    keys: list[str] = []
    for node in nodes:
        for key in node.keys():
            if key not in keys:
                keys.append(key)
    common = [k for k in keys if all(k in node for node in nodes)]
    inventory: dict[str, dict] = {}
    for key in keys:
        values = [node.get(key) for node in nodes]
        types = sorted({type(v).__name__ for v in values if v is not None})
        sample: object = None
        for value in values:
            if value is not None and value != "" and value != 0:
                sample = value
                break
        entry: dict = {"types": types, "missing": sum(1 for v in values if v is None)}
        if all(isinstance(v, (int, float)) for v in values if v is not None):
            nums = [float(v) for v in values if v is not None]
            entry["min"] = min(nums)
            entry["max"] = max(nums)
        elif isinstance(sample, str):
            entry["sample"] = sample[:80]
        elif isinstance(sample, list):
            entry["sample_len"] = len(sample)
        elif isinstance(sample, dict):
            entry["sample_keys"] = sorted(sample.keys())[:12]
        elif sample is None:
            entry["sample"] = None
        inventory[key] = entry
    return {
        "node_count": len(nodes),
        "keys_union": keys,
        "keys_common": common,
        "fields": inventory,
    }


def _conf_like_keys(inventory: dict) -> list[dict]:
    hits = []
    for key, info in inventory.get("fields", {}).items():
        if _CONF_LIKE_RE.search(key):
            hits.append({"key": key, **info})
    return hits


def _collect_raw_line_nodes(result: dict) -> tuple[str, list[dict]]:
    """优先复用生产解析内部路径定位行节点；失败则通用深扫兜底。"""
    from tools.ocr import server_ocr as mod

    try:
        payload = mod._unwrap_server_payload(result)
        if mod._looks_like_focus(payload):
            nodes = list(mod._iter_focus_text_lines(payload))
            if nodes:
                return "focus(生产同路径)", [dict(n) for n in nodes]
        nodes = list(mod._iter_line_nodes(payload))
        if nodes:
            return "generic(生产同路径)", [dict(n) for n in nodes]
    except Exception as exc:  # noqa: BLE001
        print(f"  [提示] 生产解析路径不可用（{exc}），改用通用深扫")
    # 兜底：深扫找"疑似行节点"的列表（含 cornerPoints 或 text 的 dict 列表）
    candidates: list[list[dict]] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                probe = value[0]
                if "cornerPoints" in probe or "text" in probe:
                    candidates.append([dict(item) for item in value])
            for item in value:
                walk(item)

    walk(result)
    if candidates:
        biggest = max(candidates, key=len)
        return "通用深扫(最长的行节点候选列表)", biggest
    return "未找到行节点", []


def probe_one(path: Path, out_dir: Path, *, dry: bool) -> dict:
    from tools.ocr.server_ocr import ServerOcrClient, _image_base64_for_request, extract_lines

    image_base64 = _image_base64_for_request(str(path))
    client = ServerOcrClient()
    summary: dict = {
        "image": path.name,
        "url": client.ocr_url,
        "ocr_url_env": os.getenv("SERVER_OCR_URL", ""),
        "dry": dry,
        "base64_len": len(image_base64),
    }
    if dry:
        summary["dry_note"] = "未发起请求（--dry）。实际运行时将 POST 到上述 URL。"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
    result = client.get_ocr(image_base64)  # 与生产同一请求/签名/校验路径
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = out_dir / f"{stamp}_{path.stem}_raw_response.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["raw_saved"] = str(raw_file)
    summary["raw_bytes"] = raw_file.stat().st_size

    container, nodes = _collect_raw_line_nodes(result)
    summary["node_container"] = container
    if not nodes:
        summary["nodes_found"] = 0
        print(f"\n===== {path.name} =====")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("（原始响应已落盘，可用任意 JSON 工具人工查看节点路径）")
        return summary

    inventory = _field_inventory(nodes)
    conf_hits = _conf_like_keys(inventory)
    mapped_lines = extract_lines(result)
    mapped_with_conf = sum(1 for line in mapped_lines if "conf" in line)

    summary["nodes_found"] = len(nodes)
    summary["keys_union_count"] = len(inventory["keys_union"])
    summary["keys_common_count"] = len(inventory["keys_common"])
    summary["conf_like_fields"] = conf_hits
    summary["mapped_lines"] = len(mapped_lines)
    summary["mapped_with_conf"] = mapped_with_conf

    print(f"\n===== {path.name} =====")
    print(f"行节点来源：{container}（{len(nodes)} 个节点）")
    print(f"字段：全集 {len(inventory['keys_union'])} 个 / 交集 {len(inventory['keys_common'])} 个")
    print(f"字段列表：{inventory['keys_union']}")
    print(f"置信类字段：{json.dumps(conf_hits, ensure_ascii=False)}" if conf_hits
          else "置信类字段：未发现（→ 服务端未返回，需与服务方确认能否带出）")
    print(f"生产映射后行数 {len(mapped_lines)}，其中带 conf 的 {mapped_with_conf}")
    print(f"原始响应已保存：{raw_file}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="ServerOCR 原始响应取证（找 per-line 置信字段）")
    ap.add_argument("--images", nargs="+", required=True, help="要探测的图片路径（必填）")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help="原始响应落盘目录")
    ap.add_argument("--dry", action="store_true", help="不发起请求，只做参数/环境校验")
    args = ap.parse_args()

    load_env()
    images = [Path(p) for p in args.images]
    missing = [str(p) for p in images if not p.exists()]
    if missing:
        raise SystemExit(f"图片不存在：{missing[0]}")
    out_dir = Path(args.out_dir)
    print(f"[probe] 服务 URL：{os.getenv('SERVER_OCR_URL', '(env 未设，用代码默认)')}")
    if not args.dry and not os.getenv("SERVER_OCR_URL"):
        print("[提示] SERVER_OCR_URL 未在 .env/环境配置，将使用代码默认地址；"
              "若目标服务不同请先在 .env 配置 SERVER_OCR_*")
    for image in images:
        try:
            probe_one(image, out_dir, dry=args.dry)
        except Exception as exc:  # noqa: BLE001
            print(f"[probe] {image.name} 取证失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
