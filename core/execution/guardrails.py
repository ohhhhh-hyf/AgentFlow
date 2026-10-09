"""确定性事实门禁：毫秒级预检草稿中的陌生人名与历史记忆契约（零 LLM）。

定位（SUPERVISOR_AND_UNDERSTANDING_OPTIMIZATION_PLAN · 步骤五）：

- **人名在册**：草稿结构位出现的人名（``**姓名**：`` 组名行、``X工/X总/X老师``
  称谓、``姓名+动作动词``）必须落在 ``meeting_understanding.speakers`` 或原文里，
  出现未注册的陌生名字即上报；
- **数字忠实**：数字与指标忠实度交由生成端 Prompt 强约束与长文本 LLM Supervisor 深度把关，
  不再采用粗粒度正则机械比对，避免中文数词与排版序号造成高频假阳性误报；
- **对照契约**：记忆未注入（``memory_on=False``）时 ``history_comparison`` 必须为空，
  凭空产出的"历史对照"按捏造拦截。

规则全过是"免审放行"的依据（激进模式：原文 2000~5000 字区间内直接 Approve，
开关 ``SUPERVISOR_GUARDRAIL``，默认开启）；命中红线的草稿照常送 LLM 复核。

边界（刻意如此）：本模块只覆盖确定性"形"（在册名字 / 记忆契约），业务结论与深度数值分析
由生成端 Prompt 约束与 LLM 审核兜底——因此激进模式只在中等篇幅区间启用，长会（>5000
字符）始终走 LLM 审核；短会另有 <2000 字的无条件快速通道（见
``DomainNodes._make_supervisor_node``）。
"""
from __future__ import annotations

import os
import re
from typing import Any

_ENV_KEY = "SUPERVISOR_GUARDRAIL"


def guardrail_fast_path_enabled() -> bool:
    """激进放行开关：``SUPERVISOR_GUARDRAIL=off``（或 0/false/no）关闭，默认开启。"""
    value = os.getenv(_ENV_KEY, "on").strip().lower()
    return value not in ("0", "false", "off", "no")


# 历史对照由程序注入（跨场内容，本就不在本次原文里）：不参与"原文落地"校验，
# 否则"延续事项（…）：缓存保护设计"这类历史文本会被误报成幻觉。
_SKIP_KEYS = frozenset({"history_comparison"})

# ``**X**：…`` 起首的加粗行（真人模式按人分组的组名行：``**姓名**：`` 或 ``**与我相关**：``）
_GROUP_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*([^*：:\n]{1,16}?)\*\*\s*[：:]", re.M)
# 组名行里的固定标签（前缀匹配）：这些不是人名
_GROUP_LABEL_PREFIXES = (
    "与我相关", "本人", "待我", "协同输入", "关注人定调", "前置依赖", "外部依赖",
    "全局风险", "全局重大", "外部阻塞", "未决争议", "重点协同", "重点关注", "相关方",
)
# 称谓式人名：张工 / 李总 / 王老师（前后不接汉字，避免"员工""总工"这类词内命中）
_ADDRESS_RE = re.compile(
    r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{1,2}(?:工|总|老师|经理|主任|总监))(?![\u4e00-\u9fff])"
)
# 姓名 + 动作动词（2~3 字姓名紧邻动词）：起于词边界——
# 不加边界会把"本次会议确认"截成"次会议"，把结构词当人名。
_VERB_NAME_RE = re.compile(
    r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,3})"
    r"(?=(?:负责|要求|确认|提出|承诺|强调|指出|表示|跟进|牵头|汇报|反馈|同意|反对|建议|补充|明确))"
)
# 书面语主语/结构词：形态像名字但不是人（不判定，避免把"本场""会上"当陌生人名）
_SUBJECT_STOP = frozenset({
    "本场", "本次", "会上", "现场", "双方", "各方", "与会", "与会者", "团队", "部门",
    "项目组", "该项目", "对方", "甲方", "乙方", "客户", "用户", "领导", "老板",
    "大家", "各位", "同事", "同学", "专家", "嘉宾", "主持人", "记者", "听众",
    "会议", "需求", "方案", "结论", "风险", "问题", "工作", "计划", "要求",
    "目标", "结果", "后续", "相关", "有关", "当前", "目前", "本周", "下周", "下一步",
})
_MAX_FINDINGS = 12

_FULLWIDTH = str.maketrans("０１２３４５６７８９％", "0123456789%")


def _compact(text: object) -> str:
    """归一化：全角数字/百分号 → 半角，去空白与千分位逗号（两侧同口径才可比对）。"""
    return re.sub(r"[\s,，]", "", str(text or "").translate(_FULLWIDTH))


def _iter_strings(node: object, key: str = "") -> list[str]:
    if isinstance(node, dict):
        out: list[str] = []
        for k, value in node.items():
            if str(k) in _SKIP_KEYS:
                continue
            out.extend(_iter_strings(value, str(k)))
        return out
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(_iter_strings(item, key))
        return out
    if isinstance(node, str):
        return [node]
    return []


def _name_candidates(text: str) -> list[str]:
    """草稿结构位的候选人名（组名行 / 称谓 / 姓名+动词），去重保序。"""
    out: list[str] = []

    def add(name: str) -> None:
        candidate = name.strip()
        if candidate and candidate not in out:
            out.append(candidate)

    for match in _GROUP_LINE_RE.finditer(text or ""):
        label = match.group(1).strip()
        if not label or any(label.startswith(prefix) for prefix in _GROUP_LABEL_PREFIXES):
            continue
        add(label)
    for pattern in (_ADDRESS_RE, _VERB_NAME_RE):
        for match in pattern.finditer(text or ""):
            add(match.group(1))
    return out


def _name_findings(
    text: str, speakers: list[dict[str, Any]], transcript: str
) -> list[str]:
    known = {
        str(item.get("name") or "").strip()
        for item in speakers
        if isinstance(item, dict)
    }
    known.discard("")
    compact_transcript = _compact(transcript)
    findings: list[str] = []
    for name in _name_candidates(text):
        if name in _SUBJECT_STOP or name in known:
            continue
        probe = _compact(name)
        if probe and probe in compact_transcript:
            continue
        findings.append(f"陌生人名：「{name}」未在发言人清单或原文中出现")
        if len(findings) >= _MAX_FINDINGS:
            break
    return findings


def quick_facts_guardrail(
    draft: object,
    speakers: list[dict[str, Any]] | None,
    transcript: str,
    *,
    memory_on: bool = True,
) -> tuple[bool, list[str]]:
    """毫秒级确定性事实核查：陌生人名与历史记忆契约。

    返回 ``(是否全过, findings)``；``findings`` 为空表示可免审放行。
    ``history_comparison``（程序注入的跨场对照）不参与"原文落地"校验；
    但 ``memory_on=False``（本次无记忆注入）时该字段按生成契约必须为空——
    凭空产出的"历史对照"是确定性可判的捏造，直接拦下。
    本函数不抛错：任何内部异常都会向上冒泡由调用方按"未通过"处理。
    """
    text = " ".join(_iter_strings(draft))
    findings = _name_findings(text, list(speakers or []), transcript)
    if not memory_on and isinstance(draft, dict):
        comparison = draft.get("history_comparison")
        if isinstance(comparison, list) and any(str(x).strip() for x in comparison):
            findings.append("无历史记忆注入却产出历史对照（生成契约要求为空 []）")
    return (not findings), findings[:_MAX_FINDINGS]


__all__ = ["guardrail_fast_path_enabled", "quick_facts_guardrail"]
