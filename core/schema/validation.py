from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class OutputValidationError(ValueError):
    """模型输出未通过结构校验。"""
    pass


# ── 共享校验工具（供各模型的 validate 类方法使用） ──────────────

def _exact_fields(data: dict, expected: set | list, path: str) -> None:
    if not isinstance(data, dict):
        raise OutputValidationError(f"{path} 必须是 JSON 对象")
    actual = set(data)
    expected = set(expected)
    if actual != expected:
        raise OutputValidationError(
            f"{path} 字段不一致：缺失={sorted(expected - actual)}，"
            f"多余={sorted(actual - expected)}"
        )


def _string(value: object, path: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str):
        raise OutputValidationError(f"{path} 必须是字符串")


def _string_list(value: object, path: str) -> None:
    if not isinstance(value, list):
        raise OutputValidationError(f"{path} 必须是数组")
    # 容错归一：若大模型在数组里给出了 dict (如 {"risk": "...", ...}) 或非字符串项，
    # 自动提取主要文本字段或转为字符串，绝对不因顶层 dict 格式打回重试
    for i, item in enumerate(value):
        if isinstance(item, str):
            continue
        if isinstance(item, dict):
            cand = (
                item.get("risk")
                or item.get("decision")
                or item.get("task")
                or item.get("action")
                or item.get("text")
                or item.get("content")
                or item.get("question")
                or item.get("issue")
            )
            if cand and isinstance(cand, str):
                value[i] = cand
                continue
            value[i] = str(item)
        elif item is not None:
            value[i] = str(item)
        else:
            value[i] = ""


def _choice(value: object, choices: set, path: str) -> None:
    if value not in choices:
        raise OutputValidationError(f"{path} 必须是 {sorted(choices)} 之一")


def _choice_or_default(value: object, choices: set, default: str) -> object:
    """枚举容错：不在 choices 内时归一到 default（不抛错），合法值原样返回。

    为什么（2026-09-18 实测）：理解层 scene 是 7 个**粗粒度形态标签**，而真实场景有二十多种
    （产品发布、新闻发布、课堂、讲座、就医…）→ 模型自然填「产品发布」→ `_choice` 抛错 →
    客户端重试一轮（多一次调用 + 12s，两次返回内容一字不变）。枚举类字段的失败几乎都源于
    "选项覆盖不到内容"，对这类**形态标签**字段（不影响事实正确性）用归一兜底更划算；
    枚举承载硬语义时（如审核 status）仍用 `_choice` 严格校验。
    """
    return value if value in choices else default


def _review_check(value: dict, path: str) -> None:
    _exact_fields(value, {"status", "findings"}, path)
    _choice(value["status"], {"pass", "fail"}, f"{path}.status")
    _string_list(value["findings"], f"{path}.findings")


def _action(item: dict, path: str) -> None:
    required = {
        "task", "owner", "deadline", "priority",
        "status", "evidence", "confidence",
    }
    allowed = required | {"category", "deliverable", "dependency"}
    if not isinstance(item, dict):
        raise OutputValidationError(f"{path} 必须是 JSON 对象")
    actual = set(item)
    missing = required - actual
    extra = actual - allowed
    if missing or extra:
        raise OutputValidationError(
            f"{path} 字段不一致：缺失={sorted(missing)}，"
            f"多余={sorted(extra)}"
        )
    _string(item["task"], f"{path}.task")
    _string(item["owner"], f"{path}.owner", nullable=True)
    _string(item["deadline"], f"{path}.deadline", nullable=True)
    _choice(item["priority"], {"high", "medium", "low"}, f"{path}.priority")
    _choice(item["status"], {"explicit", "inferred"}, f"{path}.status")
    _string(item["evidence"], f"{path}.evidence")
    _choice(item["confidence"], {"high", "medium", "low"}, f"{path}.confidence")
    if "category" in item:
        _string(item["category"], f"{path}.category", nullable=True)
    if "deliverable" in item:
        _string(item["deliverable"], f"{path}.deliverable", nullable=True)
    if "dependency" in item:
        _string(item["dependency"], f"{path}.dependency", nullable=True)


