"""api_test/minutes_stream.py -- 会议纪要流式直出接口单次文本测试脚本.

用法:
    1. 在下方 TRANSCRIPT 中填入待测试的会议转写文本;
    2. 按需调整 BASE_URL、docs 或 extra.template (如留空自动分类，或指定 general_minutes);
    3. 运行: python api_test/minutes_stream.py
"""
import json
import os
import sys
import uuid

import requests

# ── 会议转写文本（可直接在此替换测试文本）──
TRANSCRIPT = """
张总：大家下午好，今天开会主要过一下语音模型服务的压测与上线排期。
李工：我们后端针对高并发场景进行了连接复用和动态批处理优化，首字响应延迟（TTFT）从原本的 1.8 秒压降到了 0.77 秒，QPS 提升了 40%。
王工：前端对接工作已经全部就绪，接口联调完成，建议按原计划于下周一启动全量内测。
张总：很好。这个优化方案正式通过。李工在周五前提交完整的基准压测报告，王工负责在周一前配置好内测灰度名单。今天会议就到这里，散会。
""".strip()

# ── 默认服务地址 (可通过环境变量 AGENTFLOW_BASE_URL 覆盖) ──
BASE_URL = os.getenv("AGENTFLOW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
STREAM_URL = f"{BASE_URL}/api/agent/v1/stream"
USER_ID = "1"


def main():
    if not TRANSCRIPT.strip():
        print("[提示] TRANSCRIPT 文本为空，请在脚本顶部填入待测试的会议转写内容。")
        return

    # 严格对齐当前工程的 TaskRequest 契约规范
    payload = {
        "task": "minutes",
        "texts": {
            "transcript": TRANSCRIPT,
            "keypoints": "",
            "notes": "",
            "vision_info": "",
        },
        "docs": [],  # 可选：如需测试议程图片可填 ["月度洞察会.png"]，系统自动寻址 data/{user_id}/docs/
        "extra": {
            "template": "general_minutes",  # 模板名称（留空则自动智能分类）
            "time": "",                     # 会议时间
        },
        "lang": "zh",
    }

    headers = {
        "X-Request-Id": uuid.uuid4().hex,
        "X-User-Id": USER_ID,
    }

    session = requests.Session()
    # 如果目标是本地服务，禁用代理避免被环境中的本地代理劫持导致连接超时
    if "127.0.0.1" in BASE_URL or "localhost" in BASE_URL:
        session.trust_env = False

    print(f"正在请求流式接口: {STREAM_URL}")
    print(f"用户 ID: {USER_ID}, 请求 ID: {headers['X-Request-Id']}")
    print("-" * 60)

    try:
        resp = session.post(
            STREAM_URL,
            json=payload,
            headers=headers,
            stream=True,
            timeout=300,
        )
    except Exception as exc:
        print(f"请求服务失败: {exc}")
        print("请确认后台服务已启动 (如: uvicorn main:app --host 127.0.0.1 --port 8000)")
        return

    if resp.status_code != 200:
        print(f"请求失败 HTTP {resp.status_code}: {resp.text}")
        return

    final_text = ""

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue
            event = json.loads(line_str)
        except Exception:
            continue

        evt_type = event.get("type")

        # 1. 流式输出实时 Chunk
        if evt_type == "chunk":
            chunk_text = event.get("text") or ""
            sys.stdout.write(chunk_text)
            sys.stdout.flush()

        # 2. 任务完成：输出最终校准与清洗后的内容
        elif evt_type == "done":
            data = event.get("data") or {}
            final_text = data.get("text") or data.get("content") or ""
            cost_time = event.get("monitor", {}).get("cost_time", "")
            req_id = event.get("request_id", "")
            print("\n" + "=" * 60)
            print(f"[完成] request_id={req_id} 耗时={cost_time}s")
            print("=" * 60)

        elif evt_type == "error":
            print(f"\n[错误] {event.get('message')}")
            break


if __name__ == "__main__":
    main()
