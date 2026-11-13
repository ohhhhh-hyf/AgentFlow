"""Step 10 真实端到端集成验证脚本:
1. 启动本地 FastAPI 进程 (demo/main.py);
2. 验证流式纪要请求 (严格 TaskRequest: texts.transcript + extra.template);
3. 验证待办双态请求 (严格 TaskRequest: texts.transcript + texts.actions_text + extra.time);
4. 验证 docs 图片文件名基于 user_id 自动解析 (docs: ["小艺语音技术委员会.png"] + X-User-Id: 1);
5. 验证 422 严格契约校验 (拦截未知 texts 字段);
6. 验证日志系统落盘与英文标签;
7. 安全退出.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import requests


def main():
    print("=" * 70)
    print(">>> 启动 Step 10: 严格请求体契约与 Docs 用户物理寻址真实端到端验证")
    print("=" * 70)

    # 1. 启动后台 FastAPI 服务
    print("\n[Step 1] 启动 uvicorn demo 服务进程 (http://127.0.0.1:8000)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(DEMO_ROOT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(DEMO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # 使用直连 Session，避免本地测试请求被环境中的 HTTP_PROXY 代理劫持
        client_session = requests.Session()
        client_session.trust_env = False

        # 等待服务就绪
        server_ready = False
        for i in range(15):
            time.sleep(1)
            try:
                r = client_session.get("http://127.0.0.1:8000/health", timeout=2)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    server_ready = True
                    print(f"  ✓ 服务已就绪 (耗时 {i+1}s): {r.json()}")
                    break
            except Exception:
                pass

        if not server_ready:
            print("  ✗ 服务启动超时，退出...")
            return 1

        # 2. 验证 422 严格契约校验
        print("\n[Step 2] 验证 TaskRequest 严格契约校验 (拒绝未知 key 与未知语种)...")
        bad_req_1 = {
            "task": "minutes",
            "texts": {"transcript": "会议文本...", "custom_illegal_key": "123"},
        }
        r_bad1 = client_session.post("http://127.0.0.1:8000/api/agent/v1/stream", json=bad_req_1)
        assert r_bad1.status_code == 422, f"Expected 422, got {r_bad1.status_code}"
        assert "texts 只支持" in r_bad1.text
        print("  ✓ 成功拦截 texts 未知 key 注入 (HTTP 422)")

        bad_req_2 = {
            "task": "minutes",
            "texts": {"transcript": "会议文本..."},
            "lang": "de",
        }
        r_bad2 = client_session.post("http://127.0.0.1:8000/api/agent/v1/stream", json=bad_req_2)
        assert r_bad2.status_code == 422, f"Expected 422, got {r_bad2.status_code}"
        assert "lang 仅支持 'zh' 或 'en'" in r_bad2.text
        print("  ✓ 成功拦截不支持的语种代码 (HTTP 422)")

        # 3. 验证流式纪要直出 (严格契约: texts.transcript + extra.template)
        print("\n[Step 3] 验证纪要流式接口 (POST /api/agent/v1/stream, 严格 TaskRequest)...")
        stream_payload = {
            "task": "minutes",
            "texts": {
                "transcript": "张总：今天例会推进小艺语音项目，下周一内测。李明：后端接口调优完毕，响应时间大幅压降。王总：大家继续保持。"
            },
            "docs": [],
            "extra": {
                "template": "general_minutes"
            },
            "lang": "zh"
        }
        headers_stream = {
            "X-User-Id": "user_step10_stream",
            "X-Request-Id": "req_step10_stream_001"
        }
        t0 = time.time()
        r_stream = client_session.post(
            "http://127.0.0.1:8000/api/agent/v1/stream",
            json=stream_payload,
            headers=headers_stream,
            stream=True,
            timeout=60,
        )
        assert r_stream.status_code == 200
        first_chunk_time = None
        done_text = ""
        for line in r_stream.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue
            import json
            evt = json.loads(line_str)
            if evt.get("type") == "chunk" and first_chunk_time is None:
                first_chunk_time = time.time() - t0
            elif evt.get("type") == "done":
                done_text = evt.get("data", {}).get("content", "")

        print(f"  ✓ 流式响应完成: TTFT={first_chunk_time:.3f}s, 总耗时={time.time() - t0:.2f}s, 纪要字数={len(done_text)}")
        assert "# 全文摘要" in done_text
        assert "# 要点梳理" in done_text
        assert "# 结论定调" in done_text

        # 4. 验证待办任务 (严格契约: texts.transcript + texts.actions_text + extra.time)
        print("\n[Step 4] 验证待办接口 (POST /api/agent/v1, actions_text + Calendar 推导)...")
        actions_payload = {
            "task": "actions",
            "texts": {
                "transcript": "张总：李明，明天下午六点前把接口性能调优方案交给我。李明：好的收到。张总：另外王工，EPC合同确认函这周五前盖章归档。",
                "actions_text": "1. 接口性能调优方案\n2. EPC合同确认函"
            },
            "extra": {
                "time": "2026/11/13 14:00"
            }
        }
        headers_act = {
            "X-User-Id": "user_step10_act",
            "X-Request-Id": "req_step10_act_002"
        }
        t1 = time.time()
        r_act = client_session.post("http://127.0.0.1:8000/api/agent/v1", json=actions_payload, headers=headers_act, timeout=90)
        assert r_act.status_code == 200
        res_act = r_act.json()
        print(f"  ✓ 待办响应完成 (耗时 {time.time() - t1:.2f}s): {len(res_act.get('actions', []))} 个待办项")
        assert res_act["code"] == 0
        assert "actions" in res_act
        assert "actions_update" in res_act
        assert res_act["monitor"]["calendar_executed"] is True
        # 验证责任人和绝对时间推导
        act0 = res_act["actions_update"][0]
        print(f"    待办 1: title={act0.get('title')}, owner={act0.get('owner')}, deadline={act0.get('deadline_display')}")

        # 5. 验证 docs 图片文件名结合 X-User-Id 自动物理寻址
        print("\n[Step 5] 验证 docs 仅传文件名时，根据 X-User-Id: 1 自动定位物理路径...")
        docs_payload = {
            "task": "minutes",
            "texts": {
                "transcript": "张总：开始会议。李工：测试完毕。"
            },
            "docs": [
                "小艺语音技术委员会.png"  # 纯文件名，不带目录
            ],
            "extra": {
                "template": "general_minutes"
            }
        }
        headers_docs = {
            "X-User-Id": "1",  # 对应 demo/data/1/docs/小艺语音技术委员会.png
            "X-Request-Id": "req_step10_docs_003"
        }
        r_docs = client_session.post("http://127.0.0.1:8000/api/agent/v1/stream", json=docs_payload, headers=headers_docs, stream=True, timeout=90)
        assert r_docs.status_code == 200
        for _ in r_docs.iter_lines():
            pass  # 读完流

        # 6. 验证日志系统落盘与关键标签
        print("\n[Step 6] 验证日志追踪...")
        service_log = DEMO_ROOT / "logs" / "service.log"
        assert service_log.is_file()
        content = service_log.read_text(encoding="utf-8")
        assert "[AGENDA:INPUT]" in content
        assert "user_id=1 docs=['小艺语音技术委员会.png']" in content
        assert "[VLM:REQ] file=小艺语音技术委员会.png" in content
        print("  ✓ 日志证实 docs 纯文件名基于 X-User-Id: 1 精准定位到物理图片:")
        print("    - [AGENDA:INPUT] received docs_count=1 user_id=1 docs=['小艺语音技术委员会.png']")
        print("    - [VLM:REQ] file=小艺语音技术委员会.png")

        print("\n" + "=" * 70)
        print(">>> 恭喜！Step 10 严格请求体契约与 Docs 用户物理寻址真实验证全部成功！")
        print("=" * 70)
        return 0

    finally:
        print("\n[清理] 关闭后台 uvicorn 服务进程...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("  ✓ uvicorn 进程已关闭。")


if __name__ == "__main__":
    sys.exit(main())