def validate_supervisor_semantics(
    decision: object,
    feedback: list,
    checks: dict[str, dict],
) -> None:
    """审核模型的公共语义校验（所有审核模型共用）。

    审核模型（Minutes/Actions 等）的通用骨架规则：
    - decision 只能是 approve / revise / reject
    - approve 时不得有失败检查项、不得有返工意见
    - revise 时必须有返工意见
    - reject 时至少一个检查项失败

    Args:
        decision: decision 字段的值（approve / revise / reject）。
        feedback: feedback 字段的值（字符串数组）。
        checks: 本模型的全部检查项，键为检查项名、值为检查项 dict
            （{"status": "pass|fail", "findings": [...]}）。
    """
    _choice(decision, {"approve", "revise", "reject"}, "decision")

    failed = [
        key for key, check in checks.items()
        if check["status"] == "fail"
    ]
    if decision == "approve" and failed:
        raise OutputValidationError(
            f"decision=approve 时检查项不得失败：{failed}"
        )
    if decision == "approve" and feedback:
        raise OutputValidationError("decision=approve 时返工意见必须为空")
    if decision == "revise" and not feedback:
        raise OutputValidationError("revise 决定必须提供 feedback")
    if decision == "reject" and not failed:
        raise OutputValidationError("decision=reject 时至少一个检查项必须失败")


def soften_unreasoned_reject(payload: dict) -> tuple[dict, str | None]:
    """无理由的 reject 不当否决：降为 approve，返回 (改后的 payload, 说明)。

    为什么（2026-09-18 实测）：审核把"摘录未覆盖"误读成捏造 → revise → 返工没改 →
    二轮 reject → 整线降级成拼接文本（内容反而更差）。reject 的替代品是**整篇降级**，
    代价远大于保留一版有问题的草稿；所以只有**写明具体理由**（某个失败检查项的
    findings 非空）的 reject 才生效，其余按 approve 处理并记 `reject_downgraded`。

    说明为 None 表示 payload 未改动（非 reject，或有理由的 reject）。
    """
    if str(payload.get("decision") or "").strip().lower() != "reject":
        return payload, None
    reasons: list[str] = []
    for key, value in payload.items():
        if not isinstance(value, dict) or "status" not in value:
            continue
        if str(value.get("status")).strip().lower() != "fail":
            continue
        findings = value.get("findings") or []
        if isinstance(findings, list) and any(str(f).strip() for f in findings):
            reasons.append(f"{key}: {str(findings[0]).strip()[:80]}")
    if reasons:
        return payload, None
    softened = dict(payload)
    softened["decision"] = "approve"
    softened["reject_downgraded"] = True
    # approve 的语义要求 feedback 为空（validate_supervisor_semantics）
    softened["feedback"] = []
    return softened, "reject 未写具体理由（失败检查项的 findings 为空）→ 按 approve 处理"


def soften_unsubstantial_revise(payload: dict) -> tuple[dict, str | None]:
    """无实质检查项失败的 revise 快速放行：降为 approve，避免无效返工重跑。

    审核的核心维度（facts_check、perspective_check、consistency_check 等）
    全部为 pass 时，草稿事实与结构已达到上线质量标准。此时若 decision 仍为 revise，
    多属无硬伤的形式建议（如语气修饰、段落微差、字数微调），整篇重走 Agent 返工
    （单次 35 秒延迟 + 额外 token 开销）不仅收益极低，且易诱发幻觉漂移。
    因此对此类 revise 降为 approve，原 feedback 归档为 advisory_feedback。
    """
    if str(payload.get("decision") or "").strip().lower() != "revise":
        return payload, None
    failed_checks: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict) and "status" in value:
            if str(value.get("status")).strip().lower() == "fail":
                failed_checks.append(key)
    if failed_checks:
        return payload, None
    softened = dict(payload)
    softened["decision"] = "approve"
    softened["revise_downgraded"] = True
    softened["advisory_feedback"] = list(payload.get("feedback") or [])
    softened["feedback"] = []
    return softened, "revise 无失败检查项（全部检查项均为 pass）→ 快速放行按 approve 处理"


# ── 统一入口 ──────────────────────────────────────────────────
def validate_payload(response_model: type[T], data: dict) -> T:
    """严格校验模型输出并返回实例。

    分发逻辑：每个模型类自带 validate(data) 类方法，
    这里只做一次 hasattr 检查然后委托过去。
    """
    if not hasattr(response_model, "validate"):
        raise OutputValidationError(
            f"{response_model.__name__} 没有实现 validate 类方法"
        )
    return response_model.validate(data)
