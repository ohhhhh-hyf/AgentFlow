"""编排引擎的纯函数：线状态、报告组装、降级拼装。

``domain_engine`` 再导出这些名字，领域 orchestrator 的别名 import 不用改。
"""
from __future__ import annotations

import json
import re
from dataclasses import fields


def line(state: dict, line_name: str) -> dict:
    """读取某条任务线的子空间（未初始化时返回空 dict）。"""
    return (state.get("lines") or {}).get(line_name) or {}


def line_cn(line_name: str, cn_names: dict[str, str]) -> str:
    """线名 → 中文名（查领域注册表，未注册则回退英文线名）。"""
    return cn_names.get(line_name, line_name)


def line_draft_title(line_name: str, cn_names: dict[str, str]) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return f"{line_cn(line_name, cn_names)}草稿"


def line_template(state: dict, line_name: str) -> str:
    """取某条任务线的输出模板（未传模板时返回空串）。"""
    return (state.get("templates") or {}).get(line_name, "")


def line_has_structure(report_cls: type) -> bool:
    """该线 Report 是否输出结构化列表（存在 source="structure" 字段）。"""
    return any(
        f.metadata.get("source") == "structure"
        for f in fields(report_cls)
    )


def normalize_templates(
    template: str,
    item_template: str,
    templates: dict[str, str] | None,
    line_names: list[str],
    report_assemblers: dict,
) -> dict[str, str]:
    """按线统一收纳输出模板：``templates`` 优先，便捷参数兜底。"""
    result = dict(templates or {})
    for line_name in line_names:
        if line_name in result:
            continue
        report_cls = report_assemblers[line_name]
        if line_has_structure(report_cls):
            if item_template:
                result[line_name] = item_template
        elif template:
            result[line_name] = template
    return result


def assemble_report(
    state: dict,
    warning: str | None,
    report_cls: type,
    line_name: str,
    title_fn,
) -> object:
    """通用 Report 组装器：按字段 metadata["source"] 从 state 抽屉取值。"""
    data: dict = {}
    for f in fields(report_cls):
        src = f.metadata.get("source")
        if src is None:
            continue
        if src == "title":
            data[f.name] = title_fn(state)
        elif src == "rendered":
            data[f.name] = line(state, line_name).get("rendered")
        elif src == "structure":
            data[f.name] = line(state, line_name).get("structure")
        elif src.startswith("draft."):
            draft = line(state, line_name).get("draft") or {}
            data[f.name] = draft.get(src[len("draft."):])
    names = {f.name for f in fields(report_cls)}
    if "quality_warning" in names:
        line_warn = line(state, line_name).get("quality_warning")
        data["quality_warning"] = line_warn or warning
    return report_cls(**data)


_SENTENCE_END = set("。！？；;!?：:")


def _keep_linebreak(prev: str, nxt: str) -> bool:
    """短行、已收句、下一行像条目时保留换行；只合并段落里的硬折行。"""
    prev = prev.rstrip()
    nxt = nxt.lstrip()
    if not prev or not nxt:
        return True
    if prev[-1] in _SENTENCE_END:
        return True
    if len(prev) <= 16:
        return True
    if nxt[:1] in {"#", "-", "*", "•", "（", "("}:
        return True
    return False


def normalize_transcript(text: str) -> str:
    """规范化输入文本：合并段落内硬换行，保留段落空行和条目换行。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    blocks = re.split(r"\n{2,}", text)
    out: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        buf = lines[0] if lines else ""
        kept: list[str] = []
        for nxt in lines[1:]:
            if _keep_linebreak(buf, nxt):
                kept.append(buf)
                buf = nxt
            else:
                buf = f"{buf}{nxt}"
        kept.append(buf)
        out.append("\n".join(item for item in kept if item != "" or len(kept) == 1))
    return "\n\n".join(out)


def json_dumps(value: object) -> str:
    """将模型或字典序列化为 JSON 字符串。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


def sec_attr(sec, name, default=None):
    """取段/规则属性：兼容 FallbackRules 对象与裸 dict。"""
    if isinstance(sec, dict):
        return sec.get(name, default)
    return getattr(sec, name, default)


def pick_label(sec, objective: bool) -> str:
    """段标签：支持视角联动（{objective: ..., personal: ...}）。"""
    label = sec_attr(sec, "label")
    if isinstance(label, dict):
        return label.get("objective" if objective else "personal", "未命名")
    return label or "未命名"


