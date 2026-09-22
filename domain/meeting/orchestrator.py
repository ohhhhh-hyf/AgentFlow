"""LangGraph 工作流编排。

MeetingAgentSystem 负责：组装 Agent 依赖、构建多线并行 DAG、条件路由、启动运行。

架构（注册表驱动）：
- meeting_core：会议理解 + 视角建模（公共事实底座，先行并行执行）
- tasks/{线}：各任务线（生成 → 监督 → 返工闭环），互不阻塞
- 共享编排内核位于 ``tools/core/domain_engine.py``；渲染在 ``tools.runtime.render``。
  本文件只保留：sync_domain 管理的注册/挂载生成区、领域专属 core 节点、
  领域钩子覆写。render / fallback 由运行时一份函数生成，不再按线出样板。
"""
from __future__ import annotations

import logging

from langgraph.graph import START

from tools.llm import LLMClient
from perspective import (
    PREFERENCE_LINES,
    PERSONAL_TEMPLATE_VIEW_DIRECTIVE,
    PERSONAL_VIEW_DIRECTIVE,
    PerspectiveModelingAgent,
    address_aliases,
    build_preference_block,
    foreign_only,
    slice_transcript_for_person,
)
from .meeting_factory import MeetingAgentFactory
from .meeting_core import MeetingUnderstandingAgent
from .domain_config import LINE_CN_NAMES, LINE_KINDS
from .scene_hint import scene_hint_for_templates
from .understanding_skip import skip_fields_for_template

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.core.domain_engine import DomainNodes
from tools.core.domain_engine_text import (
    format_risk_item,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
)
from tools.runtime.kinds import resolve_line_policies
from tools.runtime.progress import progress
from tools.runtime.supervisor_slice import compact_draft_for_review

# ── Report import 生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

from .reports import (
    ActionItemsReport,
    ConsensusDecisionReport,
    MindmapReport,
    MinutesReport,
    MultiStylesReport,
    MinutesTraceReport,
    RiskReport,
)
# ── Report import 生成区结束 ──

from .models import MeetingState
# ── 任务线 import 生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

from .tasks.actions import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
)

from .tasks.consensus_decision import (
    ConsensusDecisionAgent,
    ConsensusDecisionRender,
    ConsensusDecisionSupervisor,
)

from .tasks.mindmap import (
    MindmapAgent,
    MindmapRender,
    MindmapSupervisor,
)

from .tasks.minutes import (
    MinutesGenerationAgent,
    MinutesGenerationRender,
    MinutesGenerationSupervisor,
)

from .tasks.minutes_styles import (
    MultiStylesAgent,
    MultiStylesRender,
    MultiStylesSupervisor,
)

from .tasks.minutes_trace import (
    MinutesTraceAgent,
    MinutesTraceRender,
    MinutesTraceSupervisor,
)

