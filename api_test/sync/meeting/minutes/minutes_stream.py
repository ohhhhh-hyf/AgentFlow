# -*- coding: utf-8 -*-
"""请求 minutes 流式接口（POST /api/agent/v1/stream）。

用法：
    python minutes_stream.py

核心效果：
1. 先流式输出：大模型渲染 Agent 每吐出一个 Token，终端实时打字机呈现；
2. 再刷新终稿：done 事件触发后，程序无感校准完毕，一次性整篇刷新输出最终定稿内容。
两阶段完全逐字对齐，顶层绝无多余的 # 会议标题。
"""
import json
import os
import sys
import uuid

import requests

# ── 会议转写文本（可根据测试需要替换）──
TRANSCRIPT = """
• 发言者 1 00:21
各位朋友、各位同事，欢迎参加本次架构与发布计划同步会。我们所处的是一个更加变乱交织的世界，面对复杂多变的外部环境，我们的系统架构需要具备更强的确定性和韧性。今天会议主要围绕两个核心议题展开：一是网关架构重构的最新进展与性能指标；二是第四季度的版本发布规划与全员分工。
• 发言者 1 01:58
首先谈网关注册中心与链路优化。经过过去两周的重构，注册链路时延已经成功从原本的 450ms 压降到了 120ms，各项 P99 指标均达到预期。李工团队完成了二级缓存的方案验证，现场大家一致同意正式采用方案 A 作为全局规范。
• 发言者 2 03:06
关于第四季度发布计划，我们在会上做出了明确决策：全链路压测死线定为本周五下班前，十一月中旬完成全面集成测试，十二月初准时上线公测版本。针对容灾备机机房带宽受限这一卡点，现场定调由架构组协调运维团队在周三前批复预算并扩容。
• 发言者 1 04:18
在具体分工落地方面：张三牵头负责网关接口与鉴权插件升级，周五前输出联调测试报告；李四负责前端接入适配并在周二前提交回滚方案；王五跟进容灾机房配置下发。现场遗留未决的海外节点合规评测口径，交由法务与安全组会后排查并在下周例会汇报。
"""

BASE_URL = os.getenv("AGENTFLOW_BASE_URL", "http://127.0.0.1:8888").rstrip("/")
STREAM_URL = f"{BASE_URL}/api/agent/v1/stream"
USER_ID = "1"


def main():
    payload = {
        "domain": "meeting",
        "task": "minutes",
        "texts": {
            "transcript": TRANSCRIPT,
            "keypoints": "",
            "notes": "",
        },
        "docs": [],
        "memory": False,
        "extra": {
            "time": "2026-11-10",
            "template": "general_minutes",  # 可切换为 media_briefing / project_progress 等
            "profile": "",
            "project": "",
            "subject": "",
            "style": "",
        },
    }

    headers = {
        "X-Request-Id": uuid.uuid4().hex,
        "X-User-Id": USER_ID,
    }

    try:
        resp = requests.post(
            STREAM_URL,
            json=payload,
            headers=headers,
            stream=True,
            timeout=300,
        )
    except Exception as exc:
        print(f"请求服务失败: {exc}")
        print("请确认服务已启动 (uvicorn app.main:app --port 8888)")
        return

    if resp.status_code != 200:
        print(f"请求失败 HTTP {resp.status_code}: {resp.text}")
        return

    final_text = ""

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            event = json.loads(line.decode("utf-8"))
        except Exception:
            continue

        evt_type = event.get("type")

        # 1. 渲染 Agent 流式打字机输出
        if evt_type == "chunk":
            chunk_text = event.get("text") or ""
            sys.stdout.write(chunk_text)
            sys.stdout.flush()

        # 2. 任务完成：直接输出校准后的最终内容
        elif evt_type == "done":
            data = event.get("data") or {}
            final_text = data.get("text") or ""
            print("\n\n" + final_text)

        elif evt_type == "error":
            print(f"\n[错误] {event.get('message')}")
            break


if __name__ == "__main__":
    main()
