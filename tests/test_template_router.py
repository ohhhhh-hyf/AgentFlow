"""模板路由：判型 / 保真 / 拼装 / 校验 单测（不依赖真实 LLM）。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.template_router import (  # noqa: E402
    assemble_placeholder_output,
    check_compile_fidelity,
    clear_compile_caches,
    detect_template_kind,
    extract_description_cues,
    fill_placeholder_template,
    maybe_compile_natural_template,
    normalize_fill_tables,
    parse_fill_response,
    parse_placeholder_template,
    plan_placeholder_fill,
    route_template,
    split_spec_template,
    validate_rendered_output,
)


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    clear_compile_caches()
    monkeypatch.delenv("TEMPLATE_ROUTER", raising=False)
    yield
    clear_compile_caches()


# ── 判型 ──────────────────────────────────────────────────────


class TestDetectKind:
    def test_placeholder(self):
        text = "# [会议主题]\n\n- 时间：[填写时间；未明确则写\"未提及\"]"
        assert detect_template_kind(text) == "placeholder"

    def test_spec(self):
        text = (
            "# 输出格式\n严格输出 JSON 数组\n"
            "# 示例\n输入：张三\n输出：[]\n"
        )
        assert detect_template_kind(text) == "spec"

    def test_natural(self):
        text = "第一行是标题，括号里写时间和人物，下面一段总结。"
        assert detect_template_kind(text) == "natural"

    def test_markdown_link_not_placeholder(self):
        text = "详见 [文档](https://example.com) 说明输出格式"
        # 无真占位符、无 spec 双信号 → natural
        assert detect_template_kind(text) == "natural"

    def test_empty_is_natural(self):
        assert detect_template_kind("") == "natural"


# ── 解析 / 路由 ───────────────────────────────────────────────


class TestParseAndRoute:
    def test_parse_fields_and_enum(self):
        tpl = "状态：[✅已完成 / 🔄进行中 / 未明确]\n主题：[会议主题]"
        segs = parse_placeholder_template(tpl)
        fields = [s for s in segs if s["kind"] == "field"]
        assert len(fields) == 2
        assert fields[0]["enum"] is not None
        assert "已完成" in fields[0]["enum"][0] or any(
            "已完成" in e for e in fields[0]["enum"]
        )
        assert fields[1]["hint"] == "会议主题"

    def test_route_placeholder(self):
        tpl = "# [主题]\n[正文；未明确则写\"未提及\"]"
        routed = route_template("ctx", tpl, "RP", "TP")
        assert routed is not None
        prompt, user = routed
        assert "占位符模板" in prompt
        assert "字段1" in user
        assert "ctx" in user

    def test_route_spec(self):
        tpl = (
            "严格输出 JSON 数组\n"
            "# 示例\n输入：a\n输出：[]\n"
        )
        routed = route_template("ctx", tpl, "RP", "TP")
        assert routed is not None
        prompt, user = routed
        assert "格式规范模板" in prompt
        assert "【格式指令】" in user
        assert "【示例" in user

    def test_split_spec(self):
        tpl = "指令段\n# 示例\n示例段"
        inst, ex = split_spec_template(tpl)
        assert inst == "指令段"
        assert "示例段" in ex

    def test_router_off(self, monkeypatch):
        monkeypatch.setenv("TEMPLATE_ROUTER", "off")
        tpl = "# [主题]"
        assert route_template("c", tpl, "RP", "TP") is None


# ── 自然语言保真 ─────────────────────────────────────────────


class TestFidelity:
    def test_cues_minimal_three_parts(self):
        desc = "只要三部分：进展、问题、下一步，简洁一点"
        cues = extract_description_cues(desc)
        assert cues["minimal"] is True
        assert "progress" in cues["flags"]
        assert "problem" in cues["flags"]
        assert "next" in cues["flags"]
        assert cues["section_count"] == 3

    def test_reject_over_expansion(self):
        desc = "只要三部分：进展、问题、下一步"
        # 编译结果擅自加参会人、决策、待办大表
        compiled = """# [标题]

## 参会人
[列出参会人]

## 进展
[进展]

## 问题
[问题]

## 下一步
[下一步]

## 决策事项
| 决策 | 说明 |
| --- | --- |
| [决策] | [说明] |

