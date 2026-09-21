"""会议/笔记画像分类：客观全员、真人、职业模板。

职业模板（``*.json``）与客观画像一起平铺在跨域公共目录
``perspective/profiles/``（文件名不含 ``_profile`` 后缀）；
域名下仍可保留自己的客观/真人画像（``samples/{domain}/profile/``）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 跨域公共画像目录：客观画像与职业模板平铺在同一目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_PROFILE_DIR = PROJECT_ROOT / "perspective" / "profiles"

KIND_OBJECTIVE = "objective"
KIND_PERSON = "person"
KIND_ROLE = "role_template"

KIND_LABEL = {
    KIND_OBJECTIVE: "客观",
    KIND_PERSON: "真人",
    KIND_ROLE: "职业",
}

# 用户自建真人档案：``data/{X-User-Id}/user.json``（不改仓库；``extra.profile=user`` 时读取）
USER_PROFILE_FILENAME = "user.json"
# extra.profile 里强制客观/强制真人的取值（与「空值自动选档」区分开）
_OBJECTIVE_ALIASES = frozenset({"objective", "object"})
_USER_ALIAS = "user"


def _role_template_candidates(profile_dir: Path, key: str) -> list[Path]:
    """职业模板候选：先同目录（domain 自带的模板优先），再公共 profiles 目录。"""
    return [
        profile_dir / f"{key}.json",
        SHARED_PROFILE_DIR / f"{key}.json",
    ]


def classify_profile(data: dict[str, Any] | None) -> str:
    blob = data or {}
    if str(blob.get("perspective") or "").strip().lower() == KIND_OBJECTIVE:
        return KIND_OBJECTIVE
    if str(blob.get("persona_type") or "").strip().lower() == KIND_ROLE:
        return KIND_ROLE
    return KIND_PERSON


def resolve_role_template(data: dict[str, Any], profile_dir: Path) -> dict[str, Any]:
    """真人画像引用职业模板：返回合并后的 dict（真人字段覆盖模板字段）。

    - ``data["role_template"]`` 指定模板名（如 "developer" → 公共目录 ``perspective/profiles/developer.json``）
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
    path = next((p for p in _role_template_candidates(profile_dir, key) if p.is_file()), None)
    if path is None:
        raise ValueError(
            f"role_template 指向的画像不存在：{key}"
            f"（在 {profile_dir} 或公共目录 {SHARED_PROFILE_DIR} 下查找 {key}.json）"
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
        name = Path(filename).stem or "未命名"
    role = str(data.get("role") or "").strip()
    # 真人引用职业模板且未自写 role 时，用模板的 role 展示（如「真人 · 姓名（职业）」）
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


def filter_identity_fields(data: dict[str, Any], identity_cls: type) -> dict[str, Any]:
    allowed = {item.name for item in fields(identity_cls)}
    return {key: value for key, value in (data or {}).items() if key in allowed}


# ── 用户自建真人档案 user.json ──────────────────────────────────
# 打通方式：用户把档案放在自己的数据目录 data/{X-User-Id}/user.json，
# **``extra.profile`` 传 ``user`` 才注入**。2026-09-21 改口径：以前"传空即自动发现"，
# 结果是"放了个文件就悄悄换档"——调用方拿不到稳定默认，事后也说不清某次输出是按哪个
# 视角跑的。现在传空一律走默认档（客观全员），纪要线再由 template 留空自动套「通用纪要」。


def user_profile_path(user_id: str, project_root: Path | None = None) -> Path:
    """``data/{safe_id(user_id)}/user.json``；user_id 为空返回空 Path。

    目录段与记忆/产物同源（``safe_id``），杜绝 ``../`` 之类的路径穿越。
    """
    if not str(user_id or "").strip():
        return Path("")
    from tools.memory.store import safe_id

    root = project_root or PROJECT_ROOT
    return root / "data" / safe_id(user_id) / USER_PROFILE_FILENAME


def read_user_profile(path: Path) -> dict[str, Any] | None:
    """读 user.json：必须是 JSON 对象且 ``name`` 非空，否则当"没有档案"（记一条 warning）。

    为什么要 name：没有姓名就无法按人点名，后续命中表/裁剪全落空——
    与其带着半残档案跑，不如退回客观。
    """
    if not path or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("user.json 读取失败，按无档案处理：%s", path)
        return None
    if not isinstance(data, dict):
        logger.warning("user.json 必须是 JSON 对象，按无档案处理：%s", path)
        return None
    if not str(data.get("name") or "").strip():
        logger.warning("user.json 缺少 name，按无档案处理：%s", path)
        return None
    return data


def sanitize_user_profile(data: dict[str, Any]) -> dict[str, Any]:
    """user.json 专属清洗：``perspective`` 一律忽略（有档案就是真人）、``persona_type`` 强制置空。

    只能在 user.json 这一侧做：职业文件正是靠 ``persona_type=role_template``
    才被认成职业模板（``classify_profile``），客观文件靠 ``perspective=objective``；
    统一清洗会把它们改坏。persona_type 若留着用户误写的 role_template，
    姓名会被当成职业通称（prompt 第三类画像的判定依据）。
    """
    out = dict(data or {})
    out.pop("perspective", None)
    out["persona_type"] = None
    return out


def is_user_profile_file(path: Path | None) -> bool:
    """该画像文件是否来自 user.json（只有 ``extra.profile=user`` 这一档会指向它）。"""
    return bool(path) and Path(path).name == USER_PROFILE_FILENAME


def _objective_path(domain: str, project_root: Path) -> Path:
    """客观全员画像：域名 samples 优先，否则公共 object.json。"""
    root = project_root or PROJECT_ROOT
    domain_obj = root / "samples" / domain / "profile" / "object_profile.json"
    if domain_obj.is_file():
        return domain_obj
    shared_obj = root / "perspective" / "profiles" / "object.json"
    return shared_obj if shared_obj.is_file() else Path("")


def resolve_profile_file(
    profile_value: str,
    *,
    domain: str,
    user_id: str = "",
    project_root: Path | None = None,
) -> Path:
    """``extra.profile`` → 画像文件路径（API 与 CLI 共用的唯一入口）。

    | extra.profile | 行为 |
    |---|---|
    | ``""``（空） | **默认档：客观全员**（不读 user.json；纪要线再由 template 留空套「通用纪要」） |
    | ``"user"`` | 真人档案 ``data/{uid}/user.json``（缺失/非法 → 空 Path，由调用方 400） |
    | ``"objective"`` / ``"object"`` | 客观全员（与空值同档，留作显式表达） |
    | 职业模板名 | 该职业模板（``perspective/profiles/{名}.json``），忽略 user.json |

    返回空 Path 表示"取值非法"，调用方负责报 400。
    """
    name = str(profile_value or "").strip()
    root = project_root or PROJECT_ROOT
    if not name:
        return _objective_path(domain, root)
    if name == _USER_ALIAS:
        user_path = user_profile_path(user_id, root)
        return user_path if read_user_profile(user_path) is not None else Path("")
    if name.lower() in _OBJECTIVE_ALIASES:
        return _objective_path(domain, root)
    # 职业模板：只读共享/域内 profiles，不碰 user.json
    candidate = SHARED_PROFILE_DIR / f"{name}.json"
    return candidate if candidate.is_file() else Path("")


__all__ = [
    "KIND_OBJECTIVE",
    "KIND_PERSON",
    "KIND_ROLE",
    "SHARED_PROFILE_DIR",
    "USER_PROFILE_FILENAME",
    "classify_profile",
    "filter_identity_fields",
    "is_user_profile_file",
    "list_profile_entries",
    "profile_choice_label",
    "read_user_profile",
    "resolve_profile_file",
    "resolve_role_template",
    "sanitize_user_profile",
    "user_profile_path",
]
