"""用户画像档案：``data/{user_id}/profile/{user_id}.json``。

以用户 ID 为唯一隔离粒度，自动维护用户的身份视角画像：
- 新建用户时自动在 ``data/{user_id}/profile/{user_id}.json`` 创建画像
- 自动提取或关联职业角色（开发/测试/算法/产品/项目/客户经理等），未识别或未指定时默认关联客观全员视角
- 画像文件继承职业模板的所有配置属性并与用户偏好融合，直接作为各类任务执行时的完整 Profile 供给源。
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

ROLE_TEMPLATE_MAP: dict[str, dict[str, Any]] = {
    "tester": {
        "name": "测试工程师",
        "label": "职业 · 测试工程师",
        "file": "role/tester_profile.json",
        "keywords": [
            "测试", "测试工程师", "qa", "质量保障", "自动化测试", "测试人员", "做测试", "做测试的",
            "测开", "测试开发", "软件测试", "测试组", "测试同学", "点点点", "测试管理"
        ],
    },
    "algorithm_engineer": {
        "name": "算法工程师",
        "label": "职业 · 算法工程师",
        "file": "role/algorithm_engineer_profile.json",
        "keywords": [
            "算法", "算法工程师", "ai", "机器学习", "深度学习", "大模型", "大模型算法", "nlp", "cv",
            "做算法", "做算法的", "模型工程师", "算法研究员"
        ],
    },
    "product_manager": {
        "name": "产品经理",
        "label": "职业 · 产品经理",
        "file": "role/product_manager_profile.json",
        "keywords": [
            "产品", "产品经理", "产品策划", "pm", "需求", "产品总监", "做产品", "做产品的", "产品专家", "产品顾问"
        ],
    },
    "project_manager": {
        "name": "项目经理",
        "label": "职业 · 项目经理",
        "file": "role/project_manager_profile.json",
        "keywords": [
            "项目经理", "项目管理", "pmp", "scrum", "敏捷教练", "推进", "项目负责人", "做项目", "做项目的", "项目总监", "项目主管"
        ],
    },
    "client_manager": {
        "name": "客户经理",
        "label": "职业 · 客户经理",
        "file": "role/client_manager_profile.json",
        "keywords": [
            "客户经理", "业务经理", "商务经理", "客户管理", "商务", "销售", "bd", "客户代表",
            "做销售", "做销售的", "做商务", "做商务的", "业务代表", "大客户经理"
        ],
    },
    "developer": {
        "name": "开发人员",
        "label": "职业 · 开发人员",
        "file": "role/developer_profile.json",
        "keywords": [
            "开发", "研发", "程序员", "前端", "后端", "全栈", "代码", "软件工程师", "架构师",
            "技术人员", "developer", "dev", "写代码", "写代码的", "做开发", "做开发的",
            "做研发", "做研发的", "做技术", "做技术的", "码农", "开发人员", "开发工程师", "研发工程师"
        ],
    },
    "object": {
        "name": "客观全员",
        "label": "客观 · 客观全员",
        "file": "object_profile.json",
        "keywords": ["客观", "全员", "客观视角", "全员视角", "通用", "中立", "客观全员"],
    },
}


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


def detect_role_from_text(text: str) -> tuple[str, str, str] | None:
    """从用户输入或自述中识别职业/视角画像。未识别出则返回 None。"""
    if not text or not text.strip():
        return None
    t = text.lower()

    # 按明确的优先级匹配关键词
    priority_keys = ["tester", "algorithm_engineer", "product_manager", "project_manager", "client_manager", "developer"]
    for key in priority_keys:
        info = ROLE_TEMPLATE_MAP[key]
        for kw in info["keywords"]:
            if kw.lower() in t:
                return key, info["name"], info["label"]
    return None


def match_role_template(role_text: str) -> tuple[str, str, str]:
    """匹配角色文本到职业模板。返回 (template_key, role_name, template_label)。

    若无匹配项或为空，一律默认回退到客观视角 ("object", "客观全员", "客观 · 客观全员")。
    """
    text = str(role_text or "").strip().lower()
    if not text:
        return "object", "客观全员", "客观 · 客观全员"

    # 先做直接 key 匹配
    if text in ROLE_TEMPLATE_MAP:
        info = ROLE_TEMPLATE_MAP[text]
        return text, info["name"], info["label"]

    for key, info in ROLE_TEMPLATE_MAP.items():
        if key == "object":
            continue
        if text == info["name"].lower() or text in info["label"].lower():
            return key, info["name"], info["label"]

    detected = detect_role_from_text(text)
    if detected:
        return detected

    return "object", "客观全员", "客观 · 客观全员"


def ensure_profile(project_root: Path, user_id: str, role: str = "") -> dict[str, Any]:
    """确保画像文件存在：在 data/{uid}/profile/{uid}.json 下新建/更新。

    新建时默认关联客观视角；识别或传入特定角色时关联对应已有职业。
    写入完整且自包含的画像 JSON，供任务执行直接作为 profile 读取。
    """
    from tools.memory.store import safe_id

    uid = safe_id(user_id or "default")
    existing = load_profile(project_root, uid)

    if existing is None:
        tpl_key, r_name, t_label = match_role_template(role)
        existing = {
            "user_id": uid,
            "name": "",
            "role": r_name,
            "base_template": tpl_key,
            "template_label": t_label,
            "traits": {},
            "facts": [],
            "updated_at": _now_stamp(),
        }
    else:
        existing["user_id"] = uid
        cur_role = role or existing.get("role") or ""
        tpl_key, r_name, t_label = match_role_template(cur_role)
        if not existing.get("base_template"):
            existing["base_template"] = tpl_key
            existing["role"] = r_name
            existing["template_label"] = t_label
        elif not existing.get("template_label"):
            existing["template_label"] = ROLE_TEMPLATE_MAP.get(existing["base_template"], {}).get("label", t_label)

    full_data = resolve_user_profile(project_root, uid, user_data=existing)
    save_profile(project_root, uid, full_data)
    return full_data


# ── 消费与解析：读取（含职业模板基底合并）─────────────────

def save_custom_role_profile(
    project_root: Path,
    user_id: str,
    role_name: str,
    department: str = "",
    responsibilities: list[str] | None = None,
    focus_areas: list[str] | None = None,
    output_style: str = "",
    traits: dict[str, str] | None = None,
) -> dict[str, Any]:
    """创建并保存用户自定义职业到 data/<uid>/profile/role.json，并更新关联至 user.json。"""
    from tools.memory.store import safe_id

    uid = safe_id(user_id or "default")
    profile_dir = project_root / "data" / uid / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    role_path = profile_dir / "role.json"

    r_name = (role_name or "").strip() or "自定义职业"
    dept = (department or "").strip()
    style = (output_style or "").strip() or f"{r_name}视角：突出本岗位关注的核心议题、待办分工与风险阻塞；条理清晰，结论先行"

    # 构造标准规范的职业 JSON 结构（必要核心字段齐全）
    custom_role_data = {
        "name": r_name,
        "role": f"{r_name}与专项视角记录者",
        "department": dept or "业务协同部",
        "perspective": "personal",
        "persona_type": "custom_role",
        "scope": f"{r_name}在会议中的覆盖范围：与{r_name}相关的决策、方案、排期与风险控制",
        "responsibilities": responsibilities or [
            f"从{r_name}专业视角理解会议需求与技术方案",
            f"跟进与{r_name}相关的关键待办与执行细节",
            "评估潜在风险与阻塞，确保交付质量",
        ],
        "interests": [
            f"{r_name}关注的核心目标与边界",
            "具体执行分工与节点排期",
            "跨部门协同与依赖项",
            "潜在风险与应对预案",
        ],
        "principles": [
            "忠实原文：客观事实与专业判断分开记录",
            "重点突出：突出本岗位相关的关键交付项",
            "风险显式：显式记录依赖与阻塞",
        ],
        "focus_areas": focus_areas or [
            f"{r_name}核心职责与行动项",
            "排期里程碑与进度约束",
            "跨角色依赖与外部协作",
            "风险与阻塞应对",
        ],
        "constraints": [
            "不臆造原文未提及的结论",
            "不遗漏影响交付的关键依赖",
        ],
        "values": [
            "专业性：聚焦岗位核心价值",
            "落地性：方案与行动项可落地",
        ],
        "output_style": style,
        "context": f"以{r_name}个人视角处理会议内容：优先保留与{r_name}职责、方案、任务排期、依赖与风险相关的内容；明确相关行动项与责任人；纯非相关行政细节可适度精简。",
    }

    role_path.write_text(json.dumps(custom_role_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新并关联 uid.json
    existing = load_profile(project_root, uid) or {}
    existing["user_id"] = uid
    existing["role"] = r_name
    existing["base_template"] = "custom_role"
    existing["template_label"] = f"职业 · {r_name}"
    existing["role_file"] = "role.json"
    if traits:
        cur_traits = dict(existing.get("traits") or {})
        cur_traits.update({k: v for k, v in traits.items() if v})
        existing["traits"] = cur_traits
    existing["updated_at"] = _now_stamp()

    full_data = resolve_user_profile(project_root, uid, user_data=existing)
    save_profile(project_root, uid, full_data)
    return full_data


def resolve_user_profile(project_root: Path, user_id: str, user_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """读取用户画像，以关联的职业模板/客观视角或同目录下的 role.json 为基底，用户自定义字段覆盖，生成完整 Profile。"""
    from tools.core.profiles import SHARED_PROFILE_DIR

    data = user_data if user_data is not None else (load_profile(project_root, user_id) or {})
    base = str(data.get("base_template") or "object").strip()

    base_template_data: dict[str, Any] = {}

    # 1. 优先尝试读取同目录下的 role.json
    role_path = profile_path(project_root, user_id).parent / "role.json"
    if role_path.is_file():
        try:
            base_template_data = json.loads(role_path.read_text(encoding="utf-8"))
        except Exception:
            base_template_data = {}

    # 2. 若无 role.json，回退到共享模板库
    if not base_template_data:
        template_info = ROLE_TEMPLATE_MAP.get(base) or ROLE_TEMPLATE_MAP["object"]
        template_file = SHARED_PROFILE_DIR / template_info["file"]
        if template_file.is_file():
            try:
                base_template_data = json.loads(template_file.read_text(encoding="utf-8"))
            except Exception:
                base_template_data = {}

    merged = dict(base_template_data)
    # 保留模板基底，用户显式非空字段覆盖
    merged.update({k: v for k, v in data.items() if v not in (None, "")})
    merged["user_id"] = user_id
    merged["base_template"] = base
    # name 字段严格为用户填写的真实姓名；若未填写则保持为空字符串，不从职业模板继承（没有就是没有）
    merged["name"] = str(data.get("name") or "").strip()
    if not merged.get("template_label"):
        template_info = ROLE_TEMPLATE_MAP.get(base) or ROLE_TEMPLATE_MAP["object"]
        merged["template_label"] = template_info.get("label", f"职业 · {merged.get('role', '客观全员')}")
    if not merged.get("role") or merged.get("role") == "客观全员":
        if base != "object":
            template_info = ROLE_TEMPLATE_MAP.get(base) or ROLE_TEMPLATE_MAP["object"]
            merged["role"] = data.get("role") or template_info.get("name") or "客观全员"
    return merged


def resolve_user_profile_file(project_root: Path, user_id: str) -> Path:
    """确保并在磁盘生成/更新该用户的完整 Profile JSON 文件，返回文件绝对路径。"""
    ensure_profile(project_root, user_id)
    return profile_path(project_root, user_id)


def update_user_role(project_root: Path, user_id: str, role_or_template: str) -> dict[str, Any]:
    """手动或自动更新用户的关联职业，回填并刷新 user_id.json。"""
    return update_user_profile_data(project_root, user_id, role=role_or_template)


def update_user_profile_data(
    project_root: Path,
    user_id: str,
    role: str = "",
    traits: dict[str, str] | None = None,
    name: str = "",
) -> dict[str, Any]:
    """前端直接编辑或代码更新用户的完整画像字段（职业/base_template、偏好 traits、姓名），回填并刷盘。"""
    from tools.core.profiles import SHARED_PROFILE_DIR
    from tools.memory.store import safe_id

    uid = safe_id(user_id or "default")
    profile_dir = project_root / "data" / uid / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    existing = load_profile(project_root, uid) or {}
    existing["user_id"] = uid
    stamp = _now_stamp()

    if role:
        tpl_key, r_name, t_label = match_role_template(role)
        existing["role"] = r_name
        existing["base_template"] = tpl_key
        existing["template_label"] = t_label
        existing["role_file"] = "role.json"

        # 同步将选定职业的完整模板写入 data/<uid>/profile/role.json
        template_info = ROLE_TEMPLATE_MAP.get(tpl_key) or ROLE_TEMPLATE_MAP["object"]
        template_file = SHARED_PROFILE_DIR / template_info["file"]
        if template_file.is_file():
            try:
                (profile_dir / "role.json").write_text(template_file.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
    elif not existing.get("base_template"):
        tpl_key, r_name, t_label = match_role_template("object")
        existing["role"] = r_name
        existing["base_template"] = tpl_key
        existing["template_label"] = t_label

    if name:
        existing["name"] = name.strip()

    if traits is not None:
        cur_traits = dict(existing.get("traits") or {})
        for k, v in traits.items():
            k_clean = str(k).strip()
            v_clean = str(v).strip()
            if k_clean:
                if v_clean:
                    cur_traits[k_clean] = v_clean
                else:
                    cur_traits.pop(k_clean, None)
        existing["traits"] = cur_traits

    existing["updated_at"] = stamp

    facts = list(existing.get("facts") or [])
    if role:
        facts.append({"field": "role", "value": existing.get("role", ""), "updated_at": stamp})
    if name:
        facts.append({"field": "name", "value": name, "updated_at": stamp})
    existing["facts"] = facts[-PROFILE_FACTS_CAP:]

    full_data = resolve_user_profile(project_root, uid, user_data=existing)
    save_profile(project_root, uid, full_data)
    return full_data


# ── LLM 提取 ───────────────────────────────────────────────

CHAT_PROFILE_SYSTEM_PROMPT = """你是「用户画像提取器」。从用户的对话内容中，提取关于**用户本人**的信息。
只提取对话中明确出现、或能合理推断的信息；不确定的字段留空，不要臆造。

