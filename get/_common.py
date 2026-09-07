"""产物 GET 获取公共逻辑：预览（浏览器渲染）/ 下载（存本地）/ 打印文本。

用法（各任务线脚本统一入口）：
    python get/minutes.py --rid <request_id> [--user 1] [--mode preview|download|text] [--no-open]
    python get/minutes.py                # --rid 缺省时自动读 data_minutes_response.json

mode 说明：
    preview   取页面版 html，浏览器直接打开渲染（meeting 走受控 /preview 端点；
              notes 无页面版端点，走 /data 静态同源 URL）
    download  取产物文件（html / md / json 按存在顺序回退），保存到当前目录
    text      取文本产物（md），打印正文
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import requests

import os

BASE = os.environ.get("AGENTFLOW_BASE", "http://127.0.0.1:8000")

# 各线的产物候选（按序探测，取第一个存在的文件）
_HTML = "{task}.html"
_MD_FALLBACK = ("{task}.md", "result.md")


def _auto_request_id(task: str) -> str:
    """自动读取最近一次同线请求的响应文件里的 request_id。"""
    for name in (f"data_{task}_response.json", f"data_{task}.json", "data_minutes_response.json"):
        p = Path(name)
        if p.is_file():
            try:
                rid = json.loads(p.read_text(encoding="utf-8")).get("request_id") or ""
                if rid:
                    return rid
            except (OSError, json.JSONDecodeError):
                continue
    return ""


def _static_output_url(user_id: str, request_id: str, file_name: str) -> str:
    return f"{BASE}/data/{user_id}/output/{request_id}/{file_name}"


def _probe(user_id: str, request_id: str, candidates: list[str]) -> tuple[str, requests.Response] | None:
    """按候选名顺序探测产物（命中 200 即返回 URL 与响应）。"""
    for name in candidates:
        url = _static_output_url(user_id, request_id, name)
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            return url, resp
    return None


def fetch(
    domain: str,
    task: str,
    request_id: str = "",
    user_id: str = "1",
    mode: str = "preview",
) -> None:
    """按 mode 获取产物并展示/保存。请求失败时给出 404 提示而不是崩溃。"""
    rid = (request_id or "").strip() or _auto_request_id(task)
    if not rid:
        print("缺少 request_id：请传 --rid，或先跑对应接口并保留 data_{task}_response.json")
        raise SystemExit(1)
    uid = (user_id or "1").strip() or "1"
    print(f"任务      : {domain}/{task}")
    print(f"request_id: {rid}")

    if mode == "download":
        resp = _download(domain, task, uid, rid)
    elif mode == "text":
        resp = _text(domain, task, uid, rid)
    else:
        resp = _preview(domain, task, uid, rid)
    if resp is None:
        raise SystemExit(1)
    resp.raise_for_status()


def _preview(domain: str, task: str, uid: str, rid: str) -> requests.Response | None:
    if domain == "meeting":
        url = f"{BASE}/api/v1/meeting/{task}/preview?request_id={rid}&user_id={uid}"
        resp = requests.get(url, timeout=60)
    else:
        # notes 域无受控预览端点：静态 html（text/html，浏览器渲染）同源可达
        hit = _probe(uid, rid, [f"{task}.html"])
        if hit is None:
            print(f"HTTP 404 | 没有页面版产物（output/{rid}/{task}.html 不存在）")
            return None
        url, resp = hit
    print("URL       :", url)
    print("HTTP", resp.status_code, "|", resp.headers.get("content-type"))
    print("attachment:", resp.headers.get("content-disposition", "无（→ 浏览器直接渲染展示）"))
    if resp.status_code == 200:
        try:
            webbrowser.open(url, new=2)
            print("已在浏览器打开，请查看页面效果")
        except Exception:  # noqa: BLE001 - 无浏览器环境时不影响
            print("请在浏览器手动打开上面的 URL")
        return resp
    print("失败      :", resp.text[:300])
    return None


def _download(domain: str, task: str, uid: str, rid: str) -> requests.Response | None:
    if domain == "meeting":
        url = f"{BASE}/api/v1/meeting/{task}/file?request_id={rid}&user_id={uid}"
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            return _save(resp)
        print("HTTP", resp.status_code, "|", resp.text[:300])
        return None
    # notes 域下载端点需显式文件名：按 html → md 顺序探测并保存
    hit = _probe(uid, rid, [f"{task}.html", f"{task}.md", "result.md"])
    if hit is None:
        print(f"HTTP 404 | 该 request 下没有可下载的产物文件（output/{rid}/）")
        return None
    url, resp = hit
    print("URL       :", url)
    return _save(resp, default_name=url.rsplit("/", 1)[-1])


def _text(domain: str, task: str, uid: str, rid: str) -> requests.Response | None:
    if domain == "meeting":
        # 下载端点回退链含 html；text 模式只要 md——先试 md 再 result.md
        resp = requests.get(
            f"{BASE}/api/v1/meeting/{task}/file?request_id={rid}&user_id={uid}", timeout=60
        )
    else:
        resp = None
    if resp is not None and resp.status_code == 200 and "text/" in (resp.headers.get("content-type") or ""):
        print(resp.text)
        return resp
    hit = _probe(uid, rid, [f"{task}.md", "result.md"])
    if hit is None:
        print(f"HTTP 404 | 该 request 下没有文本产物（output/{rid}/）")
        return None
    _url, resp = hit
    print(resp.text)
    return resp


def _save(resp: requests.Response, default_name: str = "") -> requests.Response:
    """保存产物到当前目录（等价下载）：优先响应头 filename，否则用探测到的产物名。"""
    filename = default_name or "output"
    cd = resp.headers.get("content-disposition") or ""
    if "filename=" in cd:
        filename = cd.split("filename=", 1)[1].strip().strip('"')
    elif filename == "output":
        ct = resp.headers.get("content-type") or ""
        filename = f"download{'.html' if 'html' in ct else '.md' if 'markdown' in ct or 'text' in ct else '.bin'}"
    out = Path(filename)
    out.write_bytes(resp.content)
    print(f"HTTP {resp.status_code} | 已下载: {out.resolve()}（{len(resp.content)} bytes）")
    return resp


def main(domain: str, task: str, title: str) -> None:
    """任务线脚本的统一 CLI：python get/<task>.py [--rid …] [--user 1] [--mode preview|download|text]"""
    parser = argparse.ArgumentParser(description=f"GET {title}产物：预览 / 下载 / 打印文本")
    parser.add_argument("--rid", default="", help="请求 id（POST 响应返回；缺省自动读取最近响应文件）")
    parser.add_argument("--user", default="1", help="用户 id（产物按用户隔离，与 POST 时 X-User-Id 一致）")
    parser.add_argument("--mode", default="preview", choices=["preview", "download", "text"])
    args = parser.parse_args()
    try:
        fetch(domain, task, request_id=args.rid, user_id=args.user, mode=args.mode)
    except requests.ConnectionError:
        print(f"无法连接 {BASE} —— 请确认服务已启动")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - 交互入口
    main("meeting", "minutes", "会议纪要")
