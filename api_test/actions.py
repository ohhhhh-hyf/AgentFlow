"""api_test/actions.py -- 待办事项提取接口单次测试脚本.

功能:
    1. 测试非流式待办抽取接口 (POST /api/agent/v1);
    2. 支持态 A（传 meeting_time -> 触发 Calendar 绝对时间推导，产出 actions_update.json）
       与态 B（不传 meeting_time -> 纯 0ms 跳过 Calendar，产出 actions.json）自由切换;
    3. 响应结果中从 data.text 提取完全剥离外壳的平铺待办 JSON 数组并格式化打印;
    4. 自动处理本地代理绕过，防止请求被系统代理劫持超时.

用法:
    python api_test/actions.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import requests

# ── 测试会议文本 ──
TRANSCRIPT = """
张总：今天开会主要过一下下周的双十一保障筹备情况。
李工：支付网关的高可用与压测由我来负责，明天下午 18:00 前我输出一份完整的容量评估与基准压测报告。
王工：前端容灾兜底页面以及降级预案由我全权跟进，下周一上午 10:00 之前完成所有环境的部署与演练。
张总：好的，李工和王工务必按时保质交付。另外赵工负责组织安全团队在周五下班前完成一轮渗透测试。散会！
""".strip()

# ── 会议起始时间（非空触发态 A，空字符串 "" 触发态 B）──
# 态 A 示例: "2026-11-13 14:00:00"
# 态 B 示例: ""
MEETING_TIME = "2026-11-13 14:00:00"

BASE_URL = os.getenv("AGENTFLOW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SYNC_URL = f"{BASE_URL}/api/agent/v1"
USER_ID = "1"


def main():
    if not TRANSCRIPT.strip():
        print("[提示] TRANSCRIPT 文本为空，请在脚本顶部填入待测试的会议转写内容。")
        return

    is_state_a = bool(MEETING_TIME.strip())
    print("=" * 70)
    print(f"正在请求待办提取接口: {SYNC_URL}")
    print(f"模式: {'【态 A: 携带会议时间 -> 触发 Calendar 绝对时间推导】' if is_state_a else '【态 B: 无会议时间 -> 跳过 Calendar】'}")
    if is_state_a:
        print(f"会议时间: {MEETING_TIME}")
    print("=" * 70)

    # 严格对齐 TaskRequest 契约规范
    payload = {
        "task": "actions",
        "texts": {
            "transcript": TRANSCRIPT,
            "actions_text": "",
            "keypoints": "",
            "notes": "",
            "vision_info": "",
        },
        "docs": [],
        "extra": {
            "time": MEETING_TIME.strip(),
            "template": "",
        },
        "lang": "zh",
    }

    req_id = uuid.uuid4().hex
    headers = {
        "X-Request-Id": req_id,
        "X-User-Id": USER_ID,
    }

    session = requests.Session()
    # 本地环境防代理劫持
    if "127.0.0.1" in BASE_URL or "localhost" in BASE_URL:
        session.trust_env = False

    try:
        resp = session.post(
            SYNC_URL,
            json=payload,
            headers=headers,
            timeout=120,
        )
    except Exception as exc:
        print(f"✗ 请求服务失败: {exc}")
        print("请确认后台服务已启动 (如: uvicorn main:app --host 127.0.0.1 --port 8000)")
        return

    if resp.status_code != 200:
        print(f"✗ 请求失败 HTTP {resp.status_code}: {resp.text}")
        return

    try:
        body = resp.json()
    except Exception as exc:
        print(f"✗ 无法解析返回为 JSON: {exc}, 原始文本: {resp.text[:300]}")
        return

    code = body.get("code")
    if code != 0:
        print(f"✗ 接口返回错误: code={code}, message={body.get('message')}")
        return

    data = body.get("data") or {}
    file_name = data.get("file_name", "")
    flat_actions = data.get("text")
    monitor = body.get("monitor") or {}

    print(f"✓ 抽取成功！")
    print(f"  - Request ID : {body.get('request_id')}")
    print(f"  - 对应落盘文件: {file_name}")
    print(f"  - 总耗时     : {monitor.get('cost_time')}s")
    print(f"  - 待办总数   : {monitor.get('total_count')} 条")
    print(f"  - Calendar执行: {monitor.get('calendar_executed')}")
    print("-" * 70)
    print("【剥离外壳后的平铺待办 JSON 数组 (data.text)】:")
    print(json.dumps(flat_actions, ensure_ascii=False, indent=2))
    print("=" * 70)


if __name__ == "__main__":
    main()
