"""端到端集成测试 (FastAPI TestClient):
验证统一入口 POST /api/agent/v1/stream 与 POST /api/agent/v1。
覆盖以下核心契约：
1. 流式 NDJSON 直出与 chunk / done 事件解析；
2. 用户级目录物理隔离落盘 (data/{user_id}/output/{request_id}/)；
3. 纪要仅产生 minutes.md，待办仅产生 actions.json；
4. 待办双态逻辑（传 time 走 Calendar 生成 actions + actions_update，未传 time 跳过 Calendar 仅生成 actions）；
5. 英文多语言后处理与序号罗马化；
6. Request-Id 与 User-Id 穿透传递。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from main import app

client = TestClient(app)


def test_health_check():
    """测试健康探针."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@patch("infra.llm.client.LLMClient.stream_text")
def test_stream_minutes_endpoint_user_isolation(mock_stream, tmp_path: Path):
    """测试 POST /api/agent/v1/stream: 流式 NDJSON 直出、用户隔离落盘与后处理."""
    # 模拟大模型输出带围栏与方括号的 Markdown
    async def _mock_stream_tokens(*args, **kwargs):
        yield "好的，为您整理如下纪要：\n```markdown\n"
        yield "# [全文摘要]\n本次会议研讨顺利。\n\n"
        yield "# [要点梳理]\n## [板块一]\n- 方案落地完成。\n"
        yield "```"

    mock_stream.side_effect = _mock_stream_tokens

    user_id = "test_user_001"
    request_id = "req_stream_abc123"

    req_body = {
        "task": "minutes",
        "texts": {
            "transcript": "今天召开核心系统架构评审会...",
        },
        "extra": {
            "template": "general_minutes",
        },
        "lang": "zh",
    }

    headers = {
        "X-User-Id": user_id,
        "X-Request-Id": request_id,
    }

    # 执行流式请求
    response = client.post("/api/agent/v1/stream", json=req_body, headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == request_id
    assert "application/x-ndjson" in response.headers.get("content-type", "")

    # 解析 NDJSON 事件帧
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    assert len(lines) >= 2  # 包含至少若干 chunk 和最后的 done

    done_event = None
    chunks = []
    for line in lines:
        evt = json.loads(line)
        if evt.get("type") == "chunk":
            chunks.append(evt.get("text", ""))
        elif evt.get("type") == "done":
            done_event = evt

    assert done_event is not None
    assert done_event["code"] == 0
    assert done_event["request_id"] == request_id
    assert done_event["data"]["file_name"] == "minutes.md"

    # 验证后处理清洗效果：方括号和代码围栏被剥离
    final_content = done_event["data"]["content"]
    assert "# 全文摘要" in final_content
    assert "[" not in final_content
    assert "```" not in final_content

    # 验证用户级隔离落盘路径
    expected_file = DEMO_ROOT / "data" / user_id / "output" / request_id / "minutes.md"
    assert expected_file.is_file()
    assert expected_file.read_text(encoding="utf-8") == final_content

    # 验证 output 目录下仅有 minutes.md，绝无其他冗余文件
    output_dir = expected_file.parent
    files = list(output_dir.iterdir())
    assert len(files) == 1
    assert files[0].name == "minutes.md"


@patch("infra.llm.client.LLMClient.stream_text")
def test_stream_minutes_english_localization(mock_stream):
    """测试英文模式下流式输出、英文模板与序号罗马化."""
    async def _mock_stream_tokens(*args, **kwargs):
        yield "# [Executive Summary]\nThe project has achieved all targets.\n\n"
        yield "## 一. [Infrastructure Update]\n- Completed cloud migration.\n"

    mock_stream.side_effect = _mock_stream_tokens

    user_id = "user_en_test"
    req_body = {
        "task": "minutes",
        "texts": {
            "transcript": "Project status review meeting...",
        },
        "extra": {
            "template": "general_minutes",
        },
        "lang": "en",
    }
    headers = {"X-User-Id": user_id}

    response = client.post("/api/agent/v1/stream", json=req_body, headers=headers)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    done_evt = json.loads(lines[-1])
    content = done_evt["data"]["content"]

    # 验证标题清洗与英文序号转换 (## 一. -> ## I.)
    assert "# Executive Summary" in content
    assert "## I. Infrastructure Update" in content


@patch("infra.llm.client.LLMClient.chat_json")
def test_sync_actions_dual_state_with_time(mock_chat_json):
    """测试 POST /api/agent/v1 (task='actions'): 态 A 传时间 -> 产出并落盘 actions + actions_update."""
    mock_chat_json.return_value = {
        "actions": [
            {
                "title": "性能压测",
                "item": "组织核心链路性能基准压测",
                "owner": "李四",
                "deadline": "明天18:00",
                "collaborators": ["张三"],
                "acceptance_criteria": "TPS > 3000",
                "dependency": None,
            }
        ]
    }

    user_id = "user_act_state_a"
    request_id = "req_act_with_time"

    req_body = {
        "task": "actions",
        "texts": {
            "transcript": "李四负责核心链路性能压测，明天18:00前完成...",
        },
        "extra": {
            "time": "2026-10-30 10:00:00",  # 传了时间 -> 态 A
        },
    }
    headers = {
        "X-User-Id": user_id,
        "X-Request-Id": request_id,
    }

    response = client.post("/api/agent/v1", json=req_body, headers=headers)
    assert response.status_code == 200
    res = response.json()

    assert res["code"] == 0
    assert res["request_id"] == request_id
    assert "actions" in res
    assert "actions_update" in res
    assert res["monitor"]["calendar_executed"] is True

    # 验证 actions_update 回填了绝对时间
    act_update = res["actions_update"][0]
    assert act_update["deadline_display"] == "2026/10/31 18:00"
    assert act_update["deadline"] == "2026-10-31T18:00:00"

    # 验证落盘文件包含两份
    expected_file = DEMO_ROOT / "data" / user_id / "output" / request_id / "actions.json"
    assert expected_file.is_file()
    disk_data = json.loads(expected_file.read_text(encoding="utf-8"))
    assert "actions" in disk_data
    assert "actions_update" in disk_data

    # 验证 output 目录下仅有 actions.json
    output_dir = expected_file.parent
    files = list(output_dir.iterdir())
    assert len(files) == 1
    assert files[0].name == "actions.json"


@patch("infra.llm.client.LLMClient.chat_json")
def test_sync_actions_dual_state_without_time(mock_chat_json):
    """测试 POST /api/agent/v1 (task='actions'): 态 B 未传时间 -> 跳过 Calendar，仅产出 actions."""
    mock_chat_json.return_value = {
        "actions": [
            {
                "title": "方案编写",
                "item": "梳理总体技术架构设计方案",
                "owner": "王五",
                "deadline": "下周五",
                "collaborators": [],
                "acceptance_criteria": "通过评审",
                "dependency": None,
            }
        ]
    }

    user_id = "user_act_state_b"
    request_id = "req_act_no_time"

    req_body = {
        "task": "actions",
        "texts": {
            "transcript": "王五负责总体技术架构设计方案，下周五前输出...",
        },
        "extra": {
            "time": "",  # 未传时间 -> 态 B
        },
    }
    headers = {
        "X-User-Id": user_id,
        "X-Request-Id": request_id,
    }

    response = client.post("/api/agent/v1", json=req_body, headers=headers)
    assert response.status_code == 200
    res = response.json()

    assert res["code"] == 0
    assert res["request_id"] == request_id
    assert "actions" in res
    assert "actions_update" not in res  # 态 B 绝不含 actions_update
    assert res["monitor"]["calendar_executed"] is False

    # 验证落盘文件仅包含 actions
    expected_file = DEMO_ROOT / "data" / user_id / "output" / request_id / "actions.json"
    assert expected_file.is_file()
    disk_data = json.loads(expected_file.read_text(encoding="utf-8"))
    assert "actions" in disk_data
    assert "actions_update" not in disk_data


@patch("infra.llm.client.LLMClient.stream_text")
def test_sync_minutes_endpoint(mock_stream):
    """测试 POST /api/agent/v1 (task='minutes'): 同步返回纪要."""
    async def _mock_stream_tokens(*args, **kwargs):
        yield "# 全文摘要\n同步接口生成成功。"

    mock_stream.side_effect = _mock_stream_tokens

    user_id = "user_sync_min"
    req_body = {
        "task": "minutes",
        "texts": {
            "transcript": "讨论内容...",
        },
        "extra": {
            "template": "general_minutes",
        },
    }
    headers = {"X-User-Id": user_id}

    response = client.post("/api/agent/v1", json=req_body, headers=headers)
    assert response.status_code == 200
    res = response.json()

    assert res["code"] == 0
    assert res["data"]["file_name"] == "minutes.md"
    assert "# 全文摘要" in res["data"]["content"]


def test_strict_contract_validation():
    """测试 TaskRequest 契约严格校验 (非法 key 拦截与非法语种拦截)."""
    # 1. 拦截 texts 中的非法 key (只允许 transcript, keypoints, notes, vision_info, actions_text)
    bad_req_1 = {
        "task": "minutes",
        "texts": {
            "transcript": "会议文本...",
            "illegal_custom_field": "some_value",
        },
    }
    resp1 = client.post("/api/agent/v1/stream", json=bad_req_1)
    assert resp1.status_code == 422
    assert "texts 只支持" in resp1.text

    # 2. 拦截未知语种 (仅支持 zh 与 en)
    bad_req_2 = {
        "task": "minutes",
        "texts": {"transcript": "会议文本..."},
        "lang": "fr",
    }
    resp2 = client.post("/api/agent/v1/stream", json=bad_req_2)
    assert resp2.status_code == 422
    assert "lang 仅支持 'zh' 或 'en'" in resp2.text

    # 3. 拦截 transcript 与 docs 同时为空
    empty_req = {
        "task": "minutes",
        "texts": {"transcript": ""},
        "docs": [],
    }
    resp3 = client.post("/api/agent/v1/stream", json=empty_req)
    assert resp3.status_code == 400


def test_docs_user_id_path_resolution():
    """测试 docs 图片文件名根据 user_id 准确物理寻址定位."""
    from tasks.minutes.agent import resolve_image_doc_path

    # 当 user_id='1'，传入文件名 '小艺语音技术委员会.png'
    resolved = resolve_image_doc_path(user_id="1", name="小艺语音技术委员会.png")
    assert resolved is not None
    assert resolved.is_file()
    assert resolved.name == "小艺语音技术委员会.png"
    assert "1" in resolved.parts
    assert "docs" in resolved.parts


@patch("infra.llm.client.LLMClient.chat_json")
def test_actions_text_in_actions_agent(mock_chat_json):
    """测试 actions_text 候选待办成功传入，并动态挂载进 Prompt."""
    mock_chat_json.return_value = {
        "actions": [
            {
                "title": "合同确认",
                "item": "EPC需提供合同确认函",
                "owner": "王工",
                "deadline": None,
                "collaborators": [],
                "acceptance_criteria": None,
                "dependency": None,
            }
        ]
    }

    req_body = {
        "task": "actions",
        "texts": {
            "transcript": "张总：王工，EPC合同确认函抓紧推进一下。王工：好的收到。",
            "actions_text": "1. EPC需提供合同确认函",
        },
    }
    headers = {"X-User-Id": "user_test_act_text"}

    response = client.post("/api/agent/v1", json=req_body, headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["code"] == 0
    assert len(res["actions"]) == 1
    assert res["actions"][0]["title"] == "合同确认"


def test_agenda_plan_schema_strict_validation():
    """测试 agenda_plan 强类型契约校验: 仅 title 必填，支持标准 items、VLM 直传与合法 JSON."""
    # 1. 最小合法报文: 仅传 title (其他字段自适应缺省)
    req_minimal = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": {
                "items": [
                    {"title": "自研芯片量产评审"}  # 仅 title
                ]
            }
        }
    }
    resp1 = client.post("/api/agent/v1/stream", json=req_minimal)
    assert resp1.status_code == 200

    # 2. 缺失必填字段 title 时拦截报 422
    req_no_title = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": {
                "items": [
                    {"seq": "01", "presenters": ["张三"]}  # 缺少核心必填 title
                ]
            }
        }
    }
    resp2 = client.post("/api/agent/v1/stream", json=req_no_title)
    assert resp2.status_code == 422

    # 3. title 为空字符串时拦截报 422
    req_empty_title = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": {
                "items": [
                    {"title": "   "}
                ]
            }
        }
    }
    resp3 = client.post("/api/agent/v1/stream", json=req_empty_title)
    assert resp3.status_code == 422

    # 4. 非法 JSON 字符串拦截报 422
    req_bad_json = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": "invalid json string {{"
        }
    }
    resp4 = client.post("/api/agent/v1/stream", json=req_bad_json)
    assert resp4.status_code == 422

    # 5. 合法 JSON 字符串反序列化并通过
    req_json_str = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": json.dumps({
                "meta": {"theme": "技术例会", "attendees": "张三；李四"},
                "items": [{"title": "算法调优", "presenters": ["李四"]}]
            })
        }
    }
    resp5 = client.post("/api/agent/v1/stream", json=req_json_str)
    assert resp5.status_code == 200

    # 6. VLM 团队直传扁平格式归一并通过
    req_vlm = {
        "task": "minutes",
        "texts": {"transcript": "发言者1：开会。"},
        "extra": {
            "agenda_plan": {
                "theme": "技术评审",
                "attendees": ["张三", "李四"],
                "agenda_items": [
                    {"title": "视觉多模态接口上线", "presenters": ["王工"]}
                ]
            }
        }
    }
    resp6 = client.post("/api/agent/v1/stream", json=req_vlm)
    assert resp6.status_code == 200