输出字段：
- name：用户姓名（对话中明确出现才填，否则空字符串）
- role：用户职业/角色/身份（如「开发人员」「测试工程师」「产品经理」「算法工程师」，未提及则空字符串）
- traits：用户的偏好、性格、做事风格，键必须限定为「做事风格」「沟通偏好」「性格」之一，没有则空对象

注意：提取的是「用户是谁、是什么样的人」，不是对话主题或项目内容。"""

CHAT_PROFILE_OUTPUT_CONTRACT = """{
  "name": "",
  "role": "",
  "traits": {}
}"""


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
        tpl_key, r_name, t_label = match_role_template(role)
        out["role"] = r_name
        out["base_template"] = tpl_key
        out["template_label"] = t_label

    cur_traits = dict(out.get("traits") or {})
    for k, v in traits.items():
        if cur_traits.get(k) != v:
            cur_traits[k] = v
    if cur_traits:
        out["traits"] = cur_traits

    facts = list(out.get("facts") or [])
    if name or role:
        for field_name, value in (("name", name), ("role", out.get("role", ""))):
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
    """完整更新流程：ensure → 提取（最近用户消息）→ 合并 → 落盘。"""
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
        full_data = resolve_user_profile(project_root, user_id, user_data=merged)
        save_profile(project_root, user_id, full_data)
        return full_data
    except Exception as exc:  # noqa: BLE001 - 画像更新失败不阻断聊天
        logger.warning("用户画像更新失败，本次跳过", exc_info=True)
        return None


__all__ = [
    "CHAT_PROFILE_OUTPUT_CONTRACT",
    "CHAT_PROFILE_SYSTEM_PROMPT",
    "ChatProfileUpdate",
    "ROLE_TEMPLATE_MAP",
    "TRAIT_KEYS",
    "ensure_profile",
    "extract_profile_update",
    "load_profile",
    "match_role_template",
    "merge_profile",
    "profile_path",
    "resolve_user_profile",
    "resolve_user_profile_file",
    "save_profile",
    "update_profile_from_chat",
    "update_user_role",
]
