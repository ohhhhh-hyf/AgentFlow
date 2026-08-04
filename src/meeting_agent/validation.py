from __future__ import annotations

from dataclasses import fields


class OutputValidationError(ValueError):
    pass


def _exact_fields(data, expected, path):
    if not isinstance(data, dict):
        raise OutputValidationError(f"{path} 必须是 JSON 对象")
    actual = set(data)
    expected = set(expected)
    if actual != expected:
        raise OutputValidationError(
            f"{path} 字段不一致：缺失={sorted(expected - actual)}，"
            f"多余={sorted(actual - expected)}"
        )


def _string(value, path, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str):
        raise OutputValidationError(f"{path} 必须是字符串")


def _string_list(value, path):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OutputValidationError(f"{path} 必须是字符串数组")


def _choice(value, choices, path):
    if value not in choices:
        raise OutputValidationError(f"{path} 必须是 {sorted(choices)} 之一")


def _review_check(value, path):
    _exact_fields(value, {"status", "findings"}, path)
    _choice(value["status"], {"pass", "fail"}, f"{path}.status")
    _string_list(value["findings"], f"{path}.findings")


def _action(item, path):
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


def validate_payload(response_model, data):
    """严格校验模型输出，不做字段丢弃、类型强转或事实补全。"""
    name = response_model.__name__
    # FinalReport.quality_warning 为系统可选字段，允许 LLM 不输出
    if name != "FinalReport":
        _exact_fields(data, [item.name for item in fields(response_model)], name)

    if name == "MeetingUnderstanding":
        _string(data["meeting_purpose"], "meeting_purpose")
        if not isinstance(data["topics"], list):
            raise OutputValidationError("topics 必须是对象数组")
        for index, topic in enumerate(data["topics"]):
            path = f"topics[{index}]"
            _exact_fields(
                topic,
                {"title", "discussion", "conclusion", "participants"},
                path,
            )
            _string(topic["title"], f"{path}.title")
            _string(topic["discussion"], f"{path}.discussion")
            _string(topic["conclusion"], f"{path}.conclusion", nullable=True)
            _string_list(topic["participants"], f"{path}.participants")
        for key in ("decisions", "open_questions", "risks"):
            _string_list(data[key], key)

    elif name == "PerspectiveProfile":
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        _string(data["name"], "name", nullable=True)
        _string(data["inferred_role"], "inferred_role", nullable=True)
        for key in (
            "responsibilities", "goals", "concerns",
            "relevant_topics", "evidence",
        ):
            _string_list(data[key], key)

    elif name == "PersonalizedMinutes":
        _string(data["headline"], "headline")
        for key in (
            "executive_summary", "key_decisions", "personally_relevant_points",
            "risks_and_blockers", "unresolved_questions",
        ):
            _string_list(data[key], key)

    elif name == "ActionItems":
        for key in ("my_actions", "delegated_actions", "unassigned_actions"):
            if not isinstance(data[key], list):
                raise OutputValidationError(f"{key} 必须是数组")
            for index, item in enumerate(data[key]):
                _action(item, f"{key}[{index}]")

    elif name == "SupervisorReview":
        decisions = {
            "approve", "revise_minutes", "revise_actions",
            "revise_both", "reject",
        }
        _choice(data["decision"], decisions, "decision")
        check_keys = (
            "facts_check", "perspective_check",
            "action_items_check", "consistency_check",
        )
        for key in check_keys:
            _review_check(data[key], key)
        _string_list(data["minutes_feedback"], "minutes_feedback")
        _string_list(data["actions_feedback"], "actions_feedback")

        failed = [
            key for key in check_keys
            if data[key]["status"] == "fail"
        ]
        if data["decision"] == "approve" and failed:
            raise OutputValidationError(
                f"decision=approve 时检查项不得失败：{failed}"
            )
        if data["decision"] == "approve" and (
            data["minutes_feedback"] or data["actions_feedback"]
        ):
            raise OutputValidationError("decision=approve 时返工意见必须为空")
        if data["decision"] in {"revise_minutes", "revise_both"} and not data[
            "minutes_feedback"
        ]:
            raise OutputValidationError("纪要返工决定必须提供 minutes_feedback")
        if data["decision"] in {"revise_actions", "revise_both"} and not data[
            "actions_feedback"
        ]:
            raise OutputValidationError("待办返工决定必须提供 actions_feedback")
        if data["decision"] == "reject" and not failed:
            raise OutputValidationError("decision=reject 时至少一个检查项必须失败")

    elif name == "FinalReport":
        # quality_warning 仅系统兜底时附加，不要求 LLM 输出
        allowed = {"title", "personalized_minutes", "action_items", "quality_warning"}
        required = {"title", "personalized_minutes", "action_items"}
        if not isinstance(data, dict):
            raise OutputValidationError("FinalReport 必须是 JSON 对象")
        actual = set(data)
        if not required.issubset(actual):
            raise OutputValidationError(
                f"FinalReport 字段不一致：缺失={sorted(required - actual)}"
            )
        extra = actual - allowed
        if extra:
            raise OutputValidationError(
                f"FinalReport 字段不一致：多余={sorted(extra)}"
            )
        _string(data["title"], "title")
        _string(data["personalized_minutes"], "personalized_minutes")
        if not isinstance(data["action_items"], list):
            raise OutputValidationError("action_items 必须是数组")
        for index, item in enumerate(data["action_items"]):
            _action(item, f"action_items[{index}]")
        if "quality_warning" in data and data["quality_warning"] is not None:
            _string(data["quality_warning"], "quality_warning")
        data = {
            "title": data["title"],
            "personalized_minutes": data["personalized_minutes"],
            "action_items": data["action_items"],
            "quality_warning": data.get("quality_warning"),
        }
    else:
        raise OutputValidationError(f"没有为 {name} 配置校验器")

    return response_model(**data)
