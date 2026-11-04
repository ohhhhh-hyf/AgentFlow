"""职业模板解析、角色同义词映射与继承测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runner.profiles import (
    load_role_mapping,
    read_user_profile,
    resolve_role_template,
    resolve_role_to_template_key,
    sanitize_user_profile,
)


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _root(tmp: Path) -> Path:
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


def test_missing_role_template(tmp_path: Path) -> None:
    """role_template 指向不存在的职业 → 明确报错（不静默降级成无底真人）。"""
    root = _root(tmp_path)
    ui = _write(root / "data" / "1" / "user.json", dict(USER_OK, role_template="nobody"))
    cleaned = sanitize_user_profile(read_user_profile(ui) or {})
    with pytest.raises(ValueError) as excinfo:
        resolve_role_template(cleaned, ui.parent)
    assert "nobody" in str(excinfo.value)

    # 名字写坏（含路径穿越）同样拒绝
    for bad in ("../developer", "a/b"):
        with pytest.raises(ValueError):
            resolve_role_template(dict(cleaned, role_template=bad), ui.parent)


def test_role_mapping() -> None:
    """验证 role 字段映射到已有的职业 profile（算法、开发、测试等）。"""
    mapping = load_role_mapping()
    assert bool(mapping) and len(mapping) > 10

    # 1. 算法工程师同义词与英文测试
    algorithm_aliases = ["算法", "算法人员", "算法工程师", "algorithm_engineer", "algorithm", "algo"]
    for alias in algorithm_aliases:
        mapped = resolve_role_to_template_key(alias)
        assert mapped == "algorithm_engineer"

    # 2. 其它常见职业映射
    assert resolve_role_to_template_key("开发") == "developer"
    assert resolve_role_to_template_key("测试工程师") == "tester"
    assert resolve_role_to_template_key("产品经理") == "product_manager"

    # 3. 未知职业返回 None（不报错）
    assert resolve_role_to_template_key("未知职业") is None

    # 4. resolve_role_template 真实合并验证
    raw_user = {
        "name": "申家坤",
        "name_aliases": ["小申", "申工"],
        "role": "算法工程师",
        "focus_person": ["徐玥", "张工", "李总"],
        "focus_thing": ["风控决策引擎", "端到端P99时延", "Q3交付排期"],
        "preferences": ["先写我的待办", "结论先行"],
    }
    merged = resolve_role_template(raw_user, Path("assets/profiles"))
    assert merged.get("role") == "算法工程师"
    assert merged.get("role_template") == "algorithm_engineer"
    assert len(merged.get("responsibilities", [])) >= 4
    assert len(merged.get("focus_areas", [])) >= 5
    assert merged.get("focus_person") == ["徐玥", "张工", "李总"]
    assert merged.get("focus_thing") == ["风控决策引擎", "端到端P99时延", "Q3交付排期"]
