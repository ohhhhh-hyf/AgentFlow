# 拆分自原大文件，保留：test_court_transcript_template_and_concurrent_fill…

"""tests/unit/core/templates/test_column_projection.py -- 逐栏并发填充、直出快线与模型执行单元测试。"""

from __future__ import annotations
import logging
import re
import sys
from pathlib import Path
import pytest
from core.templates.router._base import iter_placeholders, split_template_meta
from core.templates.router._detect import parse_placeholder_template
from core.templates.router._gate import scan_fixed_bracket_literals, validate_rendered_output
from core.templates.router._placeholder import plan_placeholder_fill
from tests.support.expectations import expect
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
)

def test_court_transcript_template_and_concurrent_fill():
    """验证庭审记录模板增强及多栏+表格解耦并发填充能力。"""
    import asyncio
    import json
    from pathlib import Path
    from core.templates.router._placeholder import (
        fill_placeholder_template,
        plan_placeholder_fill,
        _scalar_titles,
    )

    court_tpl = Path("resources/templates/zh/court_transcript.md").read_text(encoding="utf-8")
    expect("证明目的" in court_tpl and "对方质证意见" in court_tpl, "庭审记录模板包含证明目的与质证细化规则", "")
    expect("明确标明诉讼当事人与法庭认定来源" in court_tpl and "程序节点准确还原" in court_tpl,
           "庭审记录模板保留来源与程序纪律", "")

    plan = plan_placeholder_fill(court_tpl)
    expect(len(plan["scalars"]) == 4, "庭审记录模板识别出4个标量栏", f"{len(plan['scalars'])}")
    expect(len(plan["row_templates"]) == 0, "庭审记录模板当前无表格行模板", f"{len(plan['row_templates'])}")
    titles = _scalar_titles(court_tpl)
    expect(titles == ["庭审概况", "诉辩意见", "举证质证", "庭审结果"], "标量栏目名称正确提取", f"{titles}")

    class _MockCourtClient:
        def __init__(self):
            self.stream_calls = []
            self.text_calls = []

        async def stream_text(self, system, user, **kwargs):
            self.stream_calls.append(user)
            if "（庭审概况）" in user:
                yield "本案系原告张某诉被告李某买卖合同纠纷案，由北京市海淀区人民法院依法公开开庭审理。"
            elif "（诉辩意见）" in user:
                yield "原告请求判令被告支付货款及逾期利息；被告辩称原告交付货物存在质量瑕疵。"
            elif "（举证质证）" in user:
                yield ("- **证据一**：《供货协议书》\n"
                       "  - **证明目的**：证明双方存在买卖合同关系及约定付款期限。\n"
                       "  - **对方质证意见**：被告认可协议真实性与签字。\n"
                       "- **法官询问**：李某是否已收到货款凭条？\n"
                       "  - **李某陈述**：李某表示尚未收到原告补寄发票。")
            elif "（庭审结果）" in user:
                yield "合议庭组织双方进行调解，双方均同意庭后协商调解方案。本案宣布休庭。"
            else:
                yield "正文内容"

        async def text(self, system, user, **kwargs):
            self.text_calls.append(user)
            return json.dumps({
                "tables": [
                    [
                        ["原告张某", "判令被告支付货款人民币50万元及逾期利息", "双方签订供货合同且原告已完成交付，被告逾期未付"],
                        ["被告李某", "请求驳回原告诉讼请求", "原告交付货物存在严重质量瑕疵且未开具增值税专用发票"],
                    ]
                ]
            })

    mock_client = _MockCourtClient()
    rendered = asyncio.run(fill_placeholder_template(mock_client, "庭审转写上下文", court_tpl, source_han=6000))
    expect(bool(rendered and len(rendered) > 100), "庭审记录并发填充成功产出渲染文本", "")
    expect(len(mock_client.stream_calls) == 4, "并发调用发生：4次流式标量栏调用", f"{len(mock_client.stream_calls)}")
    expect(len(mock_client.text_calls) == 0, "当前庭审模板无表格，不触发表格提取调用", f"{len(mock_client.text_calls)}")
    expect("证明目的" in rendered and "法官询问" in rendered, "产出中包含举证质证结构化条目", f"{rendered}")
