# 拆分自原大文件，保留：test_domain_hooks_registry, test_tasklines_registration, test_notes_review_and_quiz_tasklines…

"""tools/core 零 LLM 自测：画像选档（``profile=user`` → data/{uid}/user.json）、清洗、职业模板合并。

用法::

    python -m tests.test_core
"""

from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from core.runner.profiles import (
    classify_profile,
    filter_identity_fields,
    is_user_profile_file,
    load_role_mapping,
    read_user_profile,
    resolve_profile_file,
    resolve_role_template,
    resolve_role_to_template_key,
    sanitize_user_profile,
    user_profile_path,
)
from tests.support.expectations import expect
import pytest

pytestmark = pytest.mark.integration

def _write(path: Path, data) -> Path:
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

def test_domain_hooks_registry() -> None:
    """域钩子注册表：引擎只按域名取钩子；未注册/未知域一律空钩子，不抛。

    2026-09-22 决策：记忆注入/回写、产物 HTML、无模板收尾压缩原先由引擎直接 import
    域包（跨层反向依赖），现改为**域自注册 + 引擎按域名取**。这里锁住协议面：
    空域名/未知域不炸、注册可覆盖、域包自注册、域名从模块路径推导、clear 可复位。
    """
    from core.graph.nodes import DomainNodes
    from core.runner.hooks import DomainHooks, clear, hooks_for, register, registered

    class _Stub(DomainNodes):
        """测试桩：不在 domain.* 包内 ⇒ 域名推导为空串。"""

    expect(hooks_for("") == DomainHooks(), "空域名 → 空钩子（测试桩/未指定域不炸）", "")
    expect(hooks_for("no_such_domain") == DomainHooks(), "未知域 → 空钩子且不抛", "")
    expect(hooks_for("no_such_domain", ensure=False) == DomainHooks(), "ensure=False 不触发 import，同样空钩子", "")

    probe = DomainHooks(memory_lines=frozenset({"x"}), html_for=lambda *a, **k: "<p>x</p>")
    register("probe_domain", probe)
    expect(hooks_for("probe_domain") is probe, "注册后按域名取回同一对象", str(registered().keys()))
    register("", probe)
    expect("" not in registered(), "空域名注册被忽略", str(registered().keys()))

    hooks = hooks_for("meeting")
    expect("meeting" in registered()
          and hooks.memory_lines == frozenset({"minutes", "minutes_styles"}), "域包 import 后自注册（meeting）", str(sorted(hooks.memory_lines)))
    expect(all(
              getattr(hooks, name) is not None
              for name in ("prepare_memory", "persist_memory", "inject_line_extra",
                           "apply_citations", "html_for", "compact_plain")
          ), "meeting 钩子六项齐全（准备/回写/注入/引用/HTML/压缩）", "")
    notes = hooks_for("notes")
    expect(notes.memory_lines == frozenset({"graph"})
          and notes.prepare_memory is not None
          and notes.persist_memory is not None
          and notes.html_for is None
          and notes.compact_plain is None, "notes 钩子只有记忆两项（无 HTML / 无压缩）", str(sorted(notes.memory_lines)))

    expect(hooks.html_for("minutes", "t", "正文", {}) is not None
          and hooks.html_for("risks", "t", "正文", {}) is not None
          and hooks.html_for("actions", "t", "正文", {}) is not None
          and hooks.html_for("minutes_trace", "t", "正文", {}) is not None
          and hooks.html_for("mindmap", "t", "正文", {}) is None, "域 HTML 钩子：纪要/风险/待办/溯源有，其它线返回 None（引擎回退通用 HTML）", "")
    from domains.meeting.tasks.minutes.steps.minutes_render import compact_untemplated_minutes

    expect(hooks.compact_plain("minutes", "a\n\n\nb") == compact_untemplated_minutes("a\n\n\nb")
          and hooks.compact_plain("actions", "a\n\n\nb") == "a\n\n\nb", "压缩钩子：纪要类线走域内压缩，其它线原样返回", repr(hooks.compact_plain("minutes", "a\n\n\nb")))

    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.notes.orchestrator import NotesAgentSystem

    expect(object.__new__(MeetingAgentSystem).domain_name == "meeting", "域名推导：domain.meeting.orchestrator → meeting", "")
    expect(object.__new__(NotesAgentSystem).domain_name == "notes", "域名推导：domain.notes.orchestrator → notes", "")
    expect(_Stub().domain_name == "", "域名推导：测试桩（非 domain 包）→ 空串", "")

    clear()
    expect(registered() == {}, "clear 后为未注册态", str(registered()))
    # ensure 只在"域包尚未 import"时才触发自注册（Python 不会重跑已 import 模块的 __init__）；
    # 生产路径由 load_domain 先 import 域包保证注册，故这里只断言"不炸且为空钩子"。
    expect(hooks_for("meeting") == DomainHooks(), "clear 后取到空钩子（生产由 load_domain 保证注册）", "")

    # 复位：clear 是测试用 API，本测试跑完必须把两个域重新注册回去——否则同一进程里
    # 后续套件（如 tests.test_engine_smoke）会拿到空钩子而误判失败（2026-09-22 实测）。
    import importlib
    import sys

    for domain_name in ("meeting", "notes"):
        module = sys.modules.get(f"domains.{domain_name}.hooks")
        if module is None:
            importlib.import_module(f"domains.{domain_name}.hooks")
            module = sys.modules[f"domains.{domain_name}.hooks"]
        register(domain_name, importlib.reload(module).HOOKS)
    expect(set(registered()) >= {"meeting", "notes"}, "测试收尾：两域钩子已复位（避免影响同进程其它套件）", str(sorted(registered())))


