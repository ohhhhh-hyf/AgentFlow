"""tools.templates.router.guard —— 模板路由·前置约束守卫层。

核心原则：
- 专题讲座 (special_lecture) 必须且只能服务于“单核心主讲人（Single Presenter）”的授课或独白演讲场景。
- 规则加固：如果原文中出现多方平等讨论、发言人交替（如“发言人1、2、3、4、5”共同交流感受），
  严禁判定为专题讲座；必须分流至圆桌研讨会 (group_seminar)、沟通交流会 (exchange_forum) 或通用纪要 (general_minutes)。
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 发言行匹配正则：
# 支持「发言人1:」「发言人2：」「发言者A:」「贝姐:」「【张教授】:」「张三：」等行首发言标记
_SPEAKER_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s*)?(?:【)?([A-Za-z0-9_\u4e00-\u9fa5]{1,12})(?:】)?\s*[:：]\s*(.+?)(?=(?:\n\s*(?:[-*]\s*)?(?:【)?[A-Za-z0-9_\u4e00-\u9fa5]{1,12}(?:】)?\s*[:：])|$)",
    re.DOTALL,
)

# 明确的单人授课/演讲角色关键词（有此类角色且占主导时才可能是讲座）
_LECTURER_ROLE_KEYWORDS = {
    "主讲人",
    "演讲者",
    "主讲",
    "讲师",
    "主讲嘉宾",
    "报告人",
    "授课老师",
    "主讲教师",
    "教授",
    "专家",
}


def analyze_speaker_topology(
    transcript: str,
    speakers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """分析素材中的发言人拓扑分布（发言人数、发言篇幅占比、轮替交替活跃度）。

    返回字典包含：
    - distinct_speakers: 独立发言人名字集合（去重）
    - distinct_speaker_count: 独立发言人数
    - speaker_chars: 各发言人发言汉字/字符总数
    - speaker_turns: 各发言人发言轮次数
    - turn_count: 总发言轮次数
    - turn_switches: 跨发言人切换次数
    - dominant_speaker: 发言字数最多的发言人
    - dominant_speaker_ratio: 最大发言人字数占全部发言字数的比例 (0.0 ~ 1.0)
    - has_explicit_lecturer: 是否在 speakers 事实索引中声明了专职主讲角色
    - is_multi_party_discussion: 是否构成“多方平等讨论/无单一核心主讲人”
    """
    text = (transcript or "").strip()
    speaker_chars: dict[str, int] = {}
    speaker_turns: dict[str, int] = {}
    turn_sequence: list[str] = []

    # 1. 从原文正文提取发言人行段落
    if text:
        for match in _SPEAKER_LINE_RE.finditer(text):
            spk_raw = match.group(1).strip()
            # 过滤误伤标记（如时间、常见前缀标签）
            if spk_raw in {"时间", "地点", "出席", "参会", "注意", "提示", "背景", "说明", "要求"}:
                continue
            content = match.group(2).strip()
            # 简单清洗发言内容长度（汉字 + 字符）
            content_len = len(re.sub(r"\s+", "", content))
            if content_len == 0:
                continue

            speaker_chars[spk_raw] = speaker_chars.get(spk_raw, 0) + content_len
            speaker_turns[spk_raw] = speaker_turns.get(spk_raw, 0) + 1
            turn_sequence.append(spk_raw)

    # 2. 如果原文通过正则提取到的发言人过少（或无显式冒号），辅以传入的 speakers 事实索引
    speakers_from_meta = speakers or []
    has_explicit_lecturer = False
    for spk_info in speakers_from_meta:
        if not isinstance(spk_info, dict):
            continue
        role = str(spk_info.get("role") or "").strip()
        name = str(spk_info.get("name") or "").strip()
        if any(kw in role for kw in _LECTURER_ROLE_KEYWORDS):
            has_explicit_lecturer = True
        if name and name not in speaker_chars:
            # 补充记入
            speaker_chars.setdefault(name, 1)

    distinct_speakers = list(speaker_chars.keys())
    distinct_speaker_count = len(distinct_speakers)
    total_chars = sum(speaker_chars.values())
    turn_count = len(turn_sequence)

    turn_switches = 0
    for i in range(1, len(turn_sequence)):
        if turn_sequence[i] != turn_sequence[i - 1]:
            turn_switches += 1

    if speaker_chars and total_chars > 0:
        dominant_speaker = max(speaker_chars, key=lambda k: speaker_chars[k])
        dominant_speaker_ratio = speaker_chars[dominant_speaker] / total_chars
    else:
        dominant_speaker = ""
        dominant_speaker_ratio = 0.0

    # 3. 判定是否为“多方平等讨论/无单一核心主讲人”
    # 核心判断逻辑：
    # A. 独立发言人 >= 3 位
    # B. 且最大发言人占比 < 60%（不存在占绝对统治地位的单人授课/演讲）
    # C. 且至少存在多轮交替（turn_switches >= 3 或 speakers >= 3 且无专职主讲人）
    is_multi_party = False
    if distinct_speaker_count >= 3:
        if not has_explicit_lecturer:
            # 无专职主讲人，且最大发言人未超过 60% 篇幅
            if dominant_speaker_ratio < 0.60:
                is_multi_party = True
            elif turn_switches >= 4:
                # 即使某一发言人稍长，但有频繁交替互动，且多人参与
                is_multi_party = True
        else:
            # 虽有主讲角色标注，但主讲人篇幅不足 50%，且多人热烈交替讨论
            if dominant_speaker_ratio < 0.50 and turn_switches >= 5:
                is_multi_party = True

    return {
        "distinct_speakers": distinct_speakers,
        "distinct_speaker_count": distinct_speaker_count,
        "speaker_chars": speaker_chars,
        "speaker_turns": speaker_turns,
        "turn_count": turn_count,
        "turn_switches": turn_switches,
        "dominant_speaker": dominant_speaker,
        "dominant_speaker_ratio": dominant_speaker_ratio,
        "has_explicit_lecturer": has_explicit_lecturer,
        "is_multi_party_discussion": is_multi_party,
    }


def is_special_lecture_disqualified(
    transcript: str,
    speakers: list[dict[str, Any]] | None = None,
) -> tuple[bool, str, str]:
    """判断当前会议素材是否违背专题讲座 (special_lecture) 的单一主讲人硬前置约束。

    返回:
        (disqualified, reason, suggested_template_id)
        - disqualified: True 表示严禁使用专题讲座模板
        - reason: 拦截并分流的具体原因
        - suggested_template_id: 建议分流的目标模板 ID（如 group_seminar / exchange_forum）
    """
    topology = analyze_speaker_topology(transcript, speakers)
    if topology["is_multi_party_discussion"]:
        spk_count = topology["distinct_speaker_count"]
        ratio = topology["dominant_speaker_ratio"]
        reason = (
            f"检测到 {spk_count} 位发言人平等互动交替（最大发言人篇幅仅占 {ratio:.1%}，"
            f"轮替切换 {topology['turn_switches']} 次），属于典型多方圆桌交流场景，"
            f"严禁套用单核心主讲人的专题讲座模板"
        )
        # 默认分流到圆桌研讨会 (group_seminar)
        return True, reason, "group_seminar"

    return False, "", "special_lecture"


def guard_template_routing(
    template_id_or_text: str,
    transcript: str,
    speakers: list[dict[str, Any]] | None = None,
    default_fallback: str = "group_seminar",
) -> tuple[str, bool, str]:
    """对选定的模板执行硬前置约束守卫检查。

    若指定了 special_lecture 但素材为多方平等讨论，触发拦截重定向。

    返回:
        (effective_template_id, was_redirected, reason)
    """
    raw = (template_id_or_text or "").strip()
    is_special_lecture = (
        raw == "special_lecture"
        or raw == "专题讲座"
        or raw.startswith("# 专题讲座")
        or "\n# 专题讲座" in raw
    )

    if not is_special_lecture:
        return raw, False, ""

    disqualified, reason, fallback_id = is_special_lecture_disqualified(transcript, speakers)
    if disqualified:
        target = fallback_id or default_fallback
        logger.warning(
            "[Template Router Guard] 触发专题讲座硬前置约束拦截：%s。已安全自动重定向分流至「%s」",
            reason,
            target,
        )
        return target, True, reason

    return "special_lecture", False, ""


def load_fallback_template_text(template_id: str) -> str:
    """按模板 ID 加载其模板文本（含 requirement 包装）。"""
    try:
        from app.config import resolve_template_format
        fmt = resolve_template_format(template_id)
        if fmt:
            return fmt
    except Exception:
        pass

    import os
    from pathlib import Path
    custom_dir = os.getenv("AGENTFLOW_TEMPLATE_DIR", "").strip()
    candidates: list[Path] = []
    if custom_dir:
        candidates.append(Path(custom_dir))
    candidates.extend([
        Path("template_v3"),
        Path("template_v2"),
        Path(__file__).resolve().parents[3] / "template_v3",
        Path(__file__).resolve().parents[3] / "template_v2",
    ])
    for cdir in candidates:
        target_path = cdir / f"{template_id}.md"
        if target_path.is_file():
            try:
                from ._base import split_template_meta, wrap_template_requirement
                raw = target_path.read_text(encoding="utf-8")
                body, req = split_template_meta(raw)
                return wrap_template_requirement(body, req)
            except Exception:
                continue
    return ""


def resolve_guarded_template(
    current_template: str,
    transcript: str,
    speakers: list[dict[str, Any]] | None = None,
    default_fallback: str = "group_seminar",
) -> tuple[str, bool, str]:
    """对输出模板执行前置守卫：若命中拦截，返回分流目标模板文本。

    返回:
        (effective_template_text, was_redirected, reason)
    """
    target_id, redirected, reason = guard_template_routing(
        current_template,
        transcript=transcript,
        speakers=speakers,
        default_fallback=default_fallback,
    )
    if not redirected:
        return current_template, False, ""

    fallback_text = load_fallback_template_text(target_id)
    if fallback_text:
        return fallback_text, True, reason

    # 兜底：如果模板文本加载失败，返回原模板避免流程中断
    logger.error("[Template Router Guard] 重定向目标模板 %s 文本读取失败，回退原模板", target_id)
    return current_template, False, reason