def field_values(draft: dict, sec, objective: bool) -> list:
    """取段字段值：支持 merge（客观视角合并多个字段）。"""
    merge = sec_attr(sec, "merge")
    field = sec_attr(sec, "field")
    if merge:
        values = list(draft.get(merge[0]) or [])
        if objective:
            for extra in merge[1:]:
                values.extend(draft.get(extra) or [])
        return values
    return draft.get(field) or []


def format_risk_item(index: int, item: dict) -> str:
    """把一条风险格式化为文本行（确定性降级输出用，与 LLM 渲染格式一致）。"""
    _sev = {"high": "高", "medium": "中", "low": "低"}
    meta = []
    sev = item.get("severity", "")
    if sev in _sev:
        meta.append(_sev[sev])
    if item.get("source"):
        meta.append(f"来源：{item['source']}")
    if item.get("impact"):
        meta.append(f"影响：{item['impact']}")
    if item.get("owner"):
        meta.append(f"负责人：{item['owner']}")
    if item.get("mitigation"):
        meta.append(f"应对：{item['mitigation']}")
    text = item.get("risk") or ""
    suffix = f"（{'；'.join(meta)}）" if meta else ""
    return f"{index}. {text}{suffix}"


def format_graph_node(index: int, item: dict) -> str:
    """把知识图谱节点格式化为文本行（确定性降级输出用）。"""
    name = str(item.get("name") or "").strip()
    definition = str(item.get("definition") or "").strip()
    if definition:
        return f"{index}. {name}（{definition[:30]}）"
    return f"{index}. {name}"


def fallback_text(
    state: dict,
    line_name: str,
    rules,
    formatters: dict[str, object],
    empty_purpose,
    disclaimer: str,
) -> tuple[str, list | None]:
    """按声明式规则把草稿拼成确定性文本（+ 可选结构化列表）。"""
    draft = line(state, line_name).get("draft") or {}
    objective = bool(state.get("objective_perspective"))
    sections: list[str] = []
    for sec in sec_attr(rules, "sections", []) or []:
        values = field_values(draft, sec, objective)
        kind = sec_attr(sec, "kind", "raw")
        if kind == "raw":
            if values:
                sections.append(str(values))
        elif kind == "join":
            body = "；".join(str(v) for v in values if v)
            if body:
                sections.append(f"{pick_label(sec, objective)}：{body}")
        elif kind == "lines":
            formatter = formatters.get(line_name)
            if formatter is None:
                continue
            for index, item in enumerate(values, start=1):
                sections.append(formatter(index, item))
    if not sections:
        text = sec_attr(rules, "empty_text", "") or ""
        prefix = sec_attr(rules, "empty_prefix", "") or ""
        if prefix:
            purpose = empty_purpose(state)
            if purpose and sec_attr(rules, "empty_purpose", False):
                text = f"{prefix}{purpose}"
            else:
                text = f"{prefix}{text}"
        text = text or "（暂无内容）"
    else:
        text = "\n".join(sections)
    if sec_attr(rules, "disclaimer", False) and text and disclaimer not in text:
        text = f"{text}\n\n{disclaimer}"
    structure = None
    structured = sec_attr(rules, "structured")
    if structured:
        field = structured.get("field")
        merge = structured.get("merge") or []
        if field:
            structure = list(draft.get(field) or [])
        elif merge:
            structure = list(draft.get(merge[0]) or [])
            if objective:
                for extra in merge[1:]:
                    structure.extend(draft.get(extra) or [])
    return text, structure


def make_fallback_text(formatters, empty_purpose, disclaimer):
    """绑定领域 formatters / empty_purpose / disclaimer，返回 3 参版本。"""

    def _bound(state: dict, line_name: str, rules):
        return fallback_text(
            state, line_name, rules, formatters, empty_purpose, disclaimer
        )

    return _bound


__all__ = [
    "assemble_report",
    "fallback_text",
    "field_values",
    "format_graph_node",
    "format_risk_item",
    "json_dumps",
    "line",
    "line_cn",
    "line_draft_title",
    "line_has_structure",
    "line_template",
    "make_fallback_text",
    "normalize_templates",
    "normalize_transcript",
    "pick_label",
    "sec_attr",
]
