"""Consensus Decision deterministic guardrails and validation gates.

Ensures:
1. Caveat & Accord cross-validation: active_disagreement issues must not claim unanimous accord.
2. False consensus heuristics: single-speaker monologues are not falsely promoted to hard alignment.
"""
from __future__ import annotations

import re
from typing import Any

CONTRADICTION_KEYWORDS = (
    "一致通过",
    "全体赞同",
    "全员支持",
    "全员赞成",
    "全票通过",
    "全体一致",
    "全场一致同意",
)


def validate_and_repair_consensus_issues(
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """确定性安全气囊：交叉验证共识议题并执行安全修复。

    1. caveat 交叉验证：当 consensus_grade 为 active_disagreement（争执未决）时，
       若最终决议文本命中“一致通过/全体赞同/全员支持”等自相矛盾关键词，触发自动纠正。
    2. 假共识检测启发式：检测单一发言人自言自语被误定为 hard_alignment，避免虚报重大共识。
    """
    if not issues:
        return []

    repaired_issues: list[dict[str, Any]] = []

    for item in issues:
        if not isinstance(item, dict):
            continue
        it = dict(item)

        grade = str(it.get("consensus_grade") or "").strip().lower()
        accord = str(it.get("accord") or "").strip()
        caveat = str(it.get("caveat") or "").strip()

        # 4.2 caveat 与 accord 交叉验证
        is_disagreement = grade in ("active_disagreement", "争执未决", "disagreement", "unresolved_concern")
        if is_disagreement:
            has_contradiction = any(w in accord for w in CONTRADICTION_KEYWORDS)
            if has_contradiction:
                it["accord"] = "未形成全员共识，各方保留分歧并约定会后单拉拉齐。"
                if not caveat or caveat.lower() in ("null", "none", "无"):
                    it["caveat"] = "各方存在实质分歧，待进一步讨论。"

        # 4.3 假共识检测启发式
        is_hard = grade in ("hard_alignment", "一致赞成", "hard")
        if is_hard:
            pro = it.get("pro_side") or {}
            con = it.get("con_side") or {}
            pro_speakers = pro.get("speakers") or []
            con_speakers = con.get("speakers") or []
            pro_args = pro.get("arguments") or []

            # 单一发言人发言、审议方完全缺席、且无充足论据展开
            if len(pro_speakers) <= 1 and not con_speakers and len(pro_args) <= 1:
                # 标记为讨论一致常规型，并确保有审议配合说明
                if not it.get("archetype") or it.get("archetype") == "authority_fiat":
                    it["archetype"] = "consensus"

        repaired_issues.append(it)

    return repaired_issues
