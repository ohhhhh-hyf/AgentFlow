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

# 模板ID → 场景ID（yaml / README 都缺失时，仍能从 template/{id}.md 还原 API key）
TEMPLATE_SCENARIO = {
    "team_meeting": "meeting_minutes",
    "project_progress": "meeting_minutes",
    "decision_review": "meeting_minutes",
    "workshop_session": "meeting_minutes",
    "retrospective_session": "meeting_minutes",
    "exchange_forum": "meeting_minutes",
    "class_transcript": "study_notes",
    "special_lecture": "study_notes",
    "group_seminar": "study_notes",
    "knowledge_memo": "study_notes",
    "debate_forum": "study_notes",
    "research_dialogue": "dialogue_interview",
    "interview_transcript": "dialogue_interview",
    "hiring_report": "job_interview",
    "interview_debrief": "job_interview",
    "clinical_advisory": "medical_consultation",
    "psychological_session": "medical_consultation",
    "legal_advisory": "legal_consultation",
    "court_transcript": "legal_consultation",
    "contract_vetting": "legal_consultation",
    "media_briefing": "press_conference",
    "product_launch": "press_conference",
    "government_bulletin": "press_conference",
    "media_qa_session": "press_conference",
    "general_minutes": "daily_journal",
    "personal_memo": "daily_journal",
    "conversation_transcript": "daily_journal",
    "site_visit_tour": "daily_journal",
    "home_school_liaison": "daily_journal",
}


def _split_template_key(value: str) -> tuple[str, str] | None:
    """``meeting_minutes_project_progress`` → (meeting_minutes, project_progress)。"""
    raw = (value or "").strip()
    for sid in sorted(SCENARIO_NAMES, key=len, reverse=True):
        prefix = f"{sid}_"
        if raw.startswith(prefix):
            tid = raw[len(prefix) :]
            if tid:
                return sid, tid
    return None


def _read_template_md(template_id: str) -> str:
    path = TEMPLATE_DIR / f"{template_id}.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _template_registry_from_dir() -> dict[str, dict[str, object]]:
    """兜底数据源：yaml 缺失时，从 template/ 目录重建注册表。

    优先读 template/README.md；没有 README 时按 TEMPLATE_SCENARIO + ``{id}.md`` 扫描。
    """
    out: dict[str, dict[str, object]] = {}
    readme = TEMPLATE_DIR / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        row_re = re.compile(
            r"\|\s*\d+\s*\|\s*([a-z_]+)\s*\|\s*([a-z_]+)\s*\|\s*([^|]+?)\s*\|\s*[^|]*?\s*\|\s*`([a-z_]+)`\s*\|"
        )
        for m in row_re.finditer(text):
            scenario_id, template_id, name, key = (
                m.group(1),
                m.group(2),
                m.group(3).strip(),
                m.group(4),
            )
            fmt = _read_template_md(template_id)
            if not fmt:
                continue
            out[key] = {
                "format": fmt,
                "name": name,
                "scenario": SCENARIO_NAMES.get(scenario_id, scenario_id),
            }
        if out:
            return out
    if not TEMPLATE_DIR.is_dir():
        return {}
    for md_path in sorted(TEMPLATE_DIR.glob("*.md")):
        if md_path.stem.lower() == "readme":
            continue
        template_id = md_path.stem
        scenario_id = TEMPLATE_SCENARIO.get(template_id)
        if not scenario_id:
            continue
        fmt = md_path.read_text(encoding="utf-8").strip()
        if not fmt:
            continue
        key = f"{scenario_id}_{template_id}"
        out[key] = {
            "format": fmt,
            "name": template_id,
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
                    "requirement": str(tpl.get("requirement") or "").strip(),
                    "description": str(tpl.get("description") or "").strip(),
                }
            if out:
                return out
        except Exception:  # noqa: BLE001 - yaml 异常回退目录源
            pass
    return _template_registry_from_dir()


def resolve_template_format(template_value: str) -> str:
    """extra.template 值 → 模板 format 文本（含写作要求注释）；非法值返回空串。"""
    value = (template_value or "").strip()
    if not value:
        return ""
    item = template_registry().get(value) or {}
    fmt = str(item.get("format") or "").strip()
    req = str(item.get("requirement") or "").strip()
    if not fmt:
        parts = _split_template_key(value)
        if parts:
            fmt = _read_template_md(parts[1])
    if not fmt:
        return ""
    from tools.template_router._base import wrap_template_requirement

    return wrap_template_requirement(fmt, req)


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
