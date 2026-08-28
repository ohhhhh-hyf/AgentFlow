"""API 层共享配置：项目根、.env、模板注册表、视角注册表、领域上下文。

模板权威来源 cm_template_v2_changed_0722.yaml；视角来自 perspective/profiles/。
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_TEMPLATE_YAML = PROJECT_ROOT / "cm_template_v2_changed_0722.yaml"


def load_env() -> None:
    from client.config import load_env as _load_env

    _load_env(PROJECT_ROOT / ".env")


def load_domain(name: str):
    from tools.runtime_context import load_domain as _load_domain

    return _load_domain(name, PROJECT_ROOT)


# ── 模板注册表（8 场景 29 类）────────────────────────────────

# 场景 ID → 中文名（template/ 目录兜底时用；yaml 存在时以 yaml 为准）
SCENARIO_NAMES = {
    "meeting_minutes": "会议",
    "study_notes": "学习",
    "dialogue_interview": "访谈",
    "job_interview": "面试",
    "medical_consultation": "医疗问诊",
    "legal_consultation": "法律沟通",
    "press_conference": "新闻发布",
    "daily_journal": "日常记录",
}

TEMPLATE_DIR = PROJECT_ROOT / "template"


def _template_registry_from_dir() -> dict[str, dict[str, object]]:
    """兜底数据源：yaml 缺失时，从 template/ 目录重建注册表。

    - 模板中文名/场景/key 从 template/README.md 注册表解析；
    - format 从 template/{模板ID}.md 读取（该 md 即 yaml format 的可读副本）。
    """
    readme = TEMPLATE_DIR / "README.md"
    if not readme.is_file():
        return {}
    text = readme.read_text(encoding="utf-8")
    out: dict[str, dict[str, object]] = {}
    row_re = re.compile(
        r"\|\s*\d+\s*\|\s*([a-z_]+)\s*\|\s*([a-z_]+)\s*\|\s*([^|]+?)\s*\|\s*[^|]*?\s*\|\s*`([a-z_]+)`\s*\|"
    )
    for m in row_re.finditer(text):
        scenario_id, template_id, name, key = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
        md_path = TEMPLATE_DIR / f"{template_id}.md"
        if not md_path.is_file():
            continue
        fmt = md_path.read_text(encoding="utf-8").strip()
        if not fmt:
            continue
        out[key] = {
            "format": fmt,
            "name": name,
            "scenario": SCENARIO_NAMES.get(scenario_id, scenario_id),
        }
    return out


def template_registry() -> dict[str, dict[str, object]]:
    """返回 {template_value: {"format": str, "name": str, "scenario": str}}。

    优先权威源 cm_template_v2_changed_0722.yaml；yaml 缺失/解析失败时
    回退 template/ 目录（md format + README 注册表），保证模板不依赖单个文件。
    """
    if _TEMPLATE_YAML.is_file():
        try:
            import yaml

            raw = yaml.safe_load(_TEMPLATE_YAML.read_text(encoding="utf-8"))
            root = (raw or {}).get("cm-template-v2") or {}
            scenarios = {
                s["id"].rsplit(".", 1)[-1]: s["name"] for s in root.get("scenarios") or []
            }
            out: dict[str, dict[str, object]] = {}
            for tpl in root.get("templates") or []:
                if not tpl.get("visible", True):
                    continue
                # yaml 中 id 用连字符且带 ${...} 包装（如 ${...meeting-minutes.team-meeting}），
                # 取末段后去尾 }、连字符转下划线，与契约 {场景ID}_{模板ID} 对齐
                scenario_id = str(tpl.get("scenario-id") or "").rsplit(".", 1)[-1].rstrip("}").replace("-", "_")
                template_id = str(tpl.get("id") or "").rsplit(".", 1)[-1].rstrip("}").replace("-", "_")
                key = f"{scenario_id}_{template_id}"
                out[key] = {
                    "format": str(tpl.get("format") or "").strip(),
                    "name": str(tpl.get("name") or ""),
                    "scenario": scenarios.get(scenario_id, scenario_id),
                }
            return out
        except Exception:  # noqa: BLE001 - yaml 异常回退目录源
            pass
    return _template_registry_from_dir()


def resolve_template_format(template_value: str) -> str:
    """extra.template 值 → 模板 format 文本；非法值返回空串（调用方判 400）。"""
    if not (template_value or "").strip():
        return ""
    return template_registry().get(template_value.strip(), {}).get("format") or ""


# ── 视角注册表（perspective/profiles 平铺）────────────────────

PROFILE_DIR = PROJECT_ROOT / "perspective" / "profiles"


def profile_path(domain: str, profile_value: str) -> Path:
    """extra.profile 值 → 画像文件路径。

    空/缺省 → 默认客观全员（域名 samples 优先，否则公共 object.json）；
    否则查公共目录 {name}.json，不存在返回空 Path（调用方判 400）。
    """
    name = (profile_value or "").strip()
    if not name:
        domain_obj = PROJECT_ROOT / "samples" / domain / "profile" / "object_profile.json"
        if domain_obj.is_file():
            return domain_obj
        shared_obj = PROFILE_DIR / "object.json"
        if shared_obj.is_file():
            return shared_obj
        return Path("")
    candidate = PROFILE_DIR / f"{name}.json"
    return candidate if candidate.is_file() else Path("")


__all__ = [
    "PROFILE_DIR",
    "PROJECT_ROOT",
    "load_domain",
    "load_env",
    "profile_path",
    "resolve_template_format",
    "template_registry",
]