## 待办事项
| 任务 | 负责人 |
| --- | --- |
| [任务] | [负责人] |
"""
        issues = check_compile_fidelity(desc, compiled)
        assert issues, "应检出过度扩写"
        joined = "；".join(issues)
        assert "参会" in joined or "待办" in joined or "决策" in joined or "部分" in joined

    def test_accept_faithful_short(self):
        desc = "只要三部分：进展、问题、下一步"
        compiled = """## 进展
[根据内容写进展；未明确则写"未提及"]

## 问题
[根据内容写问题；未明确则写"未提及"]

## 下一步
[根据内容写下一步；未明确则写"未提及"]
"""
        issues = check_compile_fidelity(desc, compiled)
        assert issues == []

    def test_missing_user_mentioned_structure(self):
        desc = "第一行标题，下面写时间和参会人"
        compiled = "# [标题]\n\n[正文]"
        issues = check_compile_fidelity(desc, compiled)
        assert any("time" in x or "时间" in x or "people" in x or "参会" in x for x in issues)


# ── 拼装稳定性 ───────────────────────────────────────────────


class TestAssemble:
    def test_scalar_assemble_preserves_fixed_text(self):
        tpl = "# [主题]\n\n- **时间**：[时间；未明确则写\"未提及\"]\n"
        out = assemble_placeholder_output(
            tpl, {"1": "验收会", "2": "周一"}
        )
        assert out.startswith("# 验收会")
        assert "**时间**" in out
        assert "周一" in out
        assert "[" not in out

    def test_missing_default(self):
        tpl = "时间：[时间；未明确则写\"未提及\"]"
        out = assemble_placeholder_output(tpl, {"1": ""})
        assert "未提及" in out

    def test_table_row_expand(self):
        tpl = (
            "| 任务 | 负责人 |\n"
            "| --- | --- |\n"
            "| [任务] | [负责人] |\n"
        )
        plan = plan_placeholder_fill(tpl)
        assert plan["row_line"] is not None
        assert len(plan["row_fields"]) == 2
        out = assemble_placeholder_output(
            tpl,
            {},
            table_rows=[["写文档", "李工"], ["联调", "王工"]],
        )
        assert "| 写文档 | 李工 |" in out
        assert "| 联调 | 王工 |" in out
        assert "| 任务 | 负责人 |" in out
        assert "[任务]" not in out

    def test_mixed_scalars_and_table(self):
        tpl = (
            "# [标题]\n\n"
            "| 项 | 值 |\n"
            "| --- | --- |\n"
            "| [项] | [值] |\n"
        )
        out = assemble_placeholder_output(
            tpl,
            {"1": "纪要"},
            table_rows=[["A", "1"], ["B", "2"]],
        )
        assert out.startswith("# 纪要")
        assert "| A | 1 |" in out
        assert "| B | 2 |" in out

    def test_multi_table_sample_minutes(self):
        path = ROOT / "samples/meeting/minutes_generation_template/simple_minutes.md"
        if not path.exists():
            pytest.skip("sample missing")
        tpl = path.read_text(encoding="utf-8")
        plan = plan_placeholder_fill(tpl)
        assert len(plan["row_templates"]) == 2
        fields = {str(i + 1): f"S{i+1}" for i in range(len(plan["scalars"]))}
        tables = [
            [["决策A", "说明A"], ["决策B", "说明B"]],
            [["任务1", "张三", "周一"], ["任务2", "李四", "周二"]],
        ]
        out = assemble_placeholder_output(tpl, fields, tables=tables)
        assert "| 决策A | 说明A |" in out
        assert "| 任务1 | 张三 | 周一 |" in out
        assert validate_rendered_output(out, tpl) == []
        assert "[原文" not in out

    def test_validate_assembled(self):
        tpl = "# [主题]\n\n正文：[内容]"
        out = assemble_placeholder_output(tpl, ["Hello", "World"])
        assert validate_rendered_output(out, tpl) == []

    def test_validate_leftover_placeholder(self):
        tpl = "# [主题]"
        assert validate_rendered_output("# [主题]", tpl)

    def test_normalize_drops_empty_keeps_all_nonempty(self):
        """通用清洗：只去空行、对齐列，不按业务规则截断行数。"""
        tpl = (
            "| 风险 | 等级 |\n"
            "| --- | --- |\n"
            "| [风险描述] | [高/中/低] |\n"
        )
        plan = plan_placeholder_fill(tpl)
        tables = [[
            ["r1", "高"],
            ["", ""],
            ["r2", "中"],
            ["r3", "低"],
            ["r4", "高"],
        ]]
        norm = normalize_fill_tables(tables, plan["row_templates"])
        assert len(norm[0]) == 4
        assert all(any(c.strip() for c in row) for row in norm[0])

    def test_assemble_no_blank_table(self):
        tpl = (
            "| 事项 | 人 |\n"
            "| --- | --- |\n"
            "| [事项] | [人] |\n"
        )
        out = assemble_placeholder_output(tpl, {}, tables=[[]])
        assert "未提及" in out

    def test_assemble_table_rows_always_newline(self):
        """模板末行无换行时，多行展开仍须每行独立，不能 || 粘连。"""
        # 故意不加末尾 \n，模拟文件最后一行
        tpl = (
            "| 风险 | 等级 |\n"
            "| --- | --- |\n"
            "| [风险描述] | [高/中/低]"
        )
        out = assemble_placeholder_output(
            tpl,
            {},
            tables=[[["开裂", "高"], ["排水", "中"], ["交通", "中"]]],
        )
        assert "||" not in out.replace("| --- | --- |", "")
        lines = [ln for ln in out.splitlines() if ln.startswith("|") and "---" not in ln]
        # 表头 + 3 数据行
        assert len(lines) == 4
        assert any("开裂" in ln and "排水" not in ln for ln in lines)

    def test_fill_prompt_is_generic(self):
        """填充 prompt 应强调「读模板原文约束」，而非写死栏目名。"""
        from tools.template_router import (
            _PLACEHOLDER_FILL_SYSTEM,
            build_placeholder_fill_user,
        )

        assert "约束" in _PLACEHOLDER_FILL_SYSTEM
        assert "风险表" not in _PLACEHOLDER_FILL_SYSTEM
        assert "待办表" not in _PLACEHOLDER_FILL_SYSTEM
        user = build_placeholder_fill_user(
            "ctx",
            "## 任意（约2行）\n| 甲 | 乙 |\n| --- | --- |\n| [列一] | [列二] |\n",
        )
        assert "模板原文" in user
        assert "tables[0]" in user


class TestParseFillResponse:
    def test_dict_fields_and_rows(self):
        raw = json.dumps(
            {"fields": {"1": "t", "2": "x"}, "rows": [["a", "b"]]},
            ensure_ascii=False,
        )
        fields, rows, tables = parse_fill_response(raw)
        assert fields["1"] == "t"
        assert rows == [["a", "b"]]
        assert tables == [[["a", "b"]]]

    def test_code_fence(self):
        raw = '```json\n{"fields": {"1": "ok"}, "rows": []}\n```'
        fields, rows, tables = parse_fill_response(raw)
        assert fields["1"] == "ok"
        assert rows == []
        assert tables == []

    def test_multi_tables(self):
        raw = json.dumps(
            {
                "fields": {"1": "t"},
                "tables": [[["d1", "s1"]], [["a", "o", "dl"]]],
            },
            ensure_ascii=False,
        )
        fields, rows, tables = parse_fill_response(raw)
        assert fields["1"] == "t"
        assert len(tables) == 2
        assert tables[1][0] == ["a", "o", "dl"]


# ── 编译（mock LLM）──────────────────────────────────────────


class TestCompileMocked:
    def test_non_natural_passthrough(self):
        tpl = "# [主题]"
        out = asyncio.run(maybe_compile_natural_template(tpl))
        assert out == tpl

    def test_compile_success_with_fidelity(self):
        desc = "只要两部分：进展和问题"

        async def fake_text(system, user):
            return (
                "## 进展\n[写进展；未明确则写\"未提及\"]\n\n"
                "## 问题\n[写问题；未明确则写\"未提及\"]\n"
            )

        client = MagicMock()
        client.temperature = 0.2
        client.text = AsyncMock(side_effect=fake_text)

        with patch("llm_client.LLMClient", return_value=client):
            # _client_text imports LLMClient inside maybe_compile via from llm_client import
            with patch(
                "tools.template_router._client_text",
                new=AsyncMock(
                    return_value=(
                        "## 进展\n[写进展；未明确则写\"未提及\"]\n\n"
                        "## 问题\n[写问题；未明确则写\"未提及\"]\n"
                    )
                ),
            ):
                out = asyncio.run(
                    maybe_compile_natural_template(
                        desc, domain="meeting", line_name="minutes_generation"
                    )
                )
        assert detect_template_kind(out) == "placeholder"
        assert "进展" in out and "问题" in out
        assert "参会" not in out

    def test_compile_retries_on_bad_fidelity(self):
        desc = "只要进展和问题两段"

        bloated = """# [标题]
