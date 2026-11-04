"""用户画像选档、路径安全与合并清洗单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

from core.runner.profiles import (
    classify_profile,
    filter_identity_fields,
    is_user_profile_file,
    read_user_profile,
    resolve_profile_file,
    resolve_role_template,
    sanitize_user_profile,
    user_profile_path,
)


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _root(tmp: Path) -> Path:
    """搭一个最小工程根：公共画像目录 + data/{uid}/。"""
    profiles = tmp / "assets" / "profiles"
    _write(profiles / "object.json", {"name": "", "perspective": "objective"})
    _write(
        profiles / "developer.json",
        {
            "name": "开发人员",
            "role": "软件研发与系统实现工程师",
            "persona_type": "role_template",
            "perspective": "personal",
            "focus_areas": ["需求、验收标准与技术实现方案", "任务分工、排期与进度节点"],
            "responsibilities": ["理解需求并确认技术实现方案"],
            "constraints": ["不臆造技术可行性结论"],
        },
    )
    return tmp


USER_OK = {
    "name": "赵衡",
    "name_aliases": ["小赵", "赵工"],
    "role": "后端工程师",
    "role_template": "developer",
    "personality": "务实，讨厌含糊的截止日期",
    "preferences": ["先写我的待办和接口依赖"],
}


def test_user_profile_path_safety() -> None:
    root = Path("/repo")
    assert user_profile_path("1", root) == root / "data" / "1" / "user.json"
    assert user_profile_path("", root) == Path("")
    traversal = user_profile_path("../../etc", root)
    assert ".." not in traversal.parts
    assert traversal.parent.parent.name == "data"


def test_selection_matrix(tmp_path: Path) -> None:
    """extra.profile 选档：空=默认档（客观，不读 user.json）；user=真人；职业名/显式客观各自独立。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = root / "data" / "1" / "user.json"

    # ① 无档案 + 空值 → 客观
    obj = resolve_profile_file("", domain="meeting", user_id="1", project_root=root)
    assert obj.name == "object.json"

    # ② 有档案 + 空值 → 仍是客观（2026-09-21 改口径：真人要显式 profile=user）
    _write(ui, USER_OK)
    still_obj = resolve_profile_file("", domain="meeting", user_id="1", project_root=root)
    assert still_obj.name == "object.json"

    # ③ profile="user" → 真人档案
    assert resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == ui

    # ④ 显式客观（与空值同档）
    for value in ("objective", "object"):
        path = resolve_profile_file(value, domain="meeting", user_id="1", project_root=root)
        assert path.name == "object.json"

    # ⑤ 职业模板
    dev = resolve_profile_file("developer", domain="meeting", user_id="1", project_root=root)
    assert dev.name == "developer.json"

    # ⑥ 未知职业名 → 空 Path（调用方 400）
    assert resolve_profile_file("nope", domain="meeting", user_id="1", project_root=root) == Path("")

    # ⑦ 无档案时 profile=user → 空 Path（400），不静默降级
    ui.unlink()
    assert resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path("")
    assert resolve_profile_file("", domain="meeting", user_id="1", project_root=root).name == "object.json"

    # ⑧ 其它用户的档案互不可见（profile=user 只看自己那份）
    _write(root / "data" / "2" / "user.json", USER_OK)
    assert resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path("")
    assert (
        resolve_profile_file("user", domain="meeting", user_id="2", project_root=root)
        == root / "data" / "2" / "user.json"
    )


def test_broken_user_profile(tmp_path: Path) -> None:
    """坏档案（非对象 / 缺 name / 坏 JSON）→ 当没有档案，不阻断请求。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = root / "data" / "1" / "user.json"
    cases = {
        "缺 name": {"name_aliases": ["小赵"]},
        "name 全空白": {"name": "   "},
        "坏 JSON": "{not json",
        "不是对象": ["赵衡"],
    }
    for label, payload in cases.items():
        _write(ui, payload)
        assert read_user_profile(ui) is None
        assert resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path("")
        assert resolve_profile_file("", domain="meeting", user_id="1", project_root=root).name == "object.json"
    _write(ui, USER_OK)
    assert (read_user_profile(ui) or {}).get("name") == "赵衡"


def test_sanitize_and_merge(tmp_path: Path) -> None:
    """清洗 + 挂职业底：perspective 忽略、persona_type 置空、模板作底、真人字段覆盖。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = _write(root / "data" / "1" / "user.json", dict(USER_OK, perspective="objective", persona_type="role_template"))
    raw = read_user_profile(ui) or {}
    cleaned = sanitize_user_profile(raw)
    assert "perspective" not in cleaned
    assert cleaned.get("persona_type") is None

    merged = resolve_role_template(cleaned, ui.parent)
    assert merged.get("name") == "赵衡"
    assert bool(merged.get("focus_areas"))
    assert merged.get("persona_type") is None
    assert merged.get("role_template") == "developer"
    assert classify_profile(merged) == "person"

    # 自写字段整段替换（列表不拼接）
    cleaned2 = dict(cleaned, focus_areas=["接口契约与依赖"])
    merged2 = resolve_role_template(cleaned2, ui.parent)
    assert merged2.get("focus_areas") == ["接口契约与依赖"]

    # 职业文件本身不受清洗影响
    prof_dir = (root / "resources" / "profiles") if (root / "resources" / "profiles").is_dir() else (root / "assets" / "profiles")
    dev_raw = json.loads((prof_dir / "developer.json").read_text(encoding="utf-8"))
    assert classify_profile(resolve_role_template(dev_raw, prof_dir)) == "role_template"
    assert is_user_profile_file(ui) and not is_user_profile_file(prof_dir / "developer.json")

    from domains.meeting.models_base import UserIdentity as MeetingIdentity

    identity = MeetingIdentity(**filter_identity_fields(merged, MeetingIdentity))
    assert identity.name == "赵衡"
    assert identity.name_aliases == ["小赵", "赵工"]
    assert identity.personality == "务实，讨厌含糊的截止日期"
    assert identity.preferences == ["先写我的待办和接口依赖"]

    from core.graph.nodes import DomainNodes

    mode = DomainNodes._mode_label(
        {"user": identity.model_dump(), "objective_perspective": False}
    )
    assert mode == "personal"
    obj_identity = MeetingIdentity(**filter_identity_fields(
        json.loads((prof_dir / "object.json").read_text(encoding="utf-8")),
        MeetingIdentity,
    ))
    assert (
        DomainNodes._mode_label(
            {"user": obj_identity.model_dump(),
             "objective_perspective": obj_identity.perspective == "objective"}
        )
        == "objective"
    )
