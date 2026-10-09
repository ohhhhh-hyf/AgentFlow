"""会议议程输入准备与参数兼容性测试。"""
from __future__ import annotations

from app.schemas import Extra, TaskRequest
from app.tasks import _prepare


def test_agenda_minutes_input_assembly() -> None:
    """验证 agenda_minutes 支持 extra.agenda_txt 纯文本传参，并兼容老字段 agenda。"""
    # 1. 验证 Extra 模型解析
    e1 = Extra(agenda_txt="1. 汇报A\n2. 汇报B")
    assert e1.agenda_txt == "1. 汇报A\n2. 汇报B"
    e2 = Extra.model_validate({"agenda": "1. 汇报A\n2. 汇报B"})
    assert e2.agenda_txt == "1. 汇报A\n2. 汇报B"

    # 2. 验证 _prepare 提取 extra.agenda_txt
    req = TaskRequest(
        texts={"transcript": "发言者1：大家早上好，开始今天的会议。"},
        extra=Extra(agenda_txt="1. 议题一：大模型发布\n2. 议题二：算法压测"),
    )
    prep = _prepare("meeting", "agenda_minutes", req, "u123")
    assert prep.line == "agenda_minutes"
    agenda_input = prep.extra_line_inputs.get("agenda_minutes", "")
    assert "1. 议题一：大模型发布" in agenda_input