## 参会人
[人]
## 进展
[进展]
## 问题
[问题]
## 待办事项
| 任务 | 负责人 |
| --- | --- |
| [任务] | [人] |
"""
        good = (
            "## 进展\n[进展；未明确则写\"未提及\"]\n\n"
            "## 问题\n[问题；未明确则写\"未提及\"]\n"
        )
        calls = {"n": 0}

        async def fake_client_text(client, system, user, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return bloated
            return good

        with patch(
            "tools.template_router._client_text", new=fake_client_text
        ):
            with patch("llm_client.LLMClient", return_value=MagicMock()):
                out = asyncio.run(maybe_compile_natural_template(desc))
        assert calls["n"] == 2
        assert "待办" not in out
        assert check_compile_fidelity(desc, out) == []

    def test_cache_key_differs_by_line(self):
        desc = "只要一个标题和一段总结"
        good = "# [标题]\n\n[总结；未明确则写\"未提及\"]"
        calls = {"n": 0}

        async def fake_client_text(client, system, user, **kwargs):
            calls["n"] += 1
            return good + "\n"

        with patch(
            "tools.template_router._client_text", new=fake_client_text
        ):
            with patch("llm_client.LLMClient", return_value=MagicMock()):
                a = asyncio.run(
                    maybe_compile_natural_template(
                        desc, domain="meeting", line_name="minutes_generation"
                    )
                )
                b = asyncio.run(
                    maybe_compile_natural_template(
                        desc, domain="meeting", line_name="minutes_generation"
                    )
                )
                c = asyncio.run(
                    maybe_compile_natural_template(
                        desc, domain="notes", line_name="points"
                    )
                )
        assert a == b == good
        # 同 domain+line 命中缓存 → 只调 1 次；换 line 再调 1 次
        assert calls["n"] == 2
        assert c == good


class TestFillPlaceholderMocked:
    def test_fill_success(self):
        tpl = "# [主题]\n\n- **时间**：[时间；未明确则写\"未提及\"]\n"
        payload = json.dumps(
            {"fields": {"1": "验收会", "2": "周五"}, "rows": []},
            ensure_ascii=False,
        )

        client = MagicMock()
        client.temperature = 0.5

        async def fake_text(client, system, user, **kwargs):
            return payload

        with patch("tools.template_router._client_text", new=fake_text):
            out = asyncio.run(fill_placeholder_template(client, "ctx", tpl))
        assert out is not None
        assert "验收会" in out
        assert "周五" in out
        assert validate_rendered_output(out, tpl) == []

    def test_fill_table(self):
        tpl = (
            "| 任务 | 负责人 |\n"
            "| --- | --- |\n"
            "| [任务] | [负责人] |\n"
        )
        payload = json.dumps(
            {
                "fields": {},
                "rows": [["文档", "李"], ["联调", "王"]],
            },
            ensure_ascii=False,
        )

        async def fake_text(client, system, user, **kwargs):
            return payload

        with patch("tools.template_router._client_text", new=fake_text):
            out = asyncio.run(
                fill_placeholder_template(MagicMock(), "ctx", tpl)
            )
        assert out is not None
        assert "| 文档 | 李 |" in out
        assert "| 联调 | 王 |" in out


# ── 真实样例文件判型 ──────────────────────────────────────────


class TestSampleFiles:
    def test_simple_minutes_placeholder(self):
        path = ROOT / "samples/meeting/minutes_generation_template/simple_minutes.md"
        if not path.exists():
            pytest.skip("sample missing")
        text = path.read_text(encoding="utf-8")
        assert detect_template_kind(text) == "placeholder"

    def test_action_items_spec(self):
        path = ROOT / "samples/meeting/action_items_template/action_items.md"
        if not path.exists():
            pytest.skip("sample missing")
        text = path.read_text(encoding="utf-8")
        assert detect_template_kind(text) == "spec"

    def test_natural_sample(self):
        path = ROOT / "samples/meeting/minutes_generation_template/test.md"
        if not path.exists():
            pytest.skip("sample missing")
        text = path.read_text(encoding="utf-8")
        assert detect_template_kind(text) == "natural"
