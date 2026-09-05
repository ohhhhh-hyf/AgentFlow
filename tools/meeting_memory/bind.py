"""Project binding for meeting memory v2."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tools.memory.store import safe_id


@dataclass(frozen=True)
class BindResult:
    project_id: str = ""
    mode: str = "auto"
    confidence: str = "low"
    evidence: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warning: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "mode": self.mode,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }
        if self.candidates:
            out["candidates"] = self.candidates
        if self.warning:
            out["warning"] = self.warning
        return out


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


_GENERIC_ANCHORS = frozenset(
    """
    agent memory 会议 会议纪要 会议记忆 历史会议 历史记忆 记忆引用
    复盘 总结 汇报 评审 例会 周会 沟通 讨论 推进 跟进
    项目 项目组 进展 开发进展 阶段 内测 问题 风险 阻塞
    功能不可用 用户 客户 产品 运营 测试 上线 交付
    """.split()
)
_PROJECT_TAIL_RE = re.compile(
    r"(开发进展|阶段复盘|内测前推进会|内测推进会|推进会|收口会|"
    r"周会|例会|月会|评审会|复盘会|沟通会|汇报会|会议|复盘|总结)$"
)


def _project_core(text: object) -> str:
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


def _looks_malformed_anchor(text: str, project_name: str) -> bool:
    del project_name
    raw = _clean(text)
    if not raw or re.search(r"[A-Za-z0-9_\-]", raw):
        return False
    if re.match(r"^(复盘|跟进|推进|总结|确认|讨论|汇报)", raw):
        return True
    if raw.endswith(("第", "第一", "阶段第")):
        return True
    # 相邻汉字 n-gram 容易切出这种不成词片段；只拦明显边界坏的短片段。
    if 3 <= len(raw) <= 4 and raw[0] in "的一是在和与及" :
        return True
    return False


def _strong_anchor(text: str) -> bool:
    raw = _clean(text)
    if _is_generic_anchor(raw):
        return False
    # 中文+拉丁混合名、较长专名、含下划线模块名更像项目身份。
    if re.search(r"[\u4e00-\u9fff]", raw) and re.search(r"[A-Za-z]", raw):
        return len(raw) >= 4
    if "_" in raw or "-" in raw:
        return len(raw) >= 6
    return len(raw) >= 5


def _pick_project_name(fact: Any) -> str:
    """从本场事实中选择项目名：标题（headline/会议主题行）整体为第一信号，
    靠 LCSubstring/名称包含匹配消化会种尾缀；标题不可用才回退候选中的拉丁实体。"""
    title = _clean(getattr(fact, "title", ""))
    if 2 <= len(title) <= 40:
        return title
    cands = [str(x).strip() for x in (getattr(fact, "project_candidates", None) or []) if str(x).strip()]
    for c in cands:
        core = _project_core(c)
        if 4 <= len(core) <= 24 and re.search(r"[A-Za-z]", core):
            return core
    if cands:
        return _project_core(max(cands, key=len))[:30]
    return ""


def _longest_common_substr(a: str, b: str) -> str:
    """两个标题的最长公共连续子串。"""
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
    # "Agent" 这类纯英文公共片段不能单独证明同一项目。
    if re.search(r"[\u4e00-\u9fff]", text):
        return True
    return len(text) >= 8 and not _is_generic_anchor(text)


def _contains_any(blob: str, values: list[str]) -> list[str]:
    hits: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text in blob and text not in hits:
            hits.append(text)
    return hits


def _project_hits(project: dict[str, Any], fact: Any) -> dict[str, Any]:
    blob = " ".join([
        _clean(getattr(fact, "title", "")),
        _clean(getattr(fact, "summary", "")),
        " ".join(getattr(fact, "anchors", []) or []),
        " ".join(getattr(fact, "decisions", []) or []),
        " ".join(getattr(fact, "open_items", []) or []),
        " ".join(getattr(fact, "risks", []) or []),
    ])
    names = _contains_any(blob, [_clean(project.get("name"))])
    aliases = _contains_any(blob, [str(x) for x in (project.get("aliases") or [])])
    raw_anchors = _contains_any(blob, [str(x) for x in (project.get("anchors") or [])])
    negative = _contains_any(blob, [str(x) for x in (project.get("negative_anchors") or [])])
    project_name = _clean(project.get("name"))
    anchors: list[str] = []
    generic: list[str] = []
    malformed: list[str] = []
    for anchor in raw_anchors:
        if _looks_malformed_anchor(anchor, project_name):
            malformed.append(anchor)
        elif _is_generic_anchor(anchor):
            generic.append(anchor)
        else:
            anchors.append(anchor)
    # 标题公共核心：本场标题与项目名的最长公共连续子串 ≥5 字 → 视为同一项目
    # （项目名可能是第一场标题整体，如「…阶段复盘」，后续「…内测前推进会」靠公共核心命中）
    if not names and not aliases:
        pname = _project_core(project.get("name"))
        ftitle = _clean(getattr(fact, "title", ""))
        common = _longest_common_substr(ftitle, pname) if pname and ftitle else ""
        if _valid_common_core(common):
            names = [common[:24]]
    strong = [anchor for anchor in anchors if _strong_anchor(anchor)]
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
                warning = "显式 project 与本场 anchors 无重叠，请确认是否误传。"
        return BindResult(
            project_id=pid,
            mode="explicit",
            confidence="high",
            evidence=[f"project:{pid}"],
            warning=warning,
        )

    scored: list[dict[str, Any]] = []
    for pid, project in (projects or {}).items():
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
    scored = sorted(scored, key=lambda x: -int(x["score"]))
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
    # 全部未命中（registry 空或与任何项目零重叠）：从本场内容提取项目实体，
    # 自动注册项目指纹，供后续同项目会议实体匹配溯源。
    # mode="auto_create"：runtime 层会在此之后做语义归属兜底——本项目标题
    # 换了说法时规则零重叠，但向量可命中历史项目（救回变体、防重复建档）。
    name = _pick_project_name(fact)
    if name:
        pid = safe_id(name)
        return BindResult(
            project_id=pid,
            mode="auto_create",
            confidence="high",
            evidence=[f"auto_create:{name}"],
        )
    return BindResult()


__all__ = ["BindResult", "bind_meeting"]
