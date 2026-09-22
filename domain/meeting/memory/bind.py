"""Project binding for meeting memory v2."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tools.core.ids import safe_id


@dataclass(frozen=True)
class BindResult:
    project_id: str = ""
    mode: str = "auto"
    confidence: str = "low"
    evidence: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warning: str = ""
    core_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "project_id": self.project_id,
            "mode": self.mode,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }
        if self.candidates:
            out["candidates"] = self.candidates
        if self.warning:
            out["warning"] = self.warning
        if self.core_name:
            out["core_name"] = self.core_name
        return out

    @property
    def is_bound(self) -> bool:
        """High-confidence identity: inject history and merge project state."""
        return bool(self.project_id) and self.confidence == "high"


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


_GENERIC_ANCHORS = frozenset(
    """
    agent memory 会议 会议纪要 会议记忆 历史会议 历史记忆 记忆引用
    复盘 总结 汇报 评审 例会 周会 沟通 讨论 推进 跟进
    项目 项目组 进展 开发进展 阶段 内测 问题 风险 阻塞
    用户 客户 产品 运营 测试 上线 交付
    """.split()
)
_PROJECT_TAIL_RE = re.compile(
    r"(开发进展|阶段复盘|推进会|收口会|"
    r"周会|例会|月会|评审会|复盘会|沟通会|汇报会|会议|复盘|总结)$"
)
_TASK_TAILS = (
    "整理", "优化", "确认", "讨论", "推进", "跟进", "落实", "排查",
    "修复", "开发", "测试", "上线", "对齐", "评估", "检查",
)
_LEAD_VERBS = (
    "复盘", "跟进", "确认", "围绕", "讨论", "召开", "汇报", "总结", "明确",
    "识别", "优化", "推进", "完成", "加快", "梳理", "协调", "沟通", "整理",
)


def project_core(text: object) -> str:
    """Strip meeting-kind suffixes so 阶段复盘 / 推进会 share one identity."""
    core = _clean(text)
    for _ in range(3):
        new = _PROJECT_TAIL_RE.sub("", core).strip(" -_：:，,")
        if new == core:
            break
        core = new
    return core


def _is_generic_anchor(text: str) -> bool:
    raw = _clean(text)
    if not raw:
        return True
    if raw.lower() in _GENERIC_ANCHORS or raw in _GENERIC_ANCHORS:
        return True
    if len(raw) <= 2:
        return True
    return False


def _looks_malformed_anchor(text: str) -> bool:
    raw = _clean(text)
    if not raw or re.search(r"[A-Za-z0-9_\-]", raw):
        return False
    if re.match(r"^(复盘|跟进|推进|总结|确认|讨论|汇报)", raw):
        return True
    if raw.endswith(("第", "第一", "阶段第")):
        return True
    if 3 <= len(raw) <= 4 and raw[0] in "的一是在和与及":
        return True
    return False


def is_strong_anchor(text: str) -> bool:
    """Identity-grade token: mixed CN+EN, module ids, or a longer proper name.

    Verb-noun task phrases (任务目录整理) are not strong even if ≥5 chars.
    """
    raw = _clean(text)
    if _is_generic_anchor(raw) or _looks_malformed_anchor(raw):
        return False
    if any(raw.startswith(v) or raw.endswith(v) for v in _TASK_TAILS):
        if not re.search(r"[A-Za-z]", raw):
            return False
    if re.search(r"[\u4e00-\u9fff]", raw) and re.search(r"[A-Za-z]", raw):
        return len(raw) >= 4
    if "_" in raw or "-" in raw:
        return len(raw) >= 6
    return len(raw) >= 8


def is_weak_project_name(text: str) -> bool:
    """True when this should not become a new project_id."""
    core = project_core(text)
    if not core or _is_generic_anchor(core) or _looks_malformed_anchor(core):
        return True
    if is_strong_anchor(core):
        return False
    if any(core.startswith(v) for v in _LEAD_VERBS):
        return True
    if not re.search(r"[A-Za-z]", core) and len(core) < 8:
        return True
    return True


def pick_project_name(fact: Any) -> str:
    """Stable project core: mixed/quoted proper name, not the first topic."""
    title = _clean(getattr(fact, "title", ""))
    core = project_core(title)
    if core and not is_weak_project_name(core):
        return core
    cands = [
        str(x).strip()
        for x in (getattr(fact, "project_candidates", None) or [])
        if str(x).strip()
    ]
    for c in cands:
        piece = project_core(c)
        if piece and not is_weak_project_name(piece) and is_strong_anchor(piece):
            return piece
    for c in cands:
        if re.search(r"[A-Za-z]", c):
            piece = project_core(c)
            if 4 <= len(piece) <= 24 and not is_weak_project_name(piece):
                return piece
    return ""


def _longest_common_substr(a: str, b: str) -> str:
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    best = 0
    end = 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > best:
                    best = dp[i][j]
                    end = i
            else:
                dp[i][j] = 0
    return a[end - best:end]


def _valid_common_core(text: str) -> bool:
    if len(text) < 5:
        return False
    if re.search(r"[\u4e00-\u9fff]", text):
        return not _is_generic_anchor(text)
    return len(text) >= 8 and not _is_generic_anchor(text)


def _contains_any(blob: str, values: list[str]) -> list[str]:
    hits: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text in blob and text not in hits:
            hits.append(text)
    return hits


def _fact_blob(fact: Any) -> str:
    return " ".join([
        _clean(getattr(fact, "title", "")),
        _clean(getattr(fact, "summary", "")),
        " ".join(getattr(fact, "anchors", []) or []),
        " ".join(getattr(fact, "project_candidates", []) or []),
        " ".join(getattr(fact, "decisions", []) or []),
        " ".join(getattr(fact, "open_items", []) or []),
        " ".join(getattr(fact, "risks", []) or []),
        " ".join(
            _clean(x.get("text") if isinstance(x, dict) else x)
            for x in (getattr(fact, "action_items", None) or [])
        ),
    ])


def _project_hits(project: dict[str, Any], fact: Any) -> dict[str, Any]:
    blob = _fact_blob(fact)
    names = _contains_any(blob, [_clean(project.get("name"))])
    aliases = _contains_any(blob, [str(x) for x in (project.get("aliases") or [])])
    raw_anchors = _contains_any(blob, [str(x) for x in (project.get("anchors") or [])])
    negative = _contains_any(blob, [str(x) for x in (project.get("negative_anchors") or [])])
    anchors: list[str] = []
    generic: list[str] = []
    malformed: list[str] = []
    for anchor in raw_anchors:
        if _looks_malformed_anchor(anchor):
            malformed.append(anchor)
        elif _is_generic_anchor(anchor):
            generic.append(anchor)
        else:
            anchors.append(anchor)
    if not names and not aliases:
        pname = project_core(project.get("name"))
        ftitle = project_core(getattr(fact, "title", ""))
        common = _longest_common_substr(ftitle, pname) if pname and ftitle else ""
        if _valid_common_core(common):
            names = [common[:24]]
        else:
            # alias cores vs this meeting title/core
            for alias in [str(x) for x in (project.get("aliases") or [])]:
                acore = project_core(alias)
                common = _longest_common_substr(ftitle, acore) if acore and ftitle else ""
                if _valid_common_core(common):
                    names = [common[:24]]
                    break
    strong = [anchor for anchor in anchors if is_strong_anchor(anchor)]
    topic = [anchor for anchor in anchors if anchor not in strong]
    return {
        "name_alias": names + aliases,
        "strong_anchors": strong,
        "topic_anchors": topic,
        "generic_anchors": generic,
        "malformed_anchors": malformed,
        "negative": negative,
    }


def _score_hits(hits: dict[str, Any]) -> int:
    score = (
        len(hits["name_alias"]) * 30
        + len(hits["strong_anchors"]) * 8
        + len(hits["topic_anchors"]) * 3
    )
    if hits["negative"]:
        score -= 40
    return score


def _has_strong_signal(row: dict[str, Any]) -> bool:
    if row["name_alias"]:
        return True
    if row["strong_anchors"]:
        return True
    return False


def _high(row: dict[str, Any]) -> bool:
    if row["negative"]:
        return False
    return bool(_has_strong_signal(row) and int(row["score"]) >= 8)


def _clear_winner(top: dict[str, Any], second: dict[str, Any] | None) -> bool:
    if not _high(top):
        return False
    if second is None or int(second.get("score") or 0) <= 0:
        return True
    top_score = int(top.get("score") or 0)
    second_score = int(second.get("score") or 0)
    return top_score >= second_score * 2 or top_score - second_score >= 10


def score_projects(registry: dict[str, Any], fact: Any) -> list[dict[str, Any]]:
    projects = registry.get("projects") or {}
    scored: list[dict[str, Any]] = []
    for pid, project in projects.items():
        if not isinstance(project, dict):
            continue
        hits = _project_hits(project, fact)
        score = _score_hits(hits)
        if score:
            scored.append({
                "project_id": str(pid),
                "name_alias": hits["name_alias"],
                "strong_anchors": hits["strong_anchors"],
                "topic_anchors": hits["topic_anchors"],
                "generic_anchors": hits["generic_anchors"],
                "malformed_anchors": hits["malformed_anchors"],
                "negative": hits["negative"],
                "score": score,
            })
    return sorted(scored, key=lambda x: -int(x["score"]))


def has_overlap(project: dict[str, Any], fact: Any) -> bool:
    """Any non-generic name/alias/anchor overlap — used by single-project prior."""
    hits = _project_hits(project, fact)
    if hits["negative"]:
        return False
    return bool(hits["name_alias"] or hits["strong_anchors"] or hits["topic_anchors"])


def bind_meeting(
    registry: dict[str, Any],
    fact: Any,
    *,
    explicit_project: str = "",
) -> BindResult:
    """Bind a meeting to a project with hard gates against one-token matches."""
    explicit = _clean(explicit_project)
    projects = registry.setdefault("projects", {})
    if explicit:
        pid = safe_id(explicit)
        project = projects.get(pid) if isinstance(projects, dict) else None
        warning = ""
        if isinstance(project, dict):
            hits = _project_hits(project, fact)
            if not hits["name_alias"] and not hits["strong_anchors"] and not hits["topic_anchors"]:
                warning = "显式 project 与本场内容无重叠，请确认是否误传。"
        return BindResult(
            project_id=pid,
            mode="explicit",
            confidence="high",
            evidence=[f"project:{pid}"],
            warning=warning,
            core_name=project_core(explicit) or explicit,
        )

    scored = score_projects(registry, fact)
    highs = [row for row in scored if _high(row)]
    if highs and _clear_winner(highs[0], scored[1] if len(scored) > 1 else None):
        row = highs[0]
        evidence = [f"alias:{x}" for x in row["name_alias"]]
        evidence.extend(f"strong_anchor:{x}" for x in row["strong_anchors"])
        evidence.extend(f"topic_anchor:{x}" for x in row["topic_anchors"][:3])
        return BindResult(
            project_id=row["project_id"],
            mode="auto",
            confidence="high",
            evidence=evidence,
            candidates=scored[:3],
        )
    if highs:
        return BindResult(
            mode="auto",
            confidence="medium",
            evidence=["ambiguous_or_close_candidates"],
            candidates=sorted(highs, key=lambda x: -int(x["score"]))[:3],
        )
    if scored:
        return BindResult(
            mode="auto",
            confidence="medium",
            evidence=["semantic_or_single_anchor_only"],
            candidates=sorted(scored, key=lambda x: -int(x["score"]))[:3],
        )
    name = pick_project_name(fact)
    if name:
        pid = safe_id(name)
        return BindResult(
            project_id=pid,
            mode="auto_create",
            confidence="high",
            evidence=[f"auto_create:{name}"],
            core_name=name,
        )
    return BindResult()


__all__ = [
    "BindResult",
    "bind_meeting",
    "has_overlap",
    "is_strong_anchor",
    "is_weak_project_name",
    "pick_project_name",
    "project_core",
    "score_projects",
]
