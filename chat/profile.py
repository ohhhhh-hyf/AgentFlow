"""用户画像档案：``data/{user_id}/profile/{user_id}.json``。

从用户对话中持续提取"用户本人"的信息（姓名 / 职业角色 / 偏好性格），
累积成一份按用户隔离的画像，供 chat 与任务线复用。

数据模型（初期，后续可扩充）：:

    {
      "user_id": "1",
      "name": "侯业飞",
      "role": "开发人员",
      "base_template": "developer",   # 可选：匹配到的公共职业模板（perspective/profiles/role/）
      "traits": {"做事风格": "..."},  # 偏好/性格/做事风格
      "facts": [{"field": "role", "value": "开发人员", "updated_at": "..."}],
      "updated_at": "..."
    }

失败一律静默（记日志不抛）——画像提取不影响聊天主流程。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.validation import OutputValidationError, _exact_fields, _string

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 从最近 N 条用户消息提取画像（太长没必要，最近几轮足够）
PROFILE_EXTRACT_LAST = 6
# facts 最多保留条数
PROFILE_FACTS_CAP = 200
# traits 固定键集合（白名单：只保留这三类偏好）
TRAIT_KEYS = ("做事风格", "沟通偏好", "性格")


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 路径与读写 ─────────────────────────────────────────────

def profile_path(project_root: Path, user_id: str) -> Path:
    from tools.memory.store import safe_id

    uid = safe_id(user_id or "default")
    return project_root / "data" / uid / "profile" / f"{uid}.json"


def load_profile(project_root: Path, user_id: str) -> dict[str, Any] | None:
    """读取用户画像；缺文件/损坏返回 None。"""
    path = profile_path(project_root, user_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取用户画像失败：%s", exc)
        return None
    return data if isinstance(data, dict) else None


def save_profile(project_root: Path, user_id: str, data: dict[str, Any]) -> Path:
    path = profile_path(project_root, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ensure_profile(project_root: Path, user_id: str) -> dict[str, Any]:
    """确保画像文件存在：新建时写入 user_id 字段；已有则补缺失的 user_id。"""
    existing = load_profile(project_root, user_id)
    if existing is None:
        existing = {"user_id": user_id, "updated_at": _now_stamp()}
        save_profile(project_root, user_id, existing)
        return existing
    if not str(existing.get("user_id") or "").strip():
        existing["user_id"] = user_id
        existing["updated_at"] = _now_stamp()
        save_profile(project_root, user_id, existing)
    return existing


# ── LLM 提取 ───────────────────────────────────────────────

CHAT_PROFILE_SYSTEM_PROMPT = """你是「用户画像提取器」。从用户的对话内容中，提取关于**用户本人**的信息。
只提取对话中明确出现、或能合理推断的信息；不确定的字段留空，不要臆造。

输出字段：
- name：用户姓名（对话中明确出现才填，否则空字符串）
- role：用户职业/角色/身份（明确提到或可明确推断，如「开发人员」「高三学生」，否则空字符串）
- traits：用户的偏好、性格、做事风格，**键必须限定为以下三个之一**：「做事风格」「沟通偏好」「性格」；
  值是具体描述；仅当对话确实体现出该特质时才填，没有则空对象

