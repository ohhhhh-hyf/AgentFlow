"""真人路径：跳过视角建模 LLM，由程序合成瘦身视角模型（P1-C）。

为什么能省（对着代码核过的事实）：
1. 视角建模那轮的输入只有「理解 JSON + 画像」（``_perspective_input_context`` 有理解摘要
   就不发全文）——**它看不到原文**，所以"这个人是谁"它本来就答不了；
2. 它的产出被 ``_compact_perspective`` 砍到 7 个字段才给草稿，而这 7 个字段在"有命中"时
   全都能从 **命中表 + 画像** 算出来（attention_points≈命中条目、responsibilities≈职责∩命中、
   possible_actions≈我的待办、evidence≈命中依据）；
3. 真正读原文的是草稿那轮（它的上下文里有原文 + 理解 + 画像 + 命中表 + 偏好指令），
   视角模型只是"给草稿的指路条"——指路条能算出来就不必专门跑一轮生成它。

必须跑 LLM 的场景（保守口径）：**画像里有可扫关注域**（挂 role_template，或自写
focus_areas/interests/responsibilities）——"没点他名、但落在他关注域里"的条目只有建模能捞；
只有"极简画像（仅姓名/别称/偏好）"才允许程序合成接管。

合成结果必须过 ``PerspectiveModeling.validate``（全字段必填、四个字符串非空、其余字符串数组），
所以下面把 15 个键一个不落地填满；填不出的给 ``[]``（宁缺不编），每条依据写进 evidence。
"""
from __future__ import annotations

from typing import Any

from .hits import HitTable

# 允许程序合成的线集合：视角模型被所有线消费，多线（待办/风险）依赖可能的行动推断，
# 合成版会薄，所以只在"只跑纪要"时跳；多线保留建模（保守，等命中表跑稳再放开）。
SYNTH_LINES = frozenset({"minutes", "minutes_styles"})
_NO_HIT_SUMMARY = "本场未点到{name}，未发现与他直接相关的条目；分工栏可以为空。"


def skip_reason(user: dict[str, Any] | None, table: HitTable, line_names: Any = None) -> str | None:
    """返回跳过建模的理由（中文短语，供日志）；返回 None 表示这一轮必须跑建模。

    判定（与客观跳过同一处）：
    - 多线请求 → None（视角模型被多条线消费，且部分线看不到原文）
    - **画像有可扫关注域**（挂了 role_template，或自写了 focus_areas/interests/responsibilities）
      → None：这一格是"没点他名、但落在他关注域里"的条目，程序只有关键词可用，
      只有建模能做（保守口径；等关注域候选程序化后再放开）
    - 极简画像（只有姓名/别称/偏好）+ 命中非空 → ``命中非空``（agent 对它只能做"标记姓名"，
      那正是命中表的活）
    - 极简画像 + 未命中 → ``未命中且无关注域``（合成"本场未点到你"，分工允许空）
    """
    profile = user if isinstance(user, dict) else {}
    if not table.name:
        return None  # 没有可用称呼表（无姓名/客观/职业模板）：交给原路径判断
    names = {str(name).strip() for name in (line_names or []) if str(name).strip()}
    if names and not names <= SYNTH_LINES:
        return None  # 多线：待办/风险线还要用视角模型
    if _has_scan_scope(profile):
        return None  # 有可扫关注域 → 关注域那层只有建模能做
    if table.matched:
        return "命中非空"
    return "未命中且无关注域"


_SCAN_SCOPE_KEYS = ("focus_areas", "interests", "responsibilities")


def _has_scan_scope(profile: dict[str, Any]) -> bool:
    """画像里有没有"可扫的关注域"：挂职业底，或自写了职责/兴趣/关注领域。

    为什么它决定跑不跑建模：这几项正是"哪些条目算他关心的"的筛选依据，而这层筛选
    是语义的（"端侧双录确认"对开发者相关，但对一个只写了姓名的人无从判断）。
    程序手里只有关键词，所以有它就必须让建模扫一遍；只有极简画像（没给任何关注域）
    时才允许跳过——那时 agent 对它唯一能做的事（标记姓名被提及处）已被命中表覆盖。
    """
    if str(profile.get("role_template") or "").strip():
        return True
    for key in _SCAN_SCOPE_KEYS:
        items = profile.get(key)
        if isinstance(items, str) and items.strip():
            return True
        if any(str(item or "").strip() for item in items or []):
            return True
    return False


def _shares_phrase(left: str, right_items: list[str], size: int = 2) -> bool:
    """两个短语是否有 ≥size 字连续重合（"接口实现与联调" ↔ "接口联调周五前给测试" 靠"接口/联调"）。

    size=2 是刻意放松的：职责条目本身就是短语（接口/排期/验收/联调），3 字重合会全落空。
    这里给出的只是"他的哪几条职责本场用到了"的提示，事实仍以命中表为准，多给一条无害。
    """
    for right in right_items:
        text = str(right or "")
        for index in range(0, max(0, len(left) - size + 1)):
            if left[index : index + size] in text:
                return True
    return False


def _intersect(items: Any, hit_texts: list[str], cap: int = 4) -> list[str]:
    """画像里的职责/关注域条目，与本场命中有关的那些（没命中就为空，不硬塞）。"""
    out: list[str] = []
    for item in items or []:
        text = " ".join(str(item or "").split()).strip()
        if text and text not in out and _shares_phrase(text, hit_texts):
            out.append(text)
        if len(out) >= cap:
            break
    return out


def synthesize_perspective_profile(user: dict[str, Any] | None, table: HitTable) -> dict[str, Any]:
    """按命中表 + 画像拼一份过得了 schema 的视角模型（纯函数，零 LLM）。"""
    from .models import EMPTY_PERSPECTIVE_MODELING

    profile = user if isinstance(user, dict) else {}
    name = table.name
    # "内容型"命中：发言人名单独出现不算内容（attention_points / 摘要里都不要碎话）
    hit_texts = [hit.snippet for hit in table.hits if hit.snippet and hit.snippet != name]
    actions = [f"原文承诺：{text}" for text in table.my_actions[:6]]
    role = " ".join(str(profile.get("role") or "").split()).strip()

    if table.matched:
        # 摘要只取"内容型"命中：发言人名这类空壳不算内容（避免"…；赵衡。"这种碎话）
        contents = [*table.my_actions, *table.my_risks, *table.my_topics]
        contents += [text for text in hit_texts if text not in contents]
        head = "；".join(contents[:2]) or f"本场有 {len(table.hits)} 处提到{name}"
        summary = f"本场与{name}直接相关：{head}。"[:120]
    else:
        summary = _NO_HIT_SUMMARY.format(name=name)

    profile_out = dict(EMPTY_PERSPECTIVE_MODELING)
    profile_out.update(
        {
            "confidence": "high" if table.confidence == "high" else "medium",
            "name": name,
            "inferred_role": role or "未提及",
            "personal_summary": summary,
            "responsibilities": _intersect(profile.get("responsibilities"), hit_texts),
            "possible_actions": actions,
            "attention_points": hit_texts[:8],
            "evidence": table.evidence()[:8],
        }
    )
    return profile_out


__all__ = ["SYNTH_LINES", "skip_reason", "synthesize_perspective_profile"]
