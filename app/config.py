"""API 层共享配置：项目根、.env、模板注册表、视角注册表、领域上下文。

模板权威来源是 template/ 目录下的 md 文件（每个模板一个文件，运行时直接读）。
视角来自 assets/profiles/。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

logger = logging.getLogger(__name__)

# 模板源目录：统一固定为 template
DEFAULT_TEMPLATE_DIR = "template"
TEMPLATE_DIR = PROJECT_ROOT / DEFAULT_TEMPLATE_DIR

# 会议纪要线的默认模板：extra.template 留空时**自动套用「通用纪要」**（不再走无模板自由渲染）。
# 只对纪要线（meeting/minutes）生效；其它线留空仍表示"不套模板"。
# 为什么（2026-09-18 实测）：无模板纪要完全听模型的——栏目自定、无缺省词、无段落上限、
# 不跑模板门禁（同一份原文 6410 汉字、最长单行 515 字、超出篇幅上限 16% 无人管）。
DEFAULT_MINUTES_TEMPLATE = "general_minutes"

# 个人视角纪要线的默认模板：extra.profile="user" 且 extra.template 留空时固定套用个人视角纪要模板。
# 统一走专属 personal_minutes.md，不再支持历史通用模板剪裁模式。
DEFAULT_PERSONAL_MINUTES_TEMPLATE = "personal_minutes"

# 共识决策线的默认模板：extra.template 留空时自动套用「共识决策」（consensus_decision）。
DEFAULT_CONSENSUS_DECISION_TEMPLATE = "consensus_decision"


def personal_minutes_template() -> str:
    """真人模式（profile=user）默认套用的纪要模板名（固定 personal_minutes）。"""
    return DEFAULT_PERSONAL_MINUTES_TEMPLATE


# 多样式纪要 5 大黄金模式
STYLE_NAMES = frozenset({"brief", "topic", "review", "retro", "alignment"})

# 多样式纪要模板目录：resources/styles/
RESOURCES_STYLES_DIR = PROJECT_ROOT / "resources" / "styles"


def style_template_path(style_name: str) -> Path | None:
    """查找 resources/styles/{style_name}.md 模板文件（严格限制为 5 大模式：brief/topic/review/retro/alignment）。"""
    name = (style_name or "").strip().lower()
    if not name:
        name = "topic"
    if name not in STYLE_NAMES:
        return None
    tpl_file = RESOURCES_STYLES_DIR / f"{name}.md"
    return tpl_file if tpl_file.is_file() else None


# 每个取值只打一次日志（template_dir() 会被频繁调用），避免配置写错时逐请求刷屏
_template_dir_logged: set[str] = set()

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_JOB_TTL_SECONDS = 7 * 24 * 60 * 60
# 异步任务执行模式：inline=API 进程内跑（缺省，兼容旧行为）；queue=推 Redis 队列，由 app.worker 消费
DEFAULT_RUN_MODE = "inline"
DEFAULT_JOB_MAX_ATTEMPTS = 2
DEFAULT_LEASE_SECONDS = 60
DEFAULT_HEARTBEAT_SECONDS = 10

_env_loaded = False


def load_env() -> None:
    """.env → os.environ（首次生效；已存在的环境变量优先，不被覆盖）。

    进程内只读一次文件：事件写 Redis 的路径会频繁取配置，重复读盘没必要。
    环境变量本身不缓存，测试里临时改 env 仍能生效。
    """
    global _env_loaded
    if _env_loaded:
        return
    try:
        from infra.llm.config import load_env as _load_env
    except ImportError:
        from infra.llm.config import load_env as _load_env

    _load_env(PROJECT_ROOT / ".env")
    _env_loaded = True


# ── 模板源目录（优先 resources/templates，回退 template）─────────

def template_dir() -> Path:
    """当前生效的模板源目录（优先 resources/templates/，回退 template/）。"""
    res_dir = PROJECT_ROOT / "resources" / "templates"
    path = res_dir if res_dir.is_dir() else (PROJECT_ROOT / "template")
    if path.name not in _template_dir_logged:
        _template_dir_logged.add(path.name)
        logger.info("模板源目录：%s", path)
    missing = sorted(tid for tid in TEMPLATE_SCENARIO if not (path / f"{tid}.md").is_file())
    if missing and f"missing:{path.name}" not in _template_dir_logged:
        _template_dir_logged.add(f"missing:{path.name}")
        logger.warning(
            "模板目录 %s 缺少 %d/%d 个模板：%s%s（对应的 extra.template 会 400）",
            path.name, len(missing), len(TEMPLATE_SCENARIO), "、".join(missing[:8]),
            "…" if len(missing) > 8 else "",
        )
    return path


def __getattr__(name: str) -> Path:
    """兼容旧的 ``from app.config import TEMPLATE_DIR``：动态返回当前模板目录。

    （模块级 ``__getattr__`` 在找不到属性时才调用，所以这里不会和别的常量打架。）
    """
    if name == "TEMPLATE_DIR":
        return template_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Redis（异步任务接口：任务状态 + 事件流 + 全局发号器）────────

def redis_url() -> str:
    """Redis 地址（.env 的 REDIS_URL），缺省本机 0 号库。

    调用方可能是请求前的建连路径（发号器、任务提交），此时 ``_prepare``
    还没跑过，所以这里自己先加载 .env，不依赖别的调用点。
    """
    load_env()
    return (os.getenv("REDIS_URL") or "").strip() or DEFAULT_REDIS_URL


def job_ttl_seconds() -> int:
    """任务状态与事件流的过期秒数（.env 的 AGENTFLOW_JOB_TTL_SECONDS，默认 7 天）。"""
    load_env()
    try:
        value = int((os.getenv("AGENTFLOW_JOB_TTL_SECONDS") or "").strip())
    except ValueError:
        return DEFAULT_JOB_TTL_SECONDS
    return value if value > 0 else DEFAULT_JOB_TTL_SECONDS


# ── 异步任务执行（队列 / worker）──────────────────────────

def _int_env(name: str, default: int) -> int:
    load_env()
    try:
        value = int((os.getenv(name) or "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def run_mode() -> str:
    """异步任务在哪执行。

    ``inline``（默认）：API 进程内 BackgroundTasks，行为和旧版一致，起个 uvicorn 就能用；
    ``queue``：提交只落盘 + 入队，由独立进程 ``python -m app.worker`` 消费执行。
    """
    load_env()
    value = (os.getenv("AGENTFLOW_RUN_MODE") or "").strip().lower()
    return value if value in {"inline", "queue"} else DEFAULT_RUN_MODE


def job_max_attempts() -> int:
    """同一 job 最多执行几次（含首次）。仅对可重试失败生效（输入类错误不重试）。"""
    return _int_env("AGENTFLOW_JOB_MAX_ATTEMPTS", DEFAULT_JOB_MAX_ATTEMPTS)


def lease_seconds() -> int:
    """执行租约时长：worker 超过这个时间没续期，任务会被判定为失联并回收重排。"""
    return _int_env("AGENTFLOW_LEASE_SECONDS", DEFAULT_LEASE_SECONDS)


def heartbeat_seconds() -> int:
    """worker 续期间隔，需明显小于租约时长（默认 10s 续一次 / 60s 过期）。"""
    return _int_env("AGENTFLOW_HEARTBEAT_SECONDS", DEFAULT_HEARTBEAT_SECONDS)


def load_domain(name: str):
    try:
        from core.runner.context import load_domain as _load_domain
    except ImportError:
        from core.runner.context import load_domain as _load_domain

    return _load_domain(name, PROJECT_ROOT)


# ── 模板注册表（8 场景 30 类；源 = template_dir()/*.md）────────────

# 场景 ID → 中文名（只作展示；模板文件里不存场景名）
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

# 模板 md 文件名（= 模板 ID）→ 场景 ID。模板文件不携带场景，靠这张表还原内部键
# {场景ID}_{模板ID}（内部键只用于注册表索引；对外取值是英文名/中文名）。
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
    "admission_briefing": "meeting_minutes",
    "personal_minutes": "meeting_minutes",
    "consensus_decision": "meeting_minutes",
    "general_minutes": "daily_journal",
    "personal_memo": "daily_journal",
    "conversation_transcript": "daily_journal",
    "site_visit_tour": "daily_journal",
    "home_school_liaison": "daily_journal",
}


def _parse_template_md(path: Path) -> dict[str, object] | None:
    """``template_dir()/{id}.md`` → 注册表条目；文件不合规返回 None。

    模板文件结构固定（它就是权威源，手工编辑时保持该结构）::

        # {中文名}

        <!-- requirement
        {写作要求}
        -->

        {format 正文}

    ``format`` 取出的是**去掉中文名标题行与 requirement 注释之后**的正文 ——
    与下游 ``wrap_template_requirement`` / ``split_template_meta`` 的分工保持一致。
    """
    try:
        try:
            from core.templates.router._base import split_template_meta
        except ImportError:
            from core.templates.router._base import split_template_meta

        raw = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 单文件读失败不影响其它模板
        return None

    body, requirement = split_template_meta(raw)
    lines = body.splitlines()
    name = ""
    for i, line in enumerate(lines):
        if line.startswith("# "):
            name = line[2:].strip()
            if path.stem == "general_minutes":
                # 通用纪要保留顶部 # 通用纪要 标题行，使模板渲染与产物落盘固定以此为顶级标题
                lines = lines[i:]
            else:
                lines = lines[i + 1 :]  # 中文名标题行是文件头，不进 format
            break
    format_text = "\n".join(lines).strip()
    if not format_text:
        return None
    template_id = path.stem
    scenario_id = TEMPLATE_SCENARIO.get(template_id)
    if not scenario_id:
        return None  # 未知模板：不猜场景，宁可不在注册表里（extra.template 会 400）
    return {
        "format": format_text,
        "name": name or template_id,
        "scenario": SCENARIO_NAMES.get(scenario_id, scenario_id),
        "requirement": requirement.strip(),
        "description": "",
        "template": template_id,
    }


def template_registry() -> dict[str, dict[str, object]]:
    """返回 {内部契约键: {"format","name","scenario","requirement","template"}}。

    **唯一模板源是 ``template_dir()/*.md``（固定为 template/）**。
    运行时直接读，没有第二兜底源。目录缺失或文件全部不合规时返回空注册表 —— 此时
    ``extra.template`` 一律 400，不会静默套错模板。
    """
    tpl_dir = template_dir()
    if not tpl_dir.is_dir():
        return {}
    out: dict[str, dict[str, object]] = {}
    for md_path in sorted(tpl_dir.glob("*.md")):
        if md_path.stem.lower() in {"readme", "diff"}:
            continue
        item = _parse_template_md(md_path)
        if item:
            out[f"{TEMPLATE_SCENARIO[md_path.stem]}_{md_path.stem}"] = item
    return out


def template_key(template_value: str) -> str:
    """extra.template 取值 → 内部契约键 ``{场景ID}_{模板ID}``；无法识别返回空串。

    只接受两种写法（英文名大小写不敏感）：
    - 模板 md 英文名：``project_progress`` / ``project_progress.md``
    - 模板中文名（YAML ``name``）：``项目进度会``

    旧契约值 ``{场景ID}_{模板ID}`` 与其它串一律不识别（调用方按 400 处理）。
    注册表内每个模板 ID 与中文名各自唯一、且互不冲突，别名不会歧义（数量随模板目录变化）。
    """
    raw = (template_value or "").strip()
    if not raw:
        return ""
    stem = raw[:-3] if raw.lower().endswith(".md") else raw
    folded = stem.strip().lower()
    registry = template_registry()
    for key, item in registry.items():
        if str(item.get("template") or "").lower() == folded:
            return key
    for key, item in registry.items():
        if raw == str(item.get("name") or "").strip():
            return key
    return ""


def resolve_template_format(template_value: str) -> str:
    """extra.template 值 → 模板 format 文本（含写作要求注释）；非法值返回空串。

    取值只两种：模板 md 英文名、模板中文名（见 :func:`template_key`）。
    """
    value = (template_value or "").strip()
    if not value:
        return ""
    item = template_registry().get(template_key(value)) or {}
    fmt = str(item.get("format") or "").strip()
    req = str(item.get("requirement") or "").strip()
    if not fmt:
        return ""
    try:
        from core.templates.router._base import wrap_template_requirement
    except ImportError:
        from core.templates.router._base import wrap_template_requirement

    return wrap_template_requirement(fmt, req)


RESOURCES_PROFILE_DIR = PROJECT_ROOT / "resources" / "profiles"
PROFILE_DIR = RESOURCES_PROFILE_DIR if RESOURCES_PROFILE_DIR.is_dir() else (PROJECT_ROOT / "assets" / "profiles")


def profile_path(domain: str, profile_value: str, user_id: str = "") -> Path:
    """extra.profile 值 → 画像文件路径（实现见 ``core.runner.profiles.resolve_profile_file``）。

    空/缺省 → **默认档：客观全员**（2026-09-21 起不再自动发现 user.json；纪要线再由
    ``extra.template`` 留空自动套「通用纪要」）；``user`` = 真人档案
    ``data/{X-User-Id}/user.json``（缺档案 → 空 Path 由调用方 400）；
    ``objective`` / ``object`` = 客观全员（与空值同档，留作显式表达）；
    其余按职业模板名查 ``resources/profiles/{name}.json``，
    不存在返回空 Path（调用方判 400）。
    """
    try:
        from core.runner.profiles import resolve_profile_file
    except ImportError:
        from core.runner.profiles import resolve_profile_file

    return resolve_profile_file(profile_value, domain=domain, user_id=user_id)


__all__ = [
    "DEFAULT_JOB_MAX_ATTEMPTS",
    "DEFAULT_JOB_TTL_SECONDS",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MINUTES_TEMPLATE",
    "DEFAULT_PERSONAL_MINUTES_TEMPLATE",
    "DEFAULT_CONSENSUS_DECISION_TEMPLATE",
    "personal_minutes_template",
    "DEFAULT_REDIS_URL",
    "DEFAULT_RUN_MODE",
    "PROFILE_DIR",
    "PROJECT_ROOT",
    "RESOURCES_STYLES_DIR",
    "STYLE_NAMES",
    "style_template_path",
    "heartbeat_seconds",
    "job_max_attempts",
    "job_ttl_seconds",
    "lease_seconds",
    "load_domain",
    "load_env",
    "profile_path",
    "redis_url",
    "resolve_template_format",
    "run_mode",
    "template_key",
    "template_registry",
]