def test_tasklines_registration() -> None:
    """验证 meeting.mindmap 及 notes.review / notes.quiz 注册生效：白名单解析通过，且 FastAPI 预览端点挂载成功。"""
    from app.main import app
    from app.tasklines import lines_for, resolve_line

    expect("mindmap" in lines_for("meeting"), "meeting 域包含 mindmap 任务线", "")
    expect(resolve_line("meeting", "mindmap") == ("meeting", "mindmap"), "resolve_line 支持 meeting + mindmap", "")
    expect("review" in lines_for("notes"), "notes 域包含 review 任务线", "")
    expect("quiz" in lines_for("notes"), "notes 域包含 quiz 任务线", "")
    expect(resolve_line("notes", "review") == ("notes", "review"), "resolve_line 支持 notes + review", "")
    expect(resolve_line("notes", "quiz") == ("notes", "quiz"), "resolve_line 支持 notes + quiz", "")
    routes = {r.path for r in app.routes}
    expect("/api/agent/v1" in routes, "FastAPI 注册了 S1 /api/agent/v1", str(routes))
    expect("/api/agent/v1/stream" in routes, "FastAPI 注册了 S2 /api/agent/v1/stream", str(routes))
    expect("/api/agent/v1/file/{request_id}/{file_name}" in routes, "FastAPI 注册了 S3 /api/agent/v1/file/{request_id}/{file_name}", str(routes))
    expect(not any(r.startswith("/api/v1/meeting") for r in routes), "meeting 域不再注册 preview 路由", str(routes))
    expect(not any(r.startswith("/api/v1/notes") for r in routes), "notes 域不再注册 preview 路由", str(routes))


def test_notes_review_and_quiz_tasklines() -> None:
    """验证 notes 域 review 和 quiz 真正作为对外任务线：入参校验与输入装配。"""
    from app.requirements import check_required
    from app.schemas import Extra, TaskRequest
    from app.tasks import _prepare

    # 1. 校验规则 (check_required)
    empty_req = TaskRequest()
    missing_rev = check_required("review", empty_req, "")
    expect(len(missing_rev) == 2, "缺 user_id 与材料时提示缺失", str(missing_rev))

    text_req = TaskRequest(
        texts={"notes": "光电效应是光子与金属中电子相互作用的现象。"},
        extra=Extra(subject="physics"),
    )
    missing_ok = check_required("review", text_req, "u123")
    expect(len(missing_ok) == 0, "传入 notes 文本与 user_id 时校验通过", str(missing_ok))

    # 2. _prepare 输入准备与 scope 注入
    prep_rev = _prepare("notes", "review", text_req, "u123")
    expect(prep_rev.line == "review", "line 正确解析为 review", "")
    expect(prep_rev.input_files is not None and prep_rev.input_files.is_file(), "用户输入文件正常生成", "")
    expect("【用户ID】u123" in (prep_rev.extra_line_inputs.get("review") or ""), "extra_line_inputs 注入了 scope", "")

    quiz_req = TaskRequest(
        texts={"transcript": "牛顿第二定律公式为 F=ma，其中 m 为质量，a 为加速度。"},
        extra=Extra(subject="physics"),
    )
    prep_quiz = _prepare("notes", "quiz", quiz_req, "u123")
    expect(prep_quiz.line == "quiz", "line 正确解析为 quiz", "")
    expect(prep_quiz.input_files is not None and prep_quiz.input_files.is_file(), "quiz 用户输入文件正常生成", "")
    # 3. HTTP 端点实际调用验证 (S3 产物下载端点正确寻址与响应)
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r_rev = client.get("/api/agent/v1/file/not_found/review.html?user_id=u123")
    expect(r_rev.status_code == 404 and "review.html" in r_rev.text, "review 下载端点正常响应404（寻址正确定位 output/not_found/review.html）", str(r_rev.json()))
    r_quiz = client.get("/api/agent/v1/file/not_found/quiz.html?user_id=u123")
    expect(r_quiz.status_code == 404 and "quiz.html" in r_quiz.text, "quiz 下载端点正常响应404（寻址正确定位 output/not_found/quiz.html）", str(r_quiz.json()))
