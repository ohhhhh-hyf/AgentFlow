"""编排引擎的纯函数：线状态、报告组装、降级拼装。

``domain_engine`` 再导出这些名字，领域 orchestrator 的别名 import 不用改。
"""
from __future__ import annotations

import json
import re
from dataclasses import fields
from typing import Any



def scrape_draft(context: str, markers: str | tuple[str, ...]) -> dict[str, Any]:
    """从渲染/批准上下文里抠出草稿 JSON（首个可解析对象；拿不到返回空 dict）。

    各任务线的渲染 / 组装步骤原本各抄一份实现（2026-09-21 收拢 10 处），彼此只有 marker
    文案不同：命中第一个 marker 后取其右侧文本，再从第一个 ``{`` 起解析一个 JSON 对象；
    解析结果不是对象就按空草稿处理（与旧实现逐字等价）。
    """
    blob = str(context or "")
    for marker in ((markers,) if isinstance(markers, str) else markers):
        if marker and marker in blob:
            blob = blob.split(marker, 1)[1]
            break
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def scrape_original(context: str, markers: tuple[str, ...], stops: tuple[str, ...]) -> str:
    """从上下文里抠出原文块：命中第一个 marker 后，截到最近一个 stop 之前。

    收拢自 notes 的 review / quiz 两份逐字相同的实现（2026-09-21）。
    """
    raw = str(context or "")
    for marker in markers:
        if marker not in raw:
            continue
        body = raw.split(marker, 1)[1]
        for stop in stops:
            if stop in body:
                body = body.split(stop, 1)[0]
                break
        return body.strip()
    return ""

def line(state: dict, line_name: str) -> dict:
    """读取某条任务线的子空间（未初始化时返回/补齐 dict）。"""
    lines = state.setdefault("lines", {})
    sub = lines.get(line_name)
    if sub is None or not isinstance(sub, dict):
        sub = {}
        lines[line_name] = sub
    return sub


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
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def render_risk_items(items: list[dict]) -> str:
    """把风险条目列表按业务板块（话题）归类聚合，渲染为结构化卡片清单。

    格式规范：
    1. 板块主行：{板块序号}. **[{业务板块}]**
    2. 列表风险项：   - {风险核心隐患描述}({风险级别} · {责任主体})
    3. 卡片属性块（条件输出，缩进 5 空格接 > ）：
       - 潜在影响：{客观陈述后果或连锁反应}（必出）
       - 应对方案：{预案动作或整改措施}（条件输出）
    """
    if not items:
        return "暂无明确风险事项"

    _invalid = {"null", "none", "无", "未提及", "未明确", "待排期", "待指定", "-", "待认领", "未分配", "待定", "待确认"}
    _sev_map = {
        "high": "高风险", "medium": "中风险", "low": "低风险",
        "高": "高风险", "中": "中风险", "低": "低风险",
        "高风险": "高风险", "中风险": "中风险", "低风险": "低风险",
    }

    # 1. 话题归类聚合（保持初次出现的先后顺序）
    groups: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        risk_raw = str(item.get("risk") or "").strip()
        if not risk_raw:
            continue
        cat = str(item.get("category") or "").strip()
        if not cat and (risk_raw.startswith("【") or risk_raw.startswith("[")):
            m = re.match(r"^[【\[](.*?)[】\]](.*)$", risk_raw)
            if m:
                cat = m.group(1).strip()
        if not cat:
            cat = "综合风险"
        groups.setdefault(cat, []).append(item)

    if not groups:
        return "暂无明确风险事项"

    topic_blocks: list[str] = []
    for cat_idx, (cat, cat_items) in enumerate(groups.items(), start=1):
        topic_lines = [f"{cat_idx}. **[{cat}]**"]
        for item in cat_items:
            risk_raw = str(item.get("risk") or "").strip()
            # 剔除可能重复包含在 risk_raw 开头的 [cat] 或【cat】
            if risk_raw.startswith(f"[{cat}]"):
                risk = risk_raw[len(f"[{cat}]"):].strip()
            elif risk_raw.startswith(f"【{cat}】"):
                risk = risk_raw[len(f"【{cat}】"):].strip()
            elif (risk_raw.startswith("【") and "】" in risk_raw) or (risk_raw.startswith("[") and "]" in risk_raw):
                m = re.match(r"^[【\[](.*?)[】\]](.*)$", risk_raw)
                risk = m.group(2).strip() if m else risk_raw
            else:
                risk = risk_raw

            sev_key = str(item.get("severity") or "medium").lower().strip()
            sev = _sev_map.get(sev_key, "中风险")

            owner = str(item.get("owner") or "").strip()
            impact = str(item.get("impact") or "").strip()
            mitigation = str(item.get("mitigation") or "").strip()

            if owner and owner.lower() not in _invalid:
                meta_display = f"{sev} · {owner}"
            else:
                meta_display = f"{sev}"

            topic_lines.append(f"   - {risk}({meta_display})")

            # 潜在危害（条件输出）
            if impact and impact.lower() not in _invalid:
                topic_lines.append(f"     > 潜在危害：{impact}")
            # 应对措施（条件输出）
            if mitigation and mitigation.lower() not in _invalid:
                topic_lines.append(f"     > 应对措施：{mitigation}")

        topic_blocks.append("\n".join(topic_lines))

    return "\n\n".join(topic_blocks)


