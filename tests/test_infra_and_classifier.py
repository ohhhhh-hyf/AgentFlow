"""阶段二基础设施与智能模板自测 (零旧代码依赖)."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from infra.llm.config import resolve_llm_settings
from infra.llm.client import LLMClient
from infra.vlm.agenda_client import safe_load_json
from tasks.minutes.classifier.catalog import (
    AGENDA_CANDIDATE_IDS,
    NORMAL_CANDIDATE_IDS,
    build_classifier_system_prompt,
)
from tasks.minutes.classifier.classifier import TemplateClassifier, sample_transcript


def test_llm_config_resolution():
    """测试从 demo/.env 解析 LLM 配置."""
    settings = resolve_llm_settings()
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-chat"
    assert settings.api_key.startswith("sk-")
    assert settings.timeout == 60.0


def test_llm_config_resolution_vllm_mode(monkeypatch):
    """测试切换为服务器 vLLM 后端时的环境参数解析与请求组装."""
    monkeypatch.setenv("LLM_BACKEND", "vllm")
    monkeypatch.setenv("LLM_VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_VLLM_API_KEY", "EMPTY")
    monkeypatch.setenv("LLM_VLLM_MODEL", "deepseek-v4-flash-0731")
    monkeypatch.setenv("LLM_VLLM_TEMPERATURE", "0.2")

    settings = resolve_llm_settings()
    assert settings.backend == "vllm"
    assert settings.base_url == "http://127.0.0.1:8000/v1"
    assert settings.api_key == "EMPTY"
    assert settings.model == "deepseek-v4-flash-0731"
    assert settings.temperature == 0.2

    # 验证请求构建时 URL 和 Auth Header 完全匹配 vLLM OpenAI 规范
    client = LLMClient(settings=settings)
    req = client._build_request({"model": client.model, "messages": []})
    assert req.full_url == "http://127.0.0.1:8000/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer EMPTY"



def test_llm_extract_json():
    """测试 JSON 提纯与代码围栏剥离."""
    raw = "```json\n{\"template\": \"project_progress\", \"confidence\": 0.88}\n```"
    res = LLMClient.extract_json_payload(raw)
    assert res["template"] == "project_progress"
    assert res["confidence"] == 0.88

    raw_arr = "一些废话 [{\"title\": \"任务1\"}] 结尾说明"
    res_arr = LLMClient.extract_json_payload(raw_arr)
    assert isinstance(res_arr, list)
    assert res_arr[0]["title"] == "任务1"


def test_vlm_bracket_balancing_repair():
    """测试 VLM 截断 JSON 逆序自动补齐."""
    truncated = '{"theme": "大会", "agenda_items": [{"title": "议题1"'
    repaired = safe_load_json(truncated)
    assert repaired["theme"] == "大会"
    assert repaired["agenda_items"][0]["title"] == "议题1"


def test_candidate_counts():
    """测试候选场景数量: 议题模式恰好 20 个, 普通模式全量 29 个."""
    assert len(NORMAL_CANDIDATE_IDS) == 29
    assert len(AGENDA_CANDIDATE_IDS) == 20
    assert "general_minutes" in AGENDA_CANDIDATE_IDS
    assert "general_minutes" in NORMAL_CANDIDATE_IDS

    # 验证 Prompt 注入的候选集数量
    prompt_agenda = build_classifier_system_prompt(has_agenda=True)
    prompt_normal = build_classifier_system_prompt(has_agenda=False)
    assert sum(1 for cid in AGENDA_CANDIDATE_IDS if f"- {cid}" in prompt_agenda) == 20
    assert sum(1 for cid in NORMAL_CANDIDATE_IDS if f"- {cid}" in prompt_normal) == 29


def test_sample_transcript():
    """测试 12k 采样逻辑."""
    short_text = "这是一段很短的会议记录"
    assert sample_transcript(short_text) == short_text

    long_text = "A" * 20_000
    sampled = sample_transcript(long_text)
    assert len(sampled) < 20_000
    assert "...[中间内容截断]..." in sampled


@pytest.mark.anyio
async def test_classifier_flow():
    """测试智能分类器逻辑: 正常匹配、低置信度兜底、短文本快速返回."""
    mock_llm = AsyncMock()

    # 1. 高置信度匹配成功
    mock_llm.chat_json.return_value = {"template": "project_progress", "confidence": 0.92}
    clf = TemplateClassifier(llm_client=mock_llm)
    res = await clf.classify("这是一场关于技术方案与里程碑的项目会议" * 10, has_agenda=False)
    assert res == "project_progress"

    # 2. 低置信度 (< 0.70) 兜底 general_minutes
    mock_llm.chat_json.return_value = {"template": "project_progress", "confidence": 0.55}
    res_low = await clf.classify("这是一场关于技术方案与里程碑的项目会议" * 10, has_agenda=False)
    assert res_low == "general_minutes"

    # 3. 候选集越界 (议程模式下输出了非议程场景 debate_forum)
    mock_llm.chat_json.return_value = {"template": "debate_forum", "confidence": 0.95}
    res_out = await clf.classify("辩论会议记录" * 10, has_agenda=True)
    assert res_out == "general_minutes"

    # 4. 超短文本直接返回 general_minutes (不调模型)
    res_short = await clf.classify("太短了")
    assert res_short == "general_minutes"
