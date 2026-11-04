# 拆分自 test_column_fill.py，覆盖：test_column_extraction_robustness_and_timeout, test_column_fill_high_density_exemption…

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

pytestmark = pytest.mark.integration

def test_column_extraction_robustness_and_timeout() -> None:
    """分栏抽取宽容度与自适应超时容限测试：
    1. 首行多写标题自动去皮（# 标题、## 标题：、**标题**：、【标题】均安全剥离）
    2. 正文正常列表与加粗条目不被误剥离
    3. 模板拼装阶段单标题保证
    4. clean_template_render_text 剔除相邻同名冗余标题行
    5. empty_section_issues 豁免相邻同名标题不报空栏
    6. _stream_column 能够透传 timeout 参数给底层 stream_text
    """
    import asyncio
    from core.templates.router._placeholder import (
        _strip_redundant_column_heading,
        assemble_placeholder_output,
        _stream_column,
    )
    from core.execution.gate import (
        clean_template_render_text,
        empty_section_issues,
    )

    # 1. 首行多写各种标题变体
    c1 = _strip_redundant_column_heading("## 核心政策：\n1. 积极的财政政策\n2. 稳健的货币政策", "核心政策")
    expect(c1 == "1. 积极的财政政策\n2. 稳健的货币政策", "首行 ## 标题： 自动剥离", f"c1={c1}")

    c2 = _strip_redundant_column_heading("# 核心政策\n\n1. 积极的财政政策", "核心政策")
    expect(c2 == "1. 积极的财政政策", "首行 # 标题 自动剥离（含紧随空行）", f"c2={c2}")

    c3 = _strip_redundant_column_heading("**核心政策**：\n- 措施一\n- 措施二", "核心政策")
    expect(c3 == "- 措施一\n- 措施二", "首行 **标题**： 自动剥离", f"c3={c3}")

    c4 = _strip_redundant_column_heading("【核心政策】\n1. 措施一", "核心政策")
    expect(c4 == "1. 措施一", "首行 【标题】 自动剥离", f"c4={c4}")

    # 2. 正常正文不误剥离
    c5 = _strip_redundant_column_heading("1. 积极推进核心政策的落地与执行。", "核心政策")
    expect(c5 == "1. 积极推进核心政策的落地与执行。", "正文正常句子包含栏名不被误剥离", f"c5={c5}")

    c6 = _strip_redundant_column_heading("- **核心政策**：本年度持续优化营商环境。", "核心政策")
    expect(c6 == "- **核心政策**：本年度持续优化营商环境。", "正文行首列表项不被误剥离", f"c6={c6}")

    # 3. 模板拼装阶段单标题保证
    tpl = "# 政府报告\n\n# [核心政策]\n[写核心政策]\n\n# [重点工作]\n[写重点工作]\n"
    fields = {
        "1": "## 核心政策：\n1. 财政支持加力",
        "2": "**重点工作**\n1. 推进产业升级",
    }
    assembled = assemble_placeholder_output(tpl, fields)
    expect("## 核心政策" not in assembled and "**重点工作**" not in assembled
          and "# 核心政策" in assembled and "1. 财政支持加力" in assembled
          and "# 重点工作" in assembled and "1. 推进产业升级" in assembled, "assemble_placeholder_output 自动净化首行冗余标题", f"assembled={assembled}")

    # 4. clean_template_render_text 剔除相邻同名冗余标题行
    dirty = "# 核心政策\n## 核心政策：\n1. 财政支持加力\n"
    cleaned, notes = clean_template_render_text(dirty)
    expect("## 核心政策" not in cleaned and "# 核心政策" in cleaned and "1. 财政支持加力" in cleaned, "clean_template_render_text 剔除相邻同名冗余标题", f"cleaned={cleaned}, notes={notes}")

    # 5. empty_section_issues 豁免相邻同名标题不报空栏
    raw_dup = "# 核心政策\n# 核心政策\n1. 财政支持加力\n"
    issues = empty_section_issues(raw_dup, tpl)
    expect(not any("核心政策" in is_ for is_ in issues), "empty_section_issues 豁免相邻同名标题不报空栏", f"issues={issues}")

    # 6. _stream_column 能够透传 timeout 参数与采样惩罚参数
    class MockStreamClient:
        def __init__(self):
            self.passed_kwargs = {}
        async def stream_text(self, system, user, **kwargs):
            self.passed_kwargs = kwargs
            yield "测试内容"

    client = MockStreamClient()
    out = asyncio.run(_stream_column(client, "user", cap=1000, ceiling=2000, label="test", timeout=95.0, presence_penalty=0.15, temperature=0.35))
    expect(client.passed_kwargs.get("timeout") == 95.0
          and client.passed_kwargs.get("presence_penalty") == 0.15
          and client.passed_kwargs.get("temperature") == 0.35
          and out == "测试内容", "_stream_column 成功透传 timeout 与采样惩罚参数", f"{client.passed_kwargs}")

    # 7. 清单/重点工作栏目前置注入【要点纪律】，普通栏目不注入
    from core.templates.router._placeholder import _column_fill_user, plan_placeholder_fill, fill_placeholder_by_columns
    u_work = _column_fill_user("context", "# [重点工作]\n[写工作]", index=1, total=1, hint="", title="重点工作", others=[])
    expect("【要点纪律】" in u_work and "严禁循环复述" in u_work, "重点工作栏目提示词前置注入要点纪律", f"{u_work}")
    u_time = _column_fill_user("context", "# [会议时间]\n[写时间]", index=1, total=1, hint="", title="会议时间", others=[])
    expect("【要点纪律】" not in u_time, "普通非清单栏目不注入要点纪律", f"{u_time}")

    # 8. fill_placeholder_by_columns 对重栏目首轮施加 presence_penalty=0.15
    class _CaptureStreamClient:
        def __init__(self):
            self.calls = []
        async def stream_text(self, system, user, **kwargs):
            self.calls.append(kwargs)
            yield "1. 扎实推进产业创新升级。\n2. 深入实施绿色低碳转型。"

    tpl_heavy = "# 政府工作\n\n# [重点工作]\n[写重点工作]\n"
    plan_heavy = plan_placeholder_fill(tpl_heavy)
    cap_client = _CaptureStreamClient()
    # 只取副作用（填充 cap_client.calls），返回值本身不用
    asyncio.run(fill_placeholder_by_columns(cap_client, "context", tpl_heavy, plan_heavy))
    expect(len(cap_client.calls) > 0 and cap_client.calls[0].get("presence_penalty") == 0.15, "重点工作首轮调用自动配置 presence_penalty=0.15", f"{cap_client.calls}")

    # 9. LLMClient._stream_sync 序列化 presence_penalty 与 frequency_penalty
    from infra.llm.client import LLMClient
    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = [b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n', b'data: [DONE]\n\n']
    captured_req = []
    with patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: (captured_req.append(req), mock_resp)[1]):
        llm = LLMClient(api_key="sk-test", base_url="http://fake.api", model="test-model", provider="openai")
        # 只取副作用（消费生成器以触发 urlopen 并填充 captured_req）
        list(llm._stream_sync([{"role": "user", "content": "hi"}], presence_penalty=0.2, frequency_penalty=0.1))
        import json
        req_body = json.loads(captured_req[0].data.decode("utf-8"))
        expect(req_body.get("presence_penalty") == 0.2 and req_body.get("frequency_penalty") == 0.1, "LLMClient 请求体包含 presence_penalty 与 frequency_penalty", f"{req_body}")


