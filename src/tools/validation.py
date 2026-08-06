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