from .tasks.risks import (
    RiskAgent,
    RiskRender,
    RiskSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

from .tasks.actions.contracts import ACTION_ITEMS_FALLBACK_RULES
from .tasks.consensus_decision.contracts import CONSENSUS_DECISION_FALLBACK_RULES
from .tasks.mindmap.contracts import MINDMAP_FALLBACK_RULES
from .tasks.minutes.contracts import MINUTES_FALLBACK_RULES
from .tasks.minutes_styles.contracts import MULTI_STYLES_FALLBACK_RULES
from .tasks.minutes_trace.contracts import MINUTES_TRACE_FALLBACK_RULES
from .tasks.risks.contracts import RISK_FALLBACK_RULES

# ── FallbackRules import 生成区结束 ──

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"

# ── 空结构常量生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

_EMPTY_ACTION_ITEMS = {
    "my_actions": [],
    "delegated_actions": [],
    "unassigned_actions": [],
}

_EMPTY_CONSENSUS_DECISION = {
    "summary": {},
    "issues": [],
}

_EMPTY_MEETING_UNDERSTANDING = {
    "meeting_brief": "",
    "meeting_purpose": "",
    "scene": "通用",
    "speakers": [],
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
    "action_hints": [],
    "risk_hints": [],
    "dependencies": [],
}

_EMPTY_MINDMAP = {
    "title": "",
    "outline": "",
}

_EMPTY_MINUTES = {
    "headline": "",
    "executive_summary": [],
    "key_decisions": [],
    "personally_relevant_points": [],
    "risks_and_blockers": [],
    "unresolved_questions": [],
    "history_comparison": [],
}

_EMPTY_MINUTES_TRACE = {
    "scene": "通用",
    "minutes_md": "",
    "alignments": [],
}

_EMPTY_MULTI_STYLES = {
    "mode": "time",
    "title": "",
    "sections": [],
    "summary": "",
}

_EMPTY_RISK = {
    "risks": [],
}

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

_REJECT_MINUTES_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "perspective_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "consistency_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_ACTION_ITEMS_REVIEW = {
    "decision": "reject",
    "actions_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_RISK_REVIEW = {
    "decision": "reject",
    "risk_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MINDMAP_REVIEW = {
    "decision": "reject",
    "mindmap_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MULTI_STYLES_REVIEW = {
    "decision": "reject",
    "mode_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "consistency_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MINUTES_TRACE_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "template_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "trace_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_CONSENSUS_DECISION_REVIEW = {
    "decision": "reject",
    "concession_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "tradeoff_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "evidence_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}


# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "actions": {
        "agent_attr": "actions_agent",
        "supervisor_attr": "actions_supervisor",
        "empty_draft": _EMPTY_ACTION_ITEMS,
        "reject_review": _REJECT_ACTION_ITEMS_REVIEW,
    },
    "consensus_decision": {
        "agent_attr": "consensus_decision_agent",
        "supervisor_attr": "consensus_decision_supervisor",
        "empty_draft": _EMPTY_CONSENSUS_DECISION,
        "reject_review": _REJECT_CONSENSUS_DECISION_REVIEW,
    },
    "mindmap": {
        "agent_attr": "mindmap_agent",
        "supervisor_attr": "mindmap_supervisor",
        "empty_draft": _EMPTY_MINDMAP,
        "reject_review": _REJECT_MINDMAP_REVIEW,
    },
    "minutes": {
        "agent_attr": "minutes_agent",
        "supervisor_attr": "minutes_supervisor",
        "empty_draft": _EMPTY_MINUTES,
        "reject_review": _REJECT_MINUTES_REVIEW,
    },
    "minutes_styles": {
        "agent_attr": "minutes_styles_agent",
        "supervisor_attr": "minutes_styles_supervisor",
        "empty_draft": _EMPTY_MULTI_STYLES,
        "reject_review": _REJECT_MULTI_STYLES_REVIEW,
    },
    "minutes_trace": {
        "agent_attr": "minutes_trace_agent",
        "supervisor_attr": "minutes_trace_supervisor",
        "empty_draft": _EMPTY_MINUTES_TRACE,
        "reject_review": _REJECT_MINUTES_TRACE_REVIEW,
    },
    "risks": {
        "agent_attr": "risks_agent",
        "supervisor_attr": "risks_supervisor",
        "empty_draft": _EMPTY_RISK,
        "reject_review": _REJECT_RISK_REVIEW,
    },
}

# ── 任务线注册生成区结束 ──

def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return _engine_line_cn(line_name, LINE_CN_NAMES)

def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return _engine_line_draft_title(line_name, LINE_CN_NAMES)

def _format_minutes_styles_section(index: int, item: dict) -> str:
    """把多样式纪要的一个组织段落格式化为文本行（确定性降级输出用）。"""
    title = str(item.get("title") or "").strip()
    content = str(item.get("content") or "").strip()
    if title:
        return f"{title}：{content}" if content else title
    return content

def _format_consensus_decision_issue(index: int, item: dict) -> str:
    """把共识决策议题格式化为结构化文本（确定性降级输出用）。"""
    topic = str(item.get("topic") or "").strip()
    grade = str(item.get("consensus_grade") or "").strip()
    accord = item.get("accord")
    if isinstance(accord, dict):
        resolution = str(accord.get("core_resolution") or "").strip()
    else:
        resolution = str(accord or "").strip()
    tradeoff = item.get("trade_off") or {}
    gain = str(tradeoff.get("gain") or "").strip()
    sacrifice = str(tradeoff.get("sacrifice") or "").strip()
    caveat = str(item.get("caveat") or "").strip()

    lines = [f"{index}. 【议题】{topic}（成色定级：{grade}）"]
    if resolution:
        lines.append(f"   - 决议公约：{resolution}")
    if gain or sacrifice:
        lines.append(f"   - 得失天平：收益【{gain}】/ 代价【{sacrifice}】")
    if caveat and caveat.lower() not in ("none", "null", "无", "无保留条件", "无附加保留条件"):
        lines.append(f"   - 保留条件：{caveat}")
    return "\n".join(lines)

# Lines 段逐条格式化器注册表（线名 → 格式化函数(index, item) -> str）
# actions / risks / minutes_styles 的降级输出格式与各自 LLM 渲染 prompt 保持一致
_LINES_FORMATTERS: dict[str, object] = {
    "actions": ActionItemsRender.format_action,
    "risks": format_risk_item,
    "minutes_styles": _format_minutes_styles_section,
    "consensus_decision": _format_consensus_decision_issue,
}

# 理解层按线裁剪：单线运行时跳过的字段（输出 []，字段契约与下游读取不变）。
# 多线并行共享理解时保持全量，裁剪只在单线场景生效（避免一条线白付其它线字段）。
UNDERSTANDING_SKIP_FIELDS: dict[str, frozenset[str]] = {
    "actions": frozenset({"topics", "risks", "open_questions", "risk_hints"}),
    "risks": frozenset({"topics", "action_hints"}),
    # minutes 线只消费 pack 里的 brief/purpose/scene/topics/decisions/risks/open_questions：
    # action_hints / risk_hints / dependencies（待办线与风险线的线索）它从不使用；
    # risks / open_questions 是否再跳由模板栏位决定——模板没有风险/未决栏就没有落点，
    # 见 understanding_skip.py（发布会/课堂/讲座/访谈类都不带这两栏）。
    "minutes": frozenset({"risk_hints", "action_hints", "dependencies"}),
}

def _empty_purpose(state) -> str:
    """empty_purpose 兜底时的「目的」文案（会议理解的目的）。"""
    purpose = (state.get("meeting_understanding") or {}).get(
        "meeting_purpose"
    ) or ""
    return f"会议目的：{purpose}" if purpose else ""

def _attribute_person_items(state: dict, items: list[str]) -> list[str]:
    """真人模式：按原文给结论/风险/未决条目补出归属（「姓名：」前缀），对不上的原样返回。

    为什么在程序里做（2026-09-22 实测三轮）：契约要求"按人分组"，但上游 decisions /
    risks 都是纯文本、没有归属，模型又受"措辞用上游原文"约束——三次真链路都没分组。
    这里用原文的发言行结构定位"这条是谁提出/谁在跟"，把归属变成**可照抄的事实**，
    草稿只做分组、不再做推理。只在能对上时才补（看不出归属的不补），零 LLM 调用；
    客观/职业模板原样返回。

    **模块级函数而非方法**：既有测试以 ``_Nodes._meeting_pack(object(), state, line)``
    的形式调用（用 ``object()`` 当 self），方法一旦用到 self 就会 AttributeError。
    """

    if DomainNodes._mode_label(state) != "personal" or not items:
        return list(items)
    from perspective import address_aliases, attribute_to_speaker

    user = state.get("user") or {}
    name = str(user.get("name") or "").strip()
    addresses = [item for item in (name, *address_aliases(user)) if item]
    found = attribute_to_speaker(
        state.get("transcript") or "",
        list(items),
        self_addresses=addresses,
        self_name=name,
    )
    return [
        f"{found[item.strip()]}：{item}" if found.get(str(item).strip()) else item
        for item in items
    ]


class _Nodes(DomainNodes):
    """meeting 图节点实现：共享内核 + 领域专属钩子与会议理解节点。"""

    _fallback_formatters = _LINES_FORMATTERS
    # 正文不带免责声明：质量信号走 API 的 quality_warning 字段 + 日志（见 runner 的 ⚠）
    _quality_disclaimer = ""
    _understanding_key = "meeting_understanding"
    _understanding_label = "已审核会议理解"
    _transcript_label = "会议原文"
    _line_cn_names = LINE_CN_NAMES
    _line_policies = resolve_line_policies(LINE_KINDS)

    # 理解层参与审核摘录的字段白名单（线名 → 保留字段）。
    # 该线不消费的字段不进原文摘录，命中点从遍布全文收敛到相关段落；
    # 未列出的线（minutes_styles / mindmap 等）走默认全字段。
    _understanding_needle_keep: dict[str, frozenset[str]] = {
        "actions": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "decisions",
            "action_hints", "dependencies",
        }),
        "risks": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "risks",
            "open_questions", "risk_hints", "dependencies",
        }),
        "minutes": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "speakers",
            "topics", "decisions", "risks", "open_questions", "dependencies",
        }),
        "minutes_trace": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "speakers",
            "topics", "decisions", "risks", "open_questions", "dependencies",
        }),
    }

    def _understanding_needle_fields(self, line_name: str) -> set[str] | None:
        """审核摘录时理解层的 needle 字段白名单（与按线裁剪同源）。"""
        keep = self._understanding_needle_keep.get(line_name)
        return set(keep) if keep else None

    # ── 领域钩子：视角标题 / 展示标题 ─────────────────────────

    def _compute_title(self, state) -> str:
        """标题：优先用纪要草稿的 headline（根据会议内容总结的主题标题），回退视角标题。"""
        try:
            draft = _line(state, "minutes").get("draft") or {}
            headline = str(draft.get("headline") or "").strip()
            if headline:
                return headline
        except Exception:  # noqa: BLE001 - 取 headline 失败回退视角标题
            pass
        if bool(state.get("objective_perspective")):
            return "客观会议纪要"
        user = state.get("user") or {}
        return f"{user.get('name', '用户')}视角会议纪要"

    def _line_title(self, state, line_name: str) -> str:
        """线 → 展示标题（按视角模式区分；新线用通用默认）。"""
        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = user.get("name") or "用户"
        if line_name == "minutes":
            return "客观会议纪要" if objective else f"{name}视角会议纪要"
        if line_name == "actions":
            return "客观待办事项（全员）" if objective else "待办事项"
        return f"{_line_cn(line_name)}输出"

    def _empty_purpose(self, state) -> str:
        return _empty_purpose(state)

    @staticmethod
    def _compact_user(user: dict) -> dict:
        """给任务 Agent 的瘦身画像，只保留会影响视角裁剪的字段。"""
        keys = (
            "name",
            "role",
            "department",
            "perspective",
            "persona_type",
            "responsibilities",
            "interests",
            "focus_areas",
            "constraints",
            "output_style",
        )
        return {key: user.get(key) for key in keys if user.get(key)}

    @staticmethod
    def _compact_perspective(profile: dict | None) -> dict:
        """视角模型瘦身：保留与任务相关性判断有关的字段。"""
        if not isinstance(profile, dict):
            return {}
        keys = (
            "personal_summary",
            "attention_points",
            "responsibilities",
            "goals",
            "concerns",
            "relevant_topics",
            "evidence",
        )
        return {key: profile.get(key) for key in keys if profile.get(key)}

    @staticmethod
    def _topic_brief(topic: dict) -> dict:
        title = str(topic.get("title") or "").strip()
        conclusion = topic.get("conclusion")
        discussion = str(topic.get("discussion") or "").strip()
        # 契约已含 key_points；模型漏填时回退用 discussion 兜底。
        key_points = topic.get("key_points")
        if not isinstance(key_points, list):
            key_points = []
        if discussion and not key_points:
            key_points = [discussion[:2000]]
        return {
            "title": title,
            "key_points": key_points[:12],
            "conclusion": conclusion,
            "participants": topic.get("participants") or [],
        }

    def _meeting_pack(self, state: dict, line_name: str) -> dict:
        """为每条任务线构造最小必要会议理解包，减少重复上下文。"""
        u = state.get("meeting_understanding") or {}
        topics = [
            self._topic_brief(item)
            for item in (u.get("topics") or [])
            if isinstance(item, dict)
        ]
        base = {
            "meeting_brief": u.get("meeting_brief") or u.get("meeting_purpose") or "",
            "meeting_purpose": u.get("meeting_purpose") or "",
            "scene": u.get("scene") or "通用",
            # 姓名↔角色对照：所有线都带上（体积小、收益大）——渲染时第一眼能绑人，
            # 不必每栏从长原文重推（实测会退化成「答」「主持人（机构名）」）
            "speakers": u.get("speakers") or [],
        }
        if line_name == "actions":
            directive_decisions = [
                item for item in (u.get("decisions") or [])
                if any(word in str(item) for word in ("要求", "必须", "务必", "请", "需", "整改", "落实"))
            ]
            return {
                **base,
                "action_hints": u.get("action_hints") or [],
                "directive_decisions": directive_decisions,
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "risks":
            return {
                **base,
                "risk_hints": u.get("risk_hints") or [],
                "risks": u.get("risks") or [],
                "dependencies": u.get("dependencies") or [],
                "risk_related_open_questions": u.get("open_questions") or [],
            }
        if line_name == "minutes_trace":
            return {
                **base,
                "topics": topics,
                "decisions": u.get("decisions") or [],
                "risks": u.get("risks") or [],
                "open_questions": u.get("open_questions") or [],
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "minutes_styles":
            # 多样式纪要重写全文(上下文另有完整原文),pack 只给理解摘要;
            # 不需要 action_hints/risk_hints(那是待办/风险线的线索)
            return {
                **base,
                "topics": topics,
                "decisions": u.get("decisions") or [],
                "risks": u.get("risks") or [],
                "open_questions": u.get("open_questions") or [],
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "minutes":
            full_topics = []
            for item in (u.get("topics") or []):
                if not isinstance(item, dict):
                    continue
                discussion = str(item.get("discussion") or "").strip()
                key_points = item.get("key_points")
                if not isinstance(key_points, list):
                    key_points = [discussion] if discussion else []
                full_topics.append({
                    "title": str(item.get("title") or "").strip(),
                    "key_points": [str(p).strip() for p in key_points if str(p).strip()][:12],
                    "discussion": discussion,
                    "conclusion": item.get("conclusion"),
                    "participants": item.get("participants") or [],
                })
            return {
                **base,
                "topics": full_topics or topics,
                "decisions": _attribute_person_items(state, u.get("decisions") or []),
                "risks": _attribute_person_items(state, u.get("risks") or []),
                "open_questions": _attribute_person_items(state, u.get("open_questions") or []),
            }
        return {
            **base,
            "topics": topics,
            "decisions": u.get("decisions") or [],
            "risks": u.get("risks") or [],
            "open_questions": u.get("open_questions") or [],
            "action_hints": u.get("action_hints") or [],
            "risk_hints": u.get("risk_hints") or [],
            "dependencies": u.get("dependencies") or [],
        }

    def _line_shared_context(self, state: dict, line_name: str) -> str:
        """按任务线裁剪后的 Agent 上下文。

        仍保留「会议理解」标签，兼容 minutes 的硬执行对齐。
        """
        pack = self._meeting_pack(state, line_name)
        if line_name == "minutes_trace":
            # minutes_trace 是客观溯源线：编排层已跳过视角建模，生成 prompt 也不消费
            # 视角/画像——上下文只发会议理解 + 原文（省输入 token，去掉误导性裁剪说明）。
            parts = [f"会议理解：\n{_json(pack)}"]
            parts.append(f"会议原文：\n{state.get('transcript') or ''}")
            return "\n\n".join(parts)
        mode = self._mode_label(state)
        if line_name == "minutes":
            fact_note = (
                "说明：会议理解是议题/决策/风险索引；写摘要与分工时必须对照会议原文"
                "把细节展开成自然段。不得编造原文没有的事实，也不得只把索引短句原样输出交差。"
                "裁剪视角时参考用户画像和用户视角模型。"
            )
        else:
            fact_note = (
                "说明：仅使用本任务上下文包中的事实；需要裁剪视角时参考用户画像和用户视角模型。"
                "不要从未提供的完整原文中补造事实。"
            )
        parts = [
            f"视角模式：{mode}",
            fact_note,
            f"用户画像：\n{_json(self._compact_user(state.get('user') or {}))}",
        ]
        # 偏好直接编成指令进纪要线（不走视角建模）：只调顺序与详略，事实口径不变。
        # 客观视角返回空串（object.json 本来也没有个人偏好）。
        if line_name in PREFERENCE_LINES:
            preference_block = build_preference_block(state.get("user") or {})
            if preference_block:
                parts.append(preference_block)
            # 命中表（程序判定，非模型推断）：他是谁、哪些待办是他的、依据在哪。
            # 跳过视角建模时它是唯一的"按人裁剪"依据；跑建模时也用它复核。
            hit_block = str(state.get("user_hits_block") or "").strip()
            if hit_block:
                parts.append(hit_block)
            groups_block = str(state.get("user_action_groups_block") or "").strip()
            if groups_block:
                parts.append(groups_block)
        parts.append(f"会议理解：\n{_json(pack)}")
        perspective = self._compact_perspective(state.get("perspective_profile") or {})
        if perspective:
            parts.append(f"用户视角模型：\n{_json(perspective)}")
        # 纪要成段需要原文细节；溯源/多样式/导图/共识决策同样需要原文。其它线优先依赖 evidence。
        if line_name in {"minutes", "minutes_trace", "minutes_styles", "mindmap", "consensus_decision"}:
            parts.append(f"会议原文：\n{state.get('transcript') or ''}")
        if line_name in {"minutes", "minutes_styles"}:
            budget = self._length_budget_line(state, line_name)
            if budget:
                parts.append(budget)
        return "\n\n".join(parts)

    def _supervisor_context(self, state, line_name: str) -> str:
        """审核上下文：原文按草稿事实点摘录，理解只给摘要。

        生成侧注入的【会议记忆】要一并给审核者：否则「对照缺失/误标」「记忆摘录被写成
        新决策」无从判定，历史对照段还会因缺锚点被判成捏造。
        同理，**命中表也要给审核者**（P2-F）：没有它，"owner 是不是这个人""职业名当成
        负责人""他名下的条被漏掉"这三类判断都只能靠猜。
        """
        sub = _line(state, line_name)
        mode = self._mode_label(state)
        blocks = [self._supervisor_source_pack(state, line_name)]
        memory = str(sub.get("memory_context") or "").strip()
        if memory:
            blocks.append(memory)
        # 命中表（程序判定，带依据）：真人/职业模板下是"谁的事"的唯一硬依据
        hits = str(state.get("user_hits_block") or "").strip()
        if hits and mode != "objective":
            blocks.append(hits)
        groups = str(state.get("user_action_groups_block") or "").strip()
        if groups and mode != "objective":
            blocks.append(groups)
        budget = self._length_budget_line(state, line_name)
        if budget:
            blocks.append(budget)
        blocks.append(
            f"{_line_draft_title(line_name)}：\n"
            f"{_json(compact_draft_for_review(sub['draft']))}"
        )
        return f"{self._revision_instruction(state, line_name)}\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _length_budget_line(state: dict, line_name: str) -> str:
        """篇幅预算块：按原文规模算好具体数字，注入生成/渲染上下文（纪要正文/多样式）。

        旧口径「篇幅以原文为参照（同量级）」对纪要既不成立（纪要必然短于原文）也无法自算，
        实测输出/输入比在 4.3%–35% 之间游走；这里把"该写多长"变成可执行的区间。
        """
        from tools.templates.length_budget import budget_line, han_count

        transcript = str(state.get("transcript") or "")
        columns = 0
        template = (state.get("templates") or {}).get(line_name) or ""
        if template:
            try:
                from tools.templates.router import plan_placeholder_fill

                columns = len(plan_placeholder_fill(template).get("scalars") or [])
            except Exception:  # noqa: BLE001 - 预算只是软提示，算不出栏数就不带
                columns = 0
        return budget_line(han_count(transcript), columns=columns)

    def _render_context(self, state: dict, line_name: str) -> str:
        """会议域渲染上下文。纪要/溯源/多样式/导图带会议原文以便成段写开；其它线不带全文。"""
        from tools.runtime.context import build_render_context

        sub = _line(state, line_name)
        extra = (state.get("line_extra") or {}).get(line_name) or ""
        pack = self._meeting_pack(state, line_name)
        if line_name in PREFERENCE_LINES:
            pack = self._person_pack(pack, state)
        blocks: list[tuple[str, object, str]] = [
            ("用户画像", self._compact_user(state.get("user") or {}), "json"),
            ("会议理解", pack, "json"),
        ]
        perspective = self._compact_perspective(state.get("perspective_profile") or {})
        if perspective:
            blocks.append(("已审核用户视角", perspective, "json"))
        if line_name in {"minutes", "minutes_trace", "minutes_styles", "mindmap", "consensus_decision"}:
            label, transcript = "会议原文", state.get("transcript") or ""
            sliced = self._person_transcript(state) if line_name in PREFERENCE_LINES else ""
            if sliced:
                label = "会议原文（真人模式·已按人裁剪）"
                transcript = sliced
            blocks.insert(0, (label, transcript, "raw"))
        budget = self._length_budget_line(state, line_name)
        if budget:
            blocks.append(("篇幅预算", budget, "raw"))
        # 命中块 / 偏好块也要进"逐栏填充"这一轮——装配才是真正写正文的地方，
        # 它看不到"他是谁、他关心什么"就会把个人视角摊回整场（实测观感：与客观没区别）。
        # 命中块对所有非客观线有用（谁的事）；偏好块只进纪要线（它讲的是"怎么写纪要"）。
        extra_parts = [extra] if str(extra or "").strip() else []
        if not bool(state.get("objective_perspective")):
            hits = str(state.get("user_hits_block") or "").strip()
            if hits:
                extra_parts.append(hits)
            groups = str(state.get("user_action_groups_block") or "").strip()
            if groups:
                extra_parts.append(groups)
            if line_name in PREFERENCE_LINES:
                preference = build_preference_block(state.get("user") or {})
                if preference:
                    extra_parts.append(preference)
        extra = "\n\n".join(extra_parts)
        return build_render_context(
            mode=self._mode_label(state),
            objective=bool(state.get("objective_perspective")),
            blocks=blocks,
            draft=sub.get("draft"),
            review=sub.get("review") or {},
            line_cn=_line_cn(line_name),
            extra=extra,
            dumps=_json,
        )

    def _person_transcript(self, state: dict) -> str:
        """真人模式给渲染用的原文切片：只留他发言/被点名的段（返回空串＝不裁剪）。

        为什么非裁不可：模板路径的正文由通用填充器逐栏写，【内容来源】里躺着整场原文、
        模板栏名又是「全文摘要 / 分段速览」——写作纪律写在消息开头也压不过眼前的两万字，
        实测两轮仍输出整场（提及他的段落只占 12%）。裁掉别人的发言，栏位就没得抄；
        全局结论/数字由已批准草稿与会议理解承载，不会因此丢掉。

        裁完太少（或原文没有稳定的「称呼 + 时间」结构）一律退回整篇：宁可不聚焦，不可没料。
        """
        if self._mode_label(state) != "personal":
            return ""
        user = state.get("user") or {}
        name = str(user.get("name") or "").strip()
        addresses = [name, *address_aliases(user)]
        text, stats = slice_transcript_for_person(
            state.get("transcript") or "",
            [a for a in addresses if a],
            full_name=name,
            self_label="你",
        )
        if stats.get("fallback"):
            logger.info("personal transcript slice skipped: %s", stats)
            return ""
        logger.info(
            "personal transcript slice kept=%s dropped=%s chars=%s->%s",
            stats.get("kept"),
            stats.get("dropped"),
            stats.get("chars"),
            len(text),
        )
        return text

    def _render_directives(self, state: dict, line_name: str) -> str:
        """装配那一轮的「本栏写作纪律」：真人模式按本人聚焦，客观/职业模板不注入。

        为什么必须从这里下发：带模板时正文由 ``tools.templates.router`` 通用填充器逐栏写，
        system 里只有「你只写本栏正文」——``MINUTES_RENDER_PROMPT`` 那条路不执行。不下发
        取舍纪律，模型就只剩模板栏名（全文摘要 / 分段速览）可依，个人模式照样写成整场纪要
        （实测 8172 字、超本篇参考上限 48%，与客观版看不出区别）。

        职业模板不发：那份画像没有真人姓名，「你」无从指代，关注域已由【用户视角模型】块承担。
        """
        if self._mode_label(state) != "personal" or line_name not in PREFERENCE_LINES:
            return ""
        template = str((state.get("templates") or {}).get(line_name) or "")
        if any(marker in template for marker in ("本场概况与本人定调", "重点关注与业务进展", "行动项与协同依赖", "待确认事项与风险卡点")):
            return PERSONAL_TEMPLATE_VIEW_DIRECTIVE
        return PERSONAL_VIEW_DIRECTIVE

    def _person_pack(self, pack: dict, state: dict) -> dict:
        """真人纪要线的素材裁剪：理解包里的"别人为主语"条目去掉（客观/职业模板不动）。

        为什么必须程序裁（2026-09-21 实测定位）：装配轮没有审核，模板「行动项与分工」栏位会
        把会议理解里的 topics[].key_points 直接变成条目——「武思华明天找他们要数据」就是这样
        进正文的（157 条里 49 条以别人为主语），写作纪律压不住素材。裁的只是"别人为主语、
        且没提到他"的条目：他的条目留、无人称的全局事实（数字/结论）留，decisions/risks 不动。

        2026-09-22 追加：**topics[].discussion（议题讨论经过）走同一套判定**。它按契约写的就是
        "谁提出、怎么讨论"，是别人为主语的高发区，此前只裁 key_points ⇒ 这条通道整段漏网。
        命中即置空串（键保留），键不存在时不新增（minutes_styles 的 topic 没有该字段）。
        """
        if self._mode_label(state) != "personal":
            return pack
        user = state.get("user") or {}
        name = str(user.get("name") or "").strip()
        addresses = [item for item in (name, *address_aliases(user)) if item]
        speakers = [
            str(item.get("name") or "")
            for item in ((state.get("meeting_understanding") or {}).get("speakers") or [])
            if isinstance(item, dict)
        ]
        others = [who for who in speakers if who and who not in addresses]
        topics = pack.get("topics")
        if not addresses or not others or not topics:
            return pack
        kept: list[dict] = []
        dropped = 0
        dropped_discussions = 0
        for topic in topics:
            points = topic.get("key_points") or []
            keep_points = [
                point for point in points
                if not foreign_only(point, addresses, others, full_name=name)
            ]
            dropped += len(points) - len(keep_points)
            entry = {**topic, "key_points": keep_points}
            if "discussion" in topic:  # 讨论经过：同一套判定，命中置空（键保留、形状不变）
                discussion = str(topic.get("discussion") or "")
                if discussion.strip() and foreign_only(
                    discussion, addresses, others, full_name=name
                ):
                    entry["discussion"] = ""
                    dropped_discussions += 1
            kept.append(entry)
        if dropped:
            logger.info(
                "personal pack trim: 去掉别人为主的条目 %d/%d",
                dropped,
                sum(len(topic.get("key_points") or []) for topic in topics),
            )
        if dropped_discussions:
            logger.info(
                "personal pack trim: 去掉别人为主的议题讨论经过 %d/%d",
                dropped_discussions,
                sum(
                    1
                    for topic in topics
                    if str(topic.get("discussion") or "").strip()
                ),
            )
        return {**pack, "topics": kept}

    def _make_fallback_node(self, line_name: str):
        """生成任务线降级节点：共识决策若已产出 issues 草稿，按确定性 Markdown 模板排版，严禁回退为空白占位符。"""
        if line_name == "consensus_decision":
            async def node(state: dict) -> dict:
                draft = _line(state, "consensus_decision").get("draft") or {}
                issues = draft.get("issues") or []
                if issues:
                    from tools.exports.html.consensus_decision import format_consensus_decision_markdown
                    title = self._compute_title(state)
                    text = format_consensus_decision_markdown(draft, title=title)
                    structure = issues
                else:
                    text, structure = self._domain_fallback_text(
                        state, line_name, self._fallback_rules[line_name]
                    )
                return {
                    "lines": {
                        "consensus_decision": {
                            "rendered": text,
                            "structure": structure,
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            return node
        return super()._make_fallback_node(line_name)

    def _post_render_hook(self, state: dict, line_name: str) -> None:
        super()._post_render_hook(state, line_name)
        if line_name in PREFERENCE_LINES and self._mode_label(state) == "personal":
            try:
                line_data = _line(state, line_name)
                rendered = line_data.get("rendered")
                if rendered and isinstance(rendered, str):
                    from perspective.hits import normalize_personal_sections
                    from perspective.preferences import address_aliases, extract_supervisors

                    user = state.get("user") or {}
                    name = str(user.get("name") or "").strip()
                    aliases = address_aliases(user)
                    addresses = [a for a in (name, *aliases) if a]
                    supervisors = extract_supervisors(user)
                    normalized = normalize_personal_sections(
                        rendered,
                        addresses=addresses,
                        self_name=name,
                        supervisors=supervisors,
                    )
                    if normalized != rendered:
                        line_data["rendered"] = normalized
            except Exception:
                logger.warning("normalize_personal_sections failed line=%s", line_name, exc_info=True)

    # ── 领域钩子：core 节点 ───────────────────────────────────

    def _build_core(self, builder, line_names=None) -> list[str]:
        """核心层：会议理解（所有线都需要）+ 视角建模（按线按需）。

        minutes_trace 是 deterministic 溯源线，不消费视角 → 跳过视角建模
        （省一次 LLM 调用 + 省大输入 token）。
        """
        builder.add_node(
            "meeting_understanding",
            self._make_meeting_understanding_node(line_names),
        )
        builder.add_edge(START, "meeting_understanding")
        cores = ["meeting_understanding"]
        selected = [name for name in (line_names or []) if name]
        skip_perspective = frozenset({"minutes_trace"})
        need_perspective = (not selected) or any(
            name not in skip_perspective for name in selected
        )
        if need_perspective:
            builder.add_node(
                "perspective_modeling", self._make_perspective_node(selected)
            )
            builder.add_edge("meeting_understanding", "perspective_modeling")
            cores = ["perspective_modeling"]
        return cores

    # ── 核心节点：会议理解（公共事实底座）──────────────────────

    def _make_perspective_node(self, line_names: list[str]):
        """会议域视角建模节点：客观跳过；真人命中非空时程序合成，省一轮核心调用。

        判定与理由见 ``perspective.synth.skip_reason``——唯一保留 LLM 的是
        "真人 + 完全没命中 + 挂 role_template"（要按职业关注域捞没点名的条目）。
        节点同时把命中表写进 state，供草稿（按人裁剪）与审核（复核依据）使用。
        降级：合成异常 → 空模型 + quality_degraded，不回退去跑 LLM（时间不可控）。
        """
        base_node = super()._perspective_modeling_node  # 绑定父类实现（闭包里不能直接用 super()）

        async def node(state: dict) -> dict:
            from perspective import (
                EMPTY_PERSPECTIVE_MODELING,
                build_hit_table,
                render_action_groups_block,
                render_hit_block,
                skip_reason,
                synthesize_perspective_profile,
            )

            if bool(state.get("objective_perspective")):
                progress("skip perspective (objective)")
                return {"perspective_profile": EMPTY_PERSPECTIVE_MODELING}

            user = state.get("user") or {}
            table = build_hit_table(user, self._understanding(state) or {})
            extra = {
                "user_hits": table.as_dict(),
                "user_hits_block": render_hit_block(table),
                # 分组骨架：把"要出现哪些组名行"变成可照抄的清单（模型只复制、不重排）
                "user_action_groups_block": render_action_groups_block(
                    user, self._understanding(state) or {}
                ),
            }
            reason = skip_reason(user, table, line_names)
            if not reason:
                result = await base_node(state)
                return {**result, **extra}
            try:
                profile = synthesize_perspective_profile(user, table)
            except Exception:  # noqa: BLE001 - 合成失败按降级处理，绝不把请求打成 500
                logger.warning("synthesize perspective failed, degrade", exc_info=True)
                return {
                    "perspective_profile": EMPTY_PERSPECTIVE_MODELING,
                    "quality_degraded": True,
                    **extra,
                }
            progress(f"skip perspective ({reason}) hits={len(table.hits)}")
            return {"perspective_profile": profile, **extra}

        return node

    def _understanding_skip(
        self, line_names, template: str = "", memory_on: bool = False
    ) -> frozenset[str]:
        """单线运行时的理解输出裁剪集合；多线 / 未注册线保持全量。

        minutes 线在基础集合之外再按**模板栏位**裁一次：模板没有风险/未决栏时，
        risks / open_questions 也不进理解输出（省下的输出 token 会随 pack 影响后续每一次调用）。
        开启会议记忆时保留 action_hints / risks / open_questions，供跨场状态机使用。
        """
        selected = [name for name in (line_names or []) if name]
        if len(selected) != 1 or selected[0] not in UNDERSTANDING_SKIP_FIELDS:
            return frozenset()
        skip = set(UNDERSTANDING_SKIP_FIELDS[selected[0]])
        if selected[0] == "minutes":
            skip |= skip_fields_for_template(template)
            if memory_on:
                skip -= {"action_hints", "risks", "open_questions"}
        return frozenset(skip)

    def _make_meeting_understanding_node(self, line_names):
        """会议理解节点：按本次选线裁剪输出（单线 API 场景省输出 token）。

        裁剪只影响理解层输出（跳过字段为 []），不改变字段契约，
        下游 pack / 审核 / 记忆读取逻辑零改动。
        """
        selected = [name for name in (line_names or []) if name]

        async def node(state: dict) -> dict:
            # 裁剪集合随模板变化（模板栏位决定 risks/open_questions 是否要抽），
            # 所以在节点内、拿到 state 之后再算。
            skip = self._understanding_skip(
                line_names,
                str((state.get("templates") or {}).get("minutes") or ""),
                memory_on=bool((state.get("line_extra") or {}).get("__meeting_memory__")),
            )
            focus = selected[0] if (skip and selected) else ""
            progress("agent start meeting_understanding")
            try:
                # 本用户称呼表：把"赵工/小赵"这类原文称呼统一成真名，供下游裁剪与 owner 使用
                # （客观/职业模板/无姓名 → 空串，不注入）
                from perspective import build_user_channel

                result = await self.meeting_understanding_agent.run(
                    state["transcript"],
                    focus_line=focus,
                    skip_fields=skip,
                    user_channel=build_user_channel(state.get("user") or {}),
                )
            except Exception:
                logger.warning("meeting understanding failed, continue with empty", exc_info=True)
                return {
                    "meeting_understanding": _EMPTY_MEETING_UNDERSTANDING,
                    "quality_degraded": True,
                }
            progress("agent done meeting_understanding")
            data = result.model_dump()
            # 形态标签程序优先：调用方已选模板 → 单点映射到 7 类形态（见 scene_hint.py）。
            # 模型自选的 scene 只作没有模板时的兜底——它只有 7 类可填，遇到发布会/课堂/就医
            # 这类细粒度场景会自造类别（曾致校验失败白跑一轮），归一后也只能落到「通用」骨架。
            hint = scene_hint_for_templates(state.get("templates"))
            if hint and data.get("scene") != hint:
                logger.info("scene hint from template: %s -> %s", data.get("scene"), hint)
                data["scene"] = hint
            return {"meeting_understanding": data}

        return node

class MeetingAgentSystem(_Nodes):
    """使用 LangGraph 编排会议分析、多线并行审核返工与最终输出。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

        # 通过工厂组装全部 Agent 依赖（键名 = 属性名，与 TASK_LINES 的 *_attr 对齐）
        agents = MeetingAgentFactory.create(self.client)

        # core 层挂载（手写，生成区外——不属于任务线，脚本扫描不到）
        self.meeting_understanding_agent: MeetingUnderstandingAgent = agents[
            "meeting_understanding_agent"
        ]
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling_agent"
        ]

        # ── Agent 挂载生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

        self.actions_agent: ActionItemsAgent = agents["actions_agent"]
        self.actions_supervisor: ActionItemsSupervisor = agents["actions_supervisor"]
        self.actions_render: ActionItemsRender = agents["actions_render"]
        self.consensus_decision_agent: ConsensusDecisionAgent = agents["consensus_decision_agent"]
        self.consensus_decision_supervisor: ConsensusDecisionSupervisor = agents["consensus_decision_supervisor"]
        self.consensus_decision_render: ConsensusDecisionRender = agents["consensus_decision_render"]
        self.mindmap_agent: MindmapAgent = agents["mindmap_agent"]
        self.mindmap_supervisor: MindmapSupervisor = agents["mindmap_supervisor"]
        self.mindmap_render: MindmapRender = agents["mindmap_render"]
        self.minutes_agent: MinutesGenerationAgent = agents["minutes_agent"]
        self.minutes_supervisor: MinutesGenerationSupervisor = agents["minutes_supervisor"]
        self.minutes_render: MinutesGenerationRender = agents["minutes_render"]
        self.minutes_styles_agent: MultiStylesAgent = agents["minutes_styles_agent"]
        self.minutes_styles_supervisor: MultiStylesSupervisor = agents["minutes_styles_supervisor"]
        self.minutes_styles_render: MultiStylesRender = agents["minutes_styles_render"]
        self.minutes_trace_agent: MinutesTraceAgent = agents["minutes_trace_agent"]
        self.minutes_trace_supervisor: MinutesTraceSupervisor = agents["minutes_trace_supervisor"]
        self.minutes_trace_render: MinutesTraceRender = agents["minutes_trace_render"]
        self.risks_agent: RiskAgent = agents["risks_agent"]
        self.risks_supervisor: RiskSupervisor = agents["risks_supervisor"]
        self.risks_render: RiskRender = agents["risks_render"]

        # ── Agent 挂载生成区结束 ──

        # 各线 Report 组装器：线名 → Report 类（脚本生成，键 = 线名与 chunk.line 一致）
        # ── Report 组装器生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "actions": ActionItemsReport,
            "consensus_decision": ConsensusDecisionReport,
            "mindmap": MindmapReport,
            "minutes": MinutesReport,
            "minutes_styles": MultiStylesReport,
            "minutes_trace": MinutesTraceReport,
            "risks": RiskReport,
        }

        # ── Report 组装器生成区结束 ──

        # 各线降级规则：线名 → FallbackRules 实例（脚本生成，图异常兜底用）
        # ── FallbackRules 注册生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "actions": ACTION_ITEMS_FALLBACK_RULES,
            "consensus_decision": CONSENSUS_DECISION_FALLBACK_RULES,
            "mindmap": MINDMAP_FALLBACK_RULES,
            "minutes": MINUTES_FALLBACK_RULES,
            "minutes_styles": MULTI_STYLES_FALLBACK_RULES,
            "minutes_trace": MINUTES_TRACE_FALLBACK_RULES,
            "risks": RISK_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = MeetingState
        self._quality_warning = QUALITY_WARNING