def test_column_fill_high_density_exemption() -> None:
    """验证高信息密度重点事实栏（新闻发布会核心信息、法庭举证等）免于过度重写。

    - 新闻发布会第 2 栏 [核心信息]：按模板要求合并指标与举措，即使 2 条每条 310 字（>280 且 count=2），
      识别为高密度事实栏（放宽阈值至 380），不触发多余单栏重写；
    - 庭审记录第 2 栏 [举证与法庭调查]：明确声明「不设字数上限、写全优先」，详细质证条目（320 字）直接放行；
    - 对比项新闻发布会第 3 栏 [官方表态]：属于显式字数约束栏（每条 40–120 字），超长时仍严格受控重写。
    """
    import asyncio
    import re as _re
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    # 1. 新闻发布会核心信息栏测试
    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan_mb = plan_placeholder_fill(mb)

    # 2 条每条约 310 字的高密度政策与多指标条目
    dense_bullet = "- **政策措施**：" + "本季度落实增量政策工具并下达投资预算" * 15 + "。"  # ~310 字
    two_dense_bullets = dense_bullet + "\n" + dense_bullet

    good_mb = {
        1: "发布会概况：主办方与整体基调。",
        3: "- **表态**：官方口径一条。",
        4: "**主持人**：提问？\n**发言人**：回答。",
    }

    class _ClientMB:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield two_dense_bullets if idx == 2 else good_mb[idx]

    c_mb = _ClientMB()
    text_mb = asyncio.run(
        fill_placeholder_by_columns(
            c_mb, "内容来源略。", mb, plan_mb, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c_mb.counts.get(2) == 1, "高密度豁免：新闻发布会[核心信息]包含2条310字详实条目时不触发重写（仅1次调用）", f"{c_mb.counts}")
    expect("增量政策工具" in (text_mb or ""), "高密度豁免：核心信息正文完整保留", "")

    # 2. 庭审记录 [举证与法庭调查] 测试
    court = (_active_dir() / "court_transcript.md").read_text(encoding="utf-8")
    plan_court = plan_placeholder_fill(court)

    # 举证栏详细质证条目（约 320 字）
    evidence_bullet = (
        "- **证据一(原告提交供货单及对账确认函)**：证明原告已于约定时间足额供货，"
        + "被告对真实性无异议但辩称存在质量瑕疵未能如期投产故拒绝结算尾款" * 8 + "。"
    )
    good_court = {
        1: "庭审概况：案号与当事人。",
        2: "诉辩意见：原告请求供货款，被告辩称质量瑕疵。",
        4: "- **庭审结果**：择期宣判。",
    }

    class _ClientCourt:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield evidence_bullet if idx == 3 else good_court.get(idx, "内容。")

        async def text(self, *a, **kw):
            return '{"tables": [[["原告", "诉讼请求", "事实理由"]]]}'

    c_court = _ClientCourt()
    text_court = asyncio.run(
        fill_placeholder_by_columns(
            c_court, "内容来源略。", court, plan_court, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    expect(c_court.counts.get(3) == 1, "高密度豁免：庭审记录[举证质证]详实证据条目不触发重写（仅1次调用）", f"{c_court.counts}")
    expect("对账确认函" in (text_court or ""), "高密度豁免：法庭调查举证正文完整保留", "")
