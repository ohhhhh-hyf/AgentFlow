"""会议/笔记画像分类：客观全员、真人、职业模板。"""
from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path
from typing import Any

KIND_OBJECTIVE = "objective"
KIND_PERSON = "person"
KIND_ROLE = "role_template"

KIND_LABEL = {
    KIND_OBJECTIVE: "客观",
    KIND_PERSON: "真人",
    KIND_ROLE: "职业",
}


def classify_profile(data: dict[str, Any] | None) -> str:
    blob = data or {}
    if str(blob.get("perspective") or "").strip().lower() == KIND_OBJECTIVE:
        return KIND_OBJECTIVE
    if str(blob.get("persona_type") or "").strip().lower() == KIND_ROLE:
        return KIND_ROLE
    return KIND_PERSON


def resolve_role_template(data: dict[str, Any], profile_dir: Path) -> dict[str, Any]:
    """真人画像引用职业模板：返回合并后的 dict（真人字段覆盖模板字段）。

    - ``data["role_template"]`` 指定模板名（如 "developer" → ``{profile_dir}/developer_profile.json``）
    - 模板字段作基底，真人**显式写且值非 None** 的字段覆盖模板
    - 模板自身不允许再嵌套 ``role_template``（防递归）
    - 真人未显式写 ``persona_type`` 时重置为空（引用模板的真人仍是真人身份）
    - 找不到模板抛 ``ValueError``（名字写错应被明确指出）
    """
    key = str(data.get("role_template") or "").strip()
    if not key:
        return data
    # 安全：模板名只允许字母/数字/下划线/连字符，禁止路径穿越（../、绝对路径）
    if not re.fullmatch(r"[\w-]+", key):
        raise ValueError(
            f"role_template 只能由字母/数字/下划线/连字符组成：{key!r}"
        )
    candidates = [profile_dir / f"{key}_profile.json", profile_dir / f"{key}.json"]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise ValueError(
            f"role_template 指向的画像不存在：{key}"
            f"（在 {profile_dir} 下查找 {key}_profile.json 或 {key}.json）"
        )
    template = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise ValueError(f"职业模板必须是 JSON 对象：{path}")
    merged = dict(template)
    merged.pop("role_template", None)  # 防递归嵌套
    merged.update({k: v for k, v in (data or {}).items() if v is not None})
    # persona_type 一律以真人为准：显式写了（含 null）用真人的，没写则重置为真人身份
    merged["persona_type"] = (data or {}).get("persona_type")
    merged["role_template"] = key  # 保留引用来源，供追溯与显示
    return merged


def profile_choice_label(data: dict[str, Any], filename: str = "", profile_dir: Path | None = None) -> str:
    kind = classify_profile(data)
    prefix = KIND_LABEL[kind]
    if kind == KIND_OBJECTIVE:
        return f"{prefix} · 客观全员"
    name = str(data.get("name") or "").strip()
    if not name:
        name = Path(filename).stem.replace("_profile", "") or "未命名"
    role = str(data.get("role") or "").strip()
    # 真人引用职业模板且未自写 role 时，用模板的 role 展示（如「真人 · 张三（开发人员）」）
    if not role and profile_dir is not None:
        try:
            merged = resolve_role_template(data, profile_dir)
            role = str(merged.get("role") or "").strip()
        except ValueError:
            role = ""
    if kind == KIND_PERSON and role:
        return f"{prefix} · {name}（{role}）"
    return f"{prefix} · {name}"


def list_profile_entries(profile_dir: Path) -> list[dict[str, Any]]:
    if not profile_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(profile_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        entries.append(
            {
                "path": path,
                "filename": path.name,
                "data": data,
                "kind": classify_profile(data),
                "label": profile_choice_label(data, path.name, profile_dir),
            }
        )
    order = {KIND_OBJECTIVE: 0, KIND_PERSON: 1, KIND_ROLE: 2}
    entries.sort(key=lambda item: (order.get(item["kind"], 9), item["label"]))
    return entries


def profile_choices(profile_dir: Path) -> list[str]:
    return [item["label"] for item in list_profile_entries(profile_dir)]


def default_profile_label(profile_dir: Path) -> str:
    entries = list_profile_entries(profile_dir)
    for item in entries:
        if item["kind"] == KIND_OBJECTIVE:
            return item["label"]
    return entries[0]["label"] if entries else "客观 · 客观全员"


def resolve_profile_entry(profile_dir: Path, label: str) -> dict[str, Any] | None:
    entries = list_profile_entries(profile_dir)
    text = (label or "").strip()
    for item in entries:
        if item["label"] == text:
            return item
    for item in entries:
        if item["kind"] == KIND_OBJECTIVE:
            return item
    return entries[0] if entries else None


def filter_identity_fields(data: dict[str, Any], identity_cls: type) -> dict[str, Any]:
    allowed = {item.name for item in fields(identity_cls)}
    return {key: value for key, value in (data or {}).items() if key in allowed}


__all__ = [
    "KIND_OBJECTIVE",
    "KIND_PERSON",
    "KIND_ROLE",
    "classify_profile",
    "default_profile_label",
    "filter_identity_fields",
    "list_profile_entries",
    "profile_choice_label",
    "profile_choices",
    "resolve_profile_entry",
    "resolve_role_template",
]
