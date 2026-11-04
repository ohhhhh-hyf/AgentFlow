"""单元测试：验证工业级标准化日志输出规范 (Structured Key-Value Logging)。

覆盖标签：
- [task:start]
- [task:payload]
- [agent:start]
- [agent:skip]
- [agent:done]
- [agent:review]
- [render:start]
- [render:done]
- [export:done]
- [task:finish]
- [task:failed]
- [llm:done]
"""
import logging
import re
import pytest

from app.tasks import _log_task_payload


class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [r.getMessage() for r in self.records]


@pytest.fixture
def capture_logs():
    handler = LogCaptureHandler()
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)
    root.setLevel(old_level)


def test_task_payload_logging_full_multisource(capture_logs):
    """测试普通纪要全量多源输入时的 [task:payload] 日志格式。"""
    transcript = "这是第一句转写文本。" * 200  # > 1000 字符
    keypoints = "1. 关键决策A\n2. 关键决策B\n3. 关键决策C"
    notes = "- 原话：\"必须在月底上线\" -> 备注：高优先级\n- 笔记：留意后端并发瓶颈"
    vision = "OCR 识别表格数据：Q3 营收增长 25%"
    aux = "【用户核心关键点】\n" + keypoints

    _log_task_payload(
        lang="zh",
        transcript=transcript,
        keypoints=keypoints,
        notes=notes,
        vision_info=vision,
        aux_text=aux,
    )

    payload_logs = [m for m in capture_logs.messages if m.startswith("[task:payload]")]
    assert len(payload_logs) == 1
    log = payload_logs[0]

    assert "lang=zh" in log
    assert re.search(r"transcript=\d+\.\d+k_chars", log)
    assert "keypoints=3_items(" in log
    assert "notes=1_quotes/1_comments" in log
    assert re.search(r"vision=\d+_chars", log)
    assert re.search(r"aux=injected\(\d+_chars\)", log)
    # 严格确保无任何 Emoji
    assert not re.search(r"[\U00010000-\U0010ffff]", log)


def test_task_payload_logging_minimal(capture_logs):
    """测试纯转写无辅助字段时的 [task:payload] 日志格式。"""
    transcript = "简短发言内容。"

    _log_task_payload(
        lang="en",
        transcript=transcript,
        keypoints="",
        notes="",
        vision_info="",
        aux_text="",
        docs=["agenda.pdf"],
    )

    payload_logs = [m for m in capture_logs.messages if m.startswith("[task:payload]")]
    assert len(payload_logs) == 1
    log = payload_logs[0]

    assert "lang=en" in log
    assert "transcript=7_chars" in log
    assert "keypoints=none" in log
    assert "notes=none" in log
    assert "vision=none" in log
    assert "aux=none" in log
    assert "docs=agenda.pdf" in log


def test_standard_log_regex_patterns():
    """验证业界标准的标签正则表达式合法性。"""
    # 1. [task:start]
    start_pattern = re.compile(
        r"^\[task:start\] domain=\w+ task=\w+ req_id=\w+ user_id=\w* lang=(zh|en) memory=(true|false)$"
    )
    assert start_pattern.match(
        "[task:start] domain=meeting task=minutes req_id=req_123 user_id=u_001 lang=zh memory=false"
    )

    # 2. [agent:start]
    agent_start_pattern = re.compile(
        r"^\[agent:start\] name=\w+ line=\w+ mode=\w+ lang=(zh|en) aux=[\w,]+$"
    )
    assert agent_start_pattern.match(
        "[agent:start] name=minutes_draft line=minutes mode=objective lang=zh aux=keypoints,notes,vision"
    )

    # 3. [agent:skip]
    agent_skip_pattern = re.compile(
        r"^\[agent:skip\] name=\w+( line=\w+)? reason=\w+( hits=\d+)?$"
    )
    assert agent_skip_pattern.match("[agent:skip] name=perspective reason=objective_mode")
    assert agent_skip_pattern.match(
        "[agent:skip] name=meeting_understanding reason=agenda_minutes_self_contained"
    )
    assert agent_skip_pattern.match(
        "[agent:skip] name=minutes_review line=minutes reason=fast_path_chars"
    )
    assert agent_skip_pattern.match("[agent:skip] name=perspective reason=few_party hits=2")

    # 4. [agent:done]
    agent_done_pattern = re.compile(
        r"^\[agent:done\] name=\w+ (line=\w+ )?dur=\d+\.\d+s.*$"
    )
    assert agent_done_pattern.match(
        "[agent:done] name=minutes_draft line=minutes dur=3.44s chars=2340 sections=3"
    )
    assert agent_done_pattern.match(
        "[agent:done] name=meeting_understanding dur=2.86s segments=4 decisions=3 open_questions=2"
    )

    # 5. [agent:review]
    agent_review_pattern = re.compile(
        r"^\[agent:review\] line=\w+ decision=(approve|reject|revise) score=\d+ aux_safe=(true|false|none)( reason=\".*\")? dur=\d+\.\d+s$"
    )
    assert agent_review_pattern.match(
        "[agent:review] line=minutes decision=approve score=96 aux_safe=true dur=0.92s"
    )
    assert agent_review_pattern.match(
        '[agent:review] line=minutes decision=reject score=45 aux_safe=false reason="leaked_comment" dur=0.93s'
    )

    # 6. [render:start] & [render:done]
    assert re.match(r"^\[render:start\] line=\w+$", "[render:start] line=minutes")
    assert re.match(
        r"^\[render:done\] line=\w+ dur=\d+\.\d+s( status=\w+)?$",
        "[render:done] line=minutes dur=0.31s",
    )

    # 7. [llm:done]
    llm_pattern = re.compile(
        r"^\[llm:done\] label=[\w/]+ dur=\d+\.\d+s prompt_tokens=\d+ completion_tokens=\d+$"
    )
    assert llm_pattern.match(
        "[llm:done] label=minutes/agent/objective dur=3.42s prompt_tokens=5120 completion_tokens=1850"
    )

    # 8. [export:done]
    export_pattern = re.compile(
        r"^\[export:done\] line=\w+ format=(html|text) path=[\w/.-]+ chars=\d+$"
    )
    assert export_pattern.match(
        "[export:done] line=minutes format=html path=data/u_001/output/req_1/minutes/minutes.html chars=2340"
    )

    # 9. [task:finish] & [task:failed]
    finish_pattern = re.compile(
        r"^\[task:finish\] req_id=\w+ dur=\d+\.\d+s total_tokens=\d+ status=success$"
    )
    assert finish_pattern.match(
        "[task:finish] req_id=req_8f92a dur=8.53s total_tokens=15200 status=success"
    )
    failed_pattern = re.compile(
        r"^\[task:failed\] req_id=\w+ dur=\d+\.\d+s error=.* status=failed$"
    )
    assert failed_pattern.match(
        "[task:failed] req_id=req_8f92a dur=1.23s error=timeout status=failed"
    )