def format_risk_item(index: int, item: dict) -> str:
    """把单条风险格式化为规范文本块。"""
    res = render_risk_items([item])
    if index != 1 and res.startswith("1."):
        res = f"{index}." + res[2:]
    return res


format_risk_item.render_items = render_risk_items


def format_graph_node(index: int, item: dict) -> str:
    """把知识图谱节点格式化为文本行（确定性降级输出用）。"""
    name = str(item.get("name") or "").strip()
    definition = str(item.get("definition") or "").strip()
    if definition:
        return f"{index}. {name}（{definition[:30]}）"
    return f"{index}. {name}"


def _norm_for_dup(text: str) -> str:
    """去空白与首尾标点，用于判断"降级文本首行是否与文档标题重复"。"""
    return re.sub(r"[\s。；;：:]+", "", str(text or "")).strip()


def _join_items(values: list) -> str:
    """把若干项用「；」连成一段：先去掉每项末尾的句号/分号，避免「。；」连写。"""
    items = [str(v).strip() for v in values if str(v).strip()]
    cleaned = [re.sub(r"[。；;.\s]+$", "", item) for item in items]
    body = "；".join(x for x in cleaned if x)
    if body and not body.endswith(("。", "！", "？")):
        body += "。"
    return body


def fallback_text(
    state: dict,
    line_name: str,
    rules,
    formatters: dict[str, object],
    empty_purpose,
    disclaimer: str,
    title: str = "",
) -> tuple[str, list | None]:
    """按声明式规则把草稿拼成确定性文本（+ 可选结构化列表）。

    ``title``：文档层会另加 ``# {title}``（见 tools/exports/outputs.py），
    与降级文本首行同名时跳过该行，避免标题重复两遍（2026-09 实测降级文本
    的 headline 会与文档标题重复）。
    """
    draft = line(state, line_name).get("draft") or {}
    objective = bool(state.get("objective_perspective"))
    title_key = _norm_for_dup(title)
    sections: list[str] = []
    for sec in sec_attr(rules, "sections", []) or []:
        values = field_values(draft, sec, objective)
        kind = sec_attr(sec, "kind", "raw")
        if kind == "raw":
            if values and (title_key and _norm_for_dup(str(values)) == title_key):
                continue  # 与文档标题重复的 headline：不再重复输出
            if values:
                sections.append(str(values))
        elif kind == "join":
            body = _join_items(list(values))
            if body:
                sections.append(f"{pick_label(sec, objective)}：{body}")
        elif kind == "lines":
            formatter = formatters.get(line_name)
            if formatter is None:
                continue
            batch_fn = getattr(formatter, "render_items", None)
            if batch_fn is not None:
                batch_text = batch_fn(list(values))
                if batch_text and batch_text != sec_attr(rules, "empty_text", ""):
                    sections.append(batch_text)
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
    "scrape_original",
    "scrape_draft",
    "assemble_report",
    "fallback_text",
    "field_values",
    "format_graph_node",
    "format_risk_item",
    "render_risk_items",
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