注意：提取的是「用户是谁、是什么样的人」，不是对话主题或项目内容。"""

CHAT_PROFILE_OUTPUT_CONTRACT = """{
  "name": "",
  "role": "",
  "traits": {}
}
字段说明：
- name：用户姓名（明确出现才填，否则空字符串）
- role：用户职业/角色/身份（如「开发人员」「高三学生」）
- traits：键必须限定为「做事风格」「沟通偏好」「性格」之一，值为具体描述；没有则空对象"""


@dataclass
class ChatProfileUpdate:
    """从对话提取出的画像增量。"""

    name: str = ""
    role: str = ""
    traits: dict[str, str] = field(default_factory=dict)

    @classmethod
    def validate(cls, data: dict) -> "ChatProfileUpdate":
        _exact_fields(data, {"name", "role", "traits"}, cls.__name__)
        _string(data["name"], "name")
        _string(data["role"], "role")
        if not isinstance(data["traits"], dict):
            raise OutputValidationError("traits 必须是 JSON 对象")
        # 白名单：只保留 做事风格/沟通偏好/性格 三类键，其余丢弃
        traits = {}
        for key, value in data["traits"].items():
            key = str(key).strip()
            value = str(value).strip()
            if key in TRAIT_KEYS and value:
                traits[key] = value
        return cls(name=data["name"], role=data["role"], traits=traits)


async def extract_profile_update(client, user_texts: list[str]) -> ChatProfileUpdate | None:
    """调 LLM 从最近对话提取画像增量；失败返回 None。"""
    chat = "\n".join(f"- {t}" for t in user_texts if str(t).strip())
    if not chat.strip():
        return None
    try:
        return await client.structured(
            CHAT_PROFILE_SYSTEM_PROMPT,
            f"用户最近的对话内容：\n{chat}",
            ChatProfileUpdate,
            CHAT_PROFILE_OUTPUT_CONTRACT,
            temperature=0.0,
            label="chat/profile_extract",
        )
    except Exception as exc:  # noqa: BLE001 - 画像提取失败不阻断聊天
        logger.warning("画像提取失败，本次不更新", exc_info=True)
        return None


# ── 角色 → 公共职业模板匹配 ─────────────────────────────────

def match_role_template(role_text: str) -> str:
    """把提取到的角色文本匹配到 perspective/profiles/role/ 下的模板名。

    按模板的 name / role / 文件名做包含匹配；命中返回模板 key（如 "developer"），
    否则返回空串。找不到不算错（用户角色可能没有现成模板）。
    """
    role = str(role_text or "").strip()
    if not role:
        return ""
    from tools.profiles import SHARED_ROLE_DIR

    if not SHARED_ROLE_DIR.is_dir():
        return ""
    for path in sorted(SHARED_ROLE_DIR.glob("*_profile.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        name = str(data.get("name") or "").strip()
        tpl_role = str(data.get("role") or "").strip()
        key = path.stem.replace("_profile", "")
        if role == name or (name and (name in role or role in name)) or (
            tpl_role and role in tpl_role
        ):
            return key
    return ""


# ── 合并与落盘 ─────────────────────────────────────────────

def merge_profile(
    existing: dict[str, Any] | None,
    update: ChatProfileUpdate,
) -> dict[str, Any]:
    """把提取增量合并进已有画像（幂等：重复提取相同值不产生变化）。"""
    out = dict(existing or {})
    out.setdefault("user_id", "")
    stamp = _now_stamp()
    name = str(getattr(update, "name", "") or "").strip()
    role = str(getattr(update, "role", "") or "").strip()
    traits = dict(getattr(update, "traits", {}) or {})

    if name:
        out["name"] = name
    if role:
        out["role"] = role
        key = match_role_template(role)
        if key:
            out["base_template"] = key

    cur_traits = dict(out.get("traits") or {})
    changed = False
    for k, v in traits.items():
        if cur_traits.get(k) != v:
            cur_traits[k] = v
            changed = True
    if cur_traits:
        out["traits"] = cur_traits

    # facts：按 field+value 去重——同值只保留一条（刷新 updated_at），
    # 不同值追加（记录值变更史，如角色从"开发人员"变成"技术经理"）
    facts = list(out.get("facts") or [])
    if name or role:
        for field_name, value in (("name", name), ("role", role)):
            if not value:
                continue
            idx = next(
                (
                    i
                    for i, f in enumerate(facts)
                    if f.get("field") == field_name and f.get("value") == value
                ),
                None,
            )
            if idx is None:
                facts.append(
                    {"field": field_name, "value": value, "updated_at": stamp}
                )
            else:
                facts[idx]["updated_at"] = stamp
    if facts:
        out["facts"] = facts[-PROFILE_FACTS_CAP:]

    out["updated_at"] = stamp
    return out


async def update_profile_from_chat(
    project_root: Path,
    user_id: str,
    client,
    messages: list[dict[str, str]],
) -> dict[str, Any] | None:
    """完整更新流程：ensure → 提取（最近用户消息）→ 合并 → 落盘。

    任何失败静默返回 None，不影响聊天主流程。
    """
    try:
        existing = ensure_profile(project_root, user_id)
        user_texts = [
            str(m.get("content") or "")
            for m in (messages or [])
            if m.get("role") == "user"
        ]
        update = await extract_profile_update(client, user_texts[-PROFILE_EXTRACT_LAST:])
        if update is None:
            return existing
        merged = merge_profile(existing, update)
        save_profile(project_root, user_id, merged)
        return merged
    except Exception as exc:  # noqa: BLE001 - 画像更新失败不阻断聊天
        logger.warning("用户画像更新失败，本次跳过", exc_info=True)
        return None


# ── 消费：读取（含 base_template 合并）─────────────────────

def resolve_user_profile(project_root: Path, user_id: str) -> dict[str, Any]:
    """读取用户画像；若有 base_template，用公共职业模板做基底、用户字段覆盖。

    供 chat 头部注入 / 未来任务线加载使用。
    """
    data = load_profile(project_root, user_id) or {}
    base = str(data.get("base_template") or "").strip()
    if not base:
        return data
    from tools.profiles import SHARED_ROLE_DIR

    path = SHARED_ROLE_DIR / f"{base}_profile.json"
    if path.is_file():
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return data
        if isinstance(template, dict):
            merged = dict(template)
            merged.update({k: v for k, v in data.items() if v not in (None, "")})
            return merged
    return data


__all__ = [
    "CHAT_PROFILE_OUTPUT_CONTRACT",
    "CHAT_PROFILE_SYSTEM_PROMPT",
    "ChatProfileUpdate",
    "TRAIT_KEYS",
    "ensure_profile",
    "extract_profile_update",
    "load_profile",
    "match_role_template",
    "merge_profile",
    "profile_path",
    "resolve_user_profile",
    "save_profile",
    "update_profile_from_chat",
]
