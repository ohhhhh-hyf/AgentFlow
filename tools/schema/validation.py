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
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise OutputValidationError(f"{path} 必须是字符串数组")


def _choice(value: object, choices: set, path: str) -> None:
    if value not in choices:
        raise OutputValidationError(f"{path} 必须是 {sorted(choices)} 之一")


def _review_check(value: dict, path: str) -> None:
    _exact_fields(value, {"status", "findings"}, path)
    _choice(value["status"], {"pass", "fail"}, f"{path}.status")
    _string_list(value["findings"], f"{path}.findings")


def _action(item: dict, path: str) -> None:
    expected = {
        "task", "owner", "deadline", "priority",
        "status", "evidence", "confidence",
    }
    _exact_fields(item, expected, path)
    _string(item["task"], f"{path}.task")
    _string(item["owner"], f"{path}.owner", nullable=True)
    _string(item["deadline"], f"{path}.deadline", nullable=True)
    _choice(item["priority"], {"high", "medium", "low"}, f"{path}.priority")
    _choice(item["status"], {"explicit", "inferred"}, f"{path}.status")
    _string(item["evidence"], f"{path}.evidence")
    _choice(item["confidence"], {"high", "medium", "low"}, f"{path}.confidence")


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
