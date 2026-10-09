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

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


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


from tests.unit.core.profiles.test_user_profile import (
    test_user_profile_path_safety as _test_user_profile_path_safety,
    test_selection_matrix as _test_selection_matrix,
    test_broken_user_profile as _test_broken_user_profile,
    test_sanitize_and_merge as _test_sanitize_and_merge,
)
from tests.unit.core.profiles.test_role_mapping import (
    test_missing_role_template as _test_missing_role_template,
    test_role_mapping as _test_role_mapping,
)







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

    check("空域名 → 空钩子（测试桩/未指定域不炸）", hooks_for("") == DomainHooks(), "")
    check("未知域 → 空钩子且不抛", hooks_for("no_such_domain") == DomainHooks(), "")
    check("ensure=False 不触发 import，同样空钩子",
          hooks_for("no_such_domain", ensure=False) == DomainHooks(), "")

    probe = DomainHooks(memory_lines=frozenset({"x"}), html_for=lambda *a, **k: "<p>x</p>")
    register("probe_domain", probe)
    check("注册后按域名取回同一对象", hooks_for("probe_domain") is probe, str(registered().keys()))
    register("", probe)
    check("空域名注册被忽略", "" not in registered(), str(registered().keys()))

    hooks = hooks_for("meeting")
    check("域包 import 后自注册（meeting）",
          "meeting" in registered()
          and hooks.memory_lines == frozenset({"minutes", "minutes_styles"}),
          str(sorted(hooks.memory_lines)))
    check("meeting 钩子六项齐全（准备/回写/注入/引用/HTML/压缩）",
          all(
              getattr(hooks, name) is not None
              for name in ("prepare_memory", "persist_memory", "inject_line_extra",
                           "apply_citations", "html_for", "compact_plain")
          ),
          "")
    notes = hooks_for("notes")
    check("notes 钩子只有记忆两项（无 HTML / 无压缩）",
          notes.memory_lines == frozenset({"graph"})
          and notes.prepare_memory is not None
          and notes.persist_memory is not None
          and notes.html_for is None
          and notes.compact_plain is None,
          str(sorted(notes.memory_lines)))

    check("域 HTML 钩子：纪要/风险/待办/溯源有，其它线返回 None（引擎回退通用 HTML）",
          hooks.html_for("minutes", "t", "正文", {}) is not None
          and hooks.html_for("risks", "t", "正文", {}) is not None
          and hooks.html_for("actions", "t", "正文", {}) is not None
          and hooks.html_for("minutes_trace", "t", "正文", {}) is not None
          and hooks.html_for("mindmap", "t", "正文", {}) is None,
          "")
    from domains.meeting.tasks.minutes.steps.minutes_render import compact_untemplated_minutes

    check("压缩钩子：纪要类线走域内压缩，其它线原样返回",
          hooks.compact_plain("minutes", "a\n\n\nb") == compact_untemplated_minutes("a\n\n\nb")
          and hooks.compact_plain("actions", "a\n\n\nb") == "a\n\n\nb",
          repr(hooks.compact_plain("minutes", "a\n\n\nb")))

    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.notes.orchestrator import NotesAgentSystem

    check("域名推导：domain.meeting.orchestrator → meeting",
          object.__new__(MeetingAgentSystem).domain_name == "meeting", "")
    check("域名推导：domain.notes.orchestrator → notes",
          object.__new__(NotesAgentSystem).domain_name == "notes", "")
    check("域名推导：测试桩（非 domain 包）→ 空串", _Stub().domain_name == "", "")

    clear()
    check("clear 后为未注册态", registered() == {}, str(registered()))
    # ensure 只在"域包尚未 import"时才触发自注册（Python 不会重跑已 import 模块的 __init__）；
    # 生产路径由 load_domain 先 import 域包保证注册，故这里只断言"不炸且为空钩子"。
    check("clear 后取到空钩子（生产由 load_domain 保证注册）",
          hooks_for("meeting") == DomainHooks(), "")

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
    check("测试收尾：两域钩子已复位（避免影响同进程其它套件）",
          set(registered()) >= {"meeting", "notes"}, str(sorted(registered())))


def test_tasklines_registration() -> None:
    """验证 meeting.mindmap 及 notes.review / notes.quiz 注册生效：白名单解析通过，且 FastAPI 预览端点挂载成功。"""
    from app.main import app
    from app.tasklines import lines_for, resolve_line

    check("meeting 域包含 mindmap 任务线", "mindmap" in lines_for("meeting"), "")
    check("resolve_line 支持 meeting + mindmap", resolve_line("meeting", "mindmap") == ("meeting", "mindmap"), "")
    check("notes 域包含 review 任务线", "review" in lines_for("notes"), "")
    check("notes 域包含 quiz 任务线", "quiz" in lines_for("notes"), "")
    check("resolve_line 支持 notes + review", resolve_line("notes", "review") == ("notes", "review"), "")
    check("resolve_line 支持 notes + quiz", resolve_line("notes", "quiz") == ("notes", "quiz"), "")
    routes = {r.path for r in app.routes}
    check("FastAPI 注册了 S1 /api/agent/v1", "/api/agent/v1" in routes, str(routes))
    check("FastAPI 注册了 S2 /api/agent/v1/stream", "/api/agent/v1/stream" in routes, str(routes))
    check("FastAPI 注册了 S3 /api/agent/v1/file/{request_id}/{file_name}", "/api/agent/v1/file/{request_id}/{file_name}" in routes, str(routes))
    check("meeting 域不再注册 preview 路由", not any(r.startswith("/api/v1/meeting") for r in routes), str(routes))
    check("notes 域不再注册 preview 路由", not any(r.startswith("/api/v1/notes") for r in routes), str(routes))


def test_notes_review_and_quiz_tasklines() -> None:
    """验证 notes 域 review 和 quiz 真正作为对外任务线：入参校验与输入装配。"""
    from app.requirements import check_required
    from app.schemas import Extra, TaskRequest
    from app.tasks import _prepare

    # 1. 校验规则 (check_required)
    empty_req = TaskRequest()
    missing_rev = check_required("review", empty_req, "")
    check("缺 user_id 与材料时提示缺失", len(missing_rev) == 2, str(missing_rev))

    text_req = TaskRequest(
        texts={"notes": "光电效应是光子与金属中电子相互作用的现象。"},
        extra=Extra(subject="physics"),
    )
    missing_ok = check_required("review", text_req, "u123")
    check("传入 notes 文本与 user_id 时校验通过", len(missing_ok) == 0, str(missing_ok))

    # 2. _prepare 输入准备与 scope 注入
    prep_rev = _prepare("notes", "review", text_req, "u123")
    check("line 正确解析为 review", prep_rev.line == "review", "")
    check("用户输入文件正常生成", prep_rev.input_files is not None and prep_rev.input_files.is_file(), "")
    check("extra_line_inputs 注入了 scope", "【用户ID】u123" in (prep_rev.extra_line_inputs.get("review") or ""), "")

    quiz_req = TaskRequest(
        texts={"transcript": "牛顿第二定律公式为 F=ma，其中 m 为质量，a 为加速度。"},
        extra=Extra(subject="physics"),
    )
    prep_quiz = _prepare("notes", "quiz", quiz_req, "u123")
    check("line 正确解析为 quiz", prep_quiz.line == "quiz", "")
    check("quiz 用户输入文件正常生成", prep_quiz.input_files is not None and prep_quiz.input_files.is_file(), "")
    # 3. HTTP 端点实际调用验证 (S3 产物下载端点正确寻址与响应)
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r_rev = client.get("/api/agent/v1/file/not_found/review.html?user_id=u123")
    check("review 下载端点正常响应404（寻址正确定位 output/not_found/review.html）", r_rev.status_code == 404 and "review.html" in r_rev.text, str(r_rev.json()))
    r_quiz = client.get("/api/agent/v1/file/not_found/quiz.html?user_id=u123")
    check("quiz 下载端点正常响应404（寻址正确定位 output/not_found/quiz.html）", r_quiz.status_code == 404 and "quiz.html" in r_quiz.text, str(r_quiz.json()))


from tests.unit.meeting.test_agenda_assembly import (
    test_agenda_minutes_input_assembly as _test_agenda_minutes_input_assembly,
)


def test_request_schema_and_validation() -> None:
    """验证请求体字段重构（memory 顶层、extra.time、extra.catalog）与 14 任务前置校验。"""
    from app.config import PROJECT_ROOT
    from app.requirements import REQUIRED_FIELDS, check_required
    from app.schemas import Extra, TaskRequest
    from app.tasks import ApiError, _prepare

    # 1. 验证 TaskRequest 数据模型及向下兼容 Auto-Lifting
    # 1.1 memory 顶层字段与 extra.memory 自动互通
    r1 = TaskRequest(memory=True)
    check("TaskRequest 顶层支持 memory=True", r1.memory is True, "")
    check("TaskRequest memory 自动同步到 extra.memory", r1.extra.memory is True, "")

    r2 = TaskRequest.model_validate({"extra": {"memory": True}})
    check("老格式 extra.memory 自动提升到顶层 memory", r2.memory is True, "")

    # 1.2 time 下沉至 extra.time 与双向同步
    r3 = TaskRequest(time="2026-06-15 10:00")
    check("顶层 time 自动同步到 extra.time", r3.extra.time == "2026-06-15 10:00", "")

    r4 = TaskRequest.model_validate({"extra": {"time": "2026-06-15 10:00"}})
    check("extra.time 自动同步到顶层 time", r4.time == "2026-06-15 10:00", "")

    # 1.3 extra.catalog 显式指定及 docs 兼容提取
    r5 = TaskRequest(extra=Extra(catalog="20261001_100000.json"))
    check("Extra 支持 catalog 字段", r5.extra.catalog == "20261001_100000.json", "")

    r6 = TaskRequest.model_validate({"docs": ["phy_8b4dccc8.json", "teacher.txt"]})
    check("docs 中的 .json 自动移入 extra.catalog", r6.extra.catalog == "phy_8b4dccc8.json", "")
    check("docs 剥离 .json 仅保留真实附件", r6.docs == ["teacher.txt"], str(r6.docs))

    # 2. 验证 14 任务必填校验矩阵 (check_required)
    check("REQUIRED_FIELDS 包含全量 14 个任务", len(REQUIRED_FIELDS) == 14, str(len(REQUIRED_FIELDS)))

    # 2.1 mindmap 必传 transcript 与 user_id
    m_mindmap_empty = check_required("mindmap", TaskRequest(), "")
    check("mindmap 缺参时拦截 user_id 与 transcript", len(m_mindmap_empty) == 2, str(m_mindmap_empty))
    m_mindmap_ok = check_required("mindmap", TaskRequest(texts={"transcript": "会议记录"}), "u1")
    check("mindmap 传参完整时通过校验", len(m_mindmap_ok) == 0, str(m_mindmap_ok))

    # 2.2 graph 仅需 texts 或 docs 之一
    m_graph_empty = check_required("graph", TaskRequest(), "u1")
    check("graph 无输入时拦截 texts_or_docs", len(m_graph_empty) == 1, str(m_graph_empty))
    m_graph_text = check_required("graph", TaskRequest(texts={"notes": "概念A->概念B"}), "u1")
    check("graph 仅传 notes 文本时通过校验", len(m_graph_text) == 0, str(m_graph_text))
    m_graph_docs = check_required("graph", TaskRequest(docs=["notes.txt"]), "u1")
    check("graph 仅传 docs 文件时通过校验", len(m_graph_docs) == 0, str(m_graph_docs))

    # 2.3 checklist 仅需 extra.subject（docs 与 catalog 均为可选）
    m_chk_empty = check_required("checklist", TaskRequest(), "u1")
    check("checklist 缺 subject 时拦截", len(m_chk_empty) == 1 and "subject" in m_chk_empty[0], str(m_chk_empty))
    m_chk_ok = check_required("checklist", TaskRequest(extra=Extra(subject="physics")), "u1")
    check("checklist 仅传 subject 时即可通过必填校验", len(m_chk_ok) == 0, str(m_chk_ok))

    # 3. 验证 _prepare 中 extra.catalog 与 extra.time / memory 的组装
    # 构造测试用的 catalog 文件
    from domains.notes.tasks.catalog.store import _subject_filename

    sub_dir = _subject_filename("physics")
    cat_dir = PROJECT_ROOT / "data" / "u_test_schema" / "knowledge" / "catalogs" / sub_dir
    cat_dir.mkdir(parents=True, exist_ok=True)
    cat_file = cat_dir / "20261001_100000.json"
    cat_file.write_text('{"course": "物理", "version": "v1"}', encoding="utf-8")

    # 3.1 显式 extra.catalog
    req_chk = TaskRequest(extra=Extra(subject="physics", catalog="20261001_100000.json"))
    prep_chk = _prepare("notes", "checklist", req_chk, "u_test_schema")
    chk_input = prep_chk.extra_line_inputs.get("checklist", "")
    check("checklist 正确注入 extra.catalog", "【目录文件】20261001_100000.json" in chk_input, chk_input)

    # 3.2 兼容老客户端 docs 传入 catalog.json
    req_chk_legacy = TaskRequest.model_validate({
        "docs": ["20261001_100000.json"],
        "extra": {"subject": "physics"},
    })
    prep_chk_legacy = _prepare("notes", "checklist", req_chk_legacy, "u_test_schema")
    chk_input_legacy = prep_chk_legacy.extra_line_inputs.get("checklist", "")
    check("checklist 兼容老入参 docs 注入 catalog", "【目录文件】20261001_100000.json" in chk_input_legacy, chk_input_legacy)

    # 3.3 不存在的 catalog 报 404
    req_chk_notfound = TaskRequest(extra=Extra(subject="physics", catalog="not_exist.json"))
    try:
        _prepare("notes", "checklist", req_chk_notfound, "u_test_schema")
        check("不存在的 catalog 抛 404", False, "未抛出异常")
    except ApiError as exc:
        check("不存在的 catalog 抛 404", exc.status == 404 and "not_exist.json" in exc.message, exc.message)

    # 3.4 memory 与 time 正确传递到 _Prepared
    req_minutes = TaskRequest(
        texts={"transcript": "发言者1：开会讨论技术架构。"},
        memory=True,
        extra=Extra(time="2026-06-15 10:00", project="proj_alpha"),
    )
    prep_min = _prepare("meeting", "minutes", req_minutes, "u_test_schema")
    check("prep.memory 正确获取顶层 memory 开关", prep_min.memory is True, "")
    check("prep.time 正确获取 extra.time", prep_min.time == "2026-06-15 10:00", prep_min.time)

    # 清理测试目录
    import shutil
    shutil.rmtree(PROJECT_ROOT / "data" / "u_test_schema", ignore_errors=True)


def test_catalog_output_artifacts_and_download() -> None:
    """验证 catalog 任务产物：生成 catalog.html + result.md，file_name 返回 catalog.html 且支持下载。"""
    import shutil
    from app.config import PROJECT_ROOT
    from app.outputs import resolve_output_file, save_task_outputs
    from app.tasks import _output_file_name
    from domains.notes.reports import CatalogReport
    from domains.notes.tasks.catalog.display import (
        build_catalog_html,
        build_catalog_markdown,
    )
    from infra.exporters.outputs import save_report_artifacts

    user_id = "u_cat_test"
    req_id = "req_cat_123"

    draft = {
        "course": "高中物理",
        "version": "1",
        "mode": "build",
        "chapters": [
            {
                "name": "第一章 运动的描述",
                "topics": [
                    {
                        "name": "质点与参考系",
                        "knowledge_points": [
                            {
                                "id": "kp_001",
                                "name": "参考系的选择",
                                "learning_role": "core_concept",
                                "importance": 4,
                                "practice_type": ["distinguish", "recall"],
                                "completion_criteria": ["can_explain"],
                                "risk_tags": ["concept_confusion"],
                                "related_points": [{"name": "坐标系", "relation": "used_with"}],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    # 1. 验证 build_catalog_html 生成包含 cat-doc 的页面
    html = build_catalog_html(draft)
    check("catalog HTML 包含根容器 cat-doc", "cat-doc" in html, "")
    check("catalog HTML 包含课程名", "高中物理" in html, "")
    check("catalog HTML 包含目录层级树", "目录层级树" in html, "")
    check("catalog HTML 包含知识点卡片与标签", "参考系的选择" in html and "核心概念" in html, "")
    check("catalog HTML 包含星级评分", "★★★★☆" in html, "")

    # 验证空 draft
    empty_html = build_catalog_html({})
    check("空 catalog HTML 仍包含 cat-doc 容器", "cat-doc" in empty_html, "")
    check("空 catalog HTML 包含空提示", "没有整理出可用目录" in empty_html, "")

    # 2. 验证 save_report_artifacts 落盘 result.md 与 catalog.html
    rendered_md = build_catalog_markdown(draft)
    report = CatalogReport(
        course="高中物理",
        version="1",
        catalog_html=html,
        personalized_text=rendered_md,
    )
    from core.runner.context import load_domain

    ctx = load_domain("notes", PROJECT_ROOT)
    ctx.user_id = user_id
    saved = save_report_artifacts(ctx, "catalog", report)
    check("save_report_artifacts 成功产出 text (result.md)", "text" in saved and saved["text"].name == "result.md", str(saved))
    check("save_report_artifacts 成功产出 html (catalog.html)", "html" in saved and saved["html"].name == "catalog.html", str(saved))

    # 3. 验证 save_task_outputs 收拢到 output/{request_id}/
    collected = save_task_outputs(user_id, req_id, {"catalog": saved})
    check("collected 包含 md (result.md)", collected.get("md") is not None and collected["md"].name == "result.md", str(collected))
    check("collected 包含 html (catalog.html)", collected.get("html") is not None and collected["html"].name == "catalog.html", str(collected))
    check("catalog.html 实际存在", collected["html"].is_file(), "")
    check("result.md 实际存在", collected["md"].is_file(), "")

    # 4. 验证 _output_file_name 返回 catalog.html
    out_name = _output_file_name("catalog", user_id, "高中物理", collected)
    check("_output_file_name 返回 catalog.html", out_name == "catalog.html", out_name)

    # 5. 验证 resolve_output_file 可下载 catalog.html 与 result.md
    dl_html = resolve_output_file(user_id, req_id, "catalog.html")
    check("resolve_output_file 成功定位 catalog.html", dl_html is not None and dl_html.name == "catalog.html", str(dl_html))
    dl_md = resolve_output_file(user_id, req_id, "result.md")
    check("resolve_output_file 成功定位 result.md", dl_md is not None and dl_md.name == "result.md", str(dl_md))

    # 清理测试目录
    shutil.rmtree(PROJECT_ROOT / "data" / user_id, ignore_errors=True)


def test_action_items_render() -> None:
    """验证待办事项卡片式清单（4个核心维度、自适应输出、无原句）及降级拼装。"""
    from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender
    from domains.meeting.memory.render import _parse_actions_from_text, render_actions_html

    # 1. 结构化草稿测试（含具象短语话题多事项聚合）
    state = {
        "lines": {
            "actions": {
                "draft": {
                    "my_actions": [
                        {
                            "category": "音视频SDK推流适配",
                            "task": "完成音视频推流协议适配与压测",
                            "owner": "张伟",
                            "deadline": "周五前",
                            "deliverable": "压测报告及文档",
                            "dependency": "需后端先提供鉴权Token",
                            "priority": "high",
                            "evidence": "张伟周五前把推流适配好",
                        },
                        {
                            "category": "音视频SDK推流适配",
                            "task": "与基础架构团队联调鉴权网关",
                            "owner": "张伟",
                            "priority": "medium",
                            "evidence": "张伟再跟架构联调一下",
                        },
                    ],
                    "delegated_actions": [
                        {
                            "category": "数据看表口径梳理",
                            "task": "梳理数据看表口径",
                            "owner": "李莉",
                            "deadline": "09-28",
                            "priority": "medium",
                            "evidence": "李莉把看表口径理一下",
                        },
                    ],
                    "unassigned_actions": [
                        {
                            "category": "预发布环境压测机申请",
                            "task": "申请预发布压测机器",
                            "deliverable": "机器分配就绪",
                            "evidence": "尽快去运维申请压测机",
                        },
                    ],
                }
            }
        }
    }
    draft_text = ActionItemsRender.render_draft(state)
    check("待办草稿包含[音视频SDK推流适配]业务板块主行", "1. **[音视频SDK推流适配]**" in draft_text, draft_text)
    check("包含具体任务及括号责任主体张伟", "完成音视频推流协议适配与压测(高优先 · 张伟)" in draft_text, draft_text)
    check("同板块事项聚拢在[音视频SDK推流适配]下", "与基础架构团队联调鉴权网关(中优先 · 张伟)" in draft_text, draft_text)
    check("包含[数据看表口径梳理]业务板块主行", "2. **[数据看表口径梳理]**" in draft_text, draft_text)
    check("包含[预发布环境压测机申请]业务板块主行", "3. **[预发布环境压测机申请]**" in draft_text, draft_text)
    check("未分配待办括号内仅为优先级无待认领", "申请预发布压测机器(中优先)" in draft_text and "待认领" not in draft_text, draft_text)
    check("不再单列责任主体行", "> 责任主体：" not in draft_text, draft_text)
    check("包含交付时限：周五前", "> 完成时限：周五前" in draft_text, draft_text)
    check("包含交付标准：压测报告及文档", "> 交付标准：压测报告及文档" in draft_text, draft_text)
    check("包含前置条件：需后端先提供鉴权Token", "> 前置条件：需后端先提供鉴权Token" in draft_text, draft_text)
    check("包含交付标准：机器分配就绪", "> 交付标准：机器分配就绪" in draft_text, draft_text)
    check("彻底去除原句引用", '张伟周五前把推流适配好' not in draft_text, draft_text)
    check("无大标题分组", "## 一、重点待办" not in draft_text and "## 二、待分配" not in draft_text, draft_text)

    # 2. 空状态测试
    empty_state = {"lines": {"actions": {"draft": {}}}}
    empty_text = ActionItemsRender.render_draft(empty_state)
    check("空待办输出暂无明确待办事项", empty_text == "暂无明确待办事项", empty_text)

    # 3. HTML 与解析测试
    parsed = _parse_actions_from_text(draft_text)
    check("文本能正确解析出 4 条待办", len(parsed) == 4, str(parsed))
    check("解析项 1 业务板块正确", parsed[0].get("category") == "音视频SDK推流适配", str(parsed[0]))
    check("解析项 1 包含责任人张伟", parsed[0].get("owner") == "张伟", str(parsed[0]))
    check("解析项 1 包含交付物", parsed[0].get("deliverable") == "压测报告及文档", str(parsed[0]))
    check("解析项 1 包含依赖", parsed[0].get("dependency") == "需后端先提供鉴权Token", str(parsed[0]))
    check("解析项 2 同属音视频推流适配", parsed[1].get("category") == "音视频SDK推流适配", str(parsed[1]))
    check("解析项 4 无未确定责任人", not parsed[3].get("owner"), str(parsed[3]))
    html = render_actions_html("待办事项清单", draft_text)
    check("HTML 公文流渲染成功包含 ck-flow-item", "ck-flow-item" in html, html[:200])


    # 4. ActionItemsReport 校验测试（确保多余 category, deliverable, dependency 不报错）
    from domains.meeting.reports import ActionItemsReport
    report_data = {
        "actions": [
            {
                "category": "接口联调",
                "task": "完成音视频推流协议适配与压测",
                "owner": "张伟",
                "deadline": "周五前",
                "deliverable": "压测报告及文档",
                "dependency": "需后端先提供鉴权Token",
                "priority": "high",
                "status": "explicit",
                "evidence": "张伟周五前把推流适配好",
                "confidence": "high",
            }
        ],
        "quality_warning": None,
        "personalized_text": None,
    }
    validated_report = ActionItemsReport.validate(report_data)
    check("ActionItemsReport 校验成功通过且保留扩展字段", validated_report.actions[0]["category"] == "接口联调", str(validated_report))


def test_risk_items_render() -> None:
    """验证风险分析卡片式清单（4个核心维度、自适应输出、无原句）及降级拼装。"""
    from domains.meeting.tasks.risks.steps.risks_render import RiskRender
    from domains.meeting.memory.render import _parse_risks_from_text, render_risks_html

    # 1. 结构化草稿测试（含具象短语话题多风险聚合）
    state = {
        "lines": {
            "risks": {
                "draft": {
                    "risks": [
                        {
                            "category": "核心网关压测流控与断流",
                            "risk": "核心路由在压测 QPS 超过 2000 时出现频繁断流",
                            "severity": "high",
                            "impact": "大促峰值期间接入层存在服务雪崩风险",
                            "mitigation": "周工本周内完成异步队列削峰改造并组织复测",
                            "owner": "周工",
                            "source": "张工说QPS一上两千就断流",
                        },
                        {
                            "category": "核心网关压测流控与断流",
                            "risk": "鉴权网关跨机房调用存在单点超时抖动",
                            "severity": "medium",
                            "impact": "高峰期引发级联超时重试，拖垮下游服务",
                            "mitigation": "增设本地缓存与降级熔断开关",
                            "owner": "周工",
                        },
                        {
                            "category": "跨团队基础鉴权Token审批",
                            "risk": "跨团队联调所需的基础鉴权 Token 审批流程过长",
                            "severity": "high",
                            "impact": "直接导致音视频推流 SDK 联调进度延期 1-2 天",
                            "mitigation": None,
                            "owner": None,
                            "source": "审批卡了三天了",
                        },
                        {
                            "category": "老旧机型暗黑模式对比度",
                            "risk": "部分老旧机型在暗黑模式下存在文本对比度缺失",
                            "severity": "low",
                            "impact": "极端夜间场景下轻微影响用户阅读体验",
                            "mitigation": "",
                            "owner": "",
                        },
                    ]
                }
            }
        }
    }
    draft_text = RiskRender.render_draft(state)
    check("风险草稿包含[核心网关压测流控与断流]业务板块主行", "1. **[核心网关压测流控与断流]**" in draft_text, draft_text)
    check("包含具体隐患及内联评级与责任人周工", "核心路由在压测 QPS 超过 2000 时出现频繁断流(高风险 · 周工)" in draft_text, draft_text)
    check("同板块事项聚拢在[核心网关压测流控与断流]下", "鉴权网关跨机房调用存在单点超时抖动(中风险 · 周工)" in draft_text, draft_text)
    check("包含[跨团队基础鉴权Token审批]业务板块主行", "2. **[跨团队基础鉴权Token审批]**" in draft_text, draft_text)
    check("未指定责任人时不输出待认领", "跨团队联调所需的基础鉴权 Token 审批流程过长(高风险)" in draft_text and "待认领" not in draft_text, draft_text)
    check("包含[老旧机型暗黑模式对比度]业务板块主行", "3. **[老旧机型暗黑模式对比度]**" in draft_text, draft_text)
    check("不再单列风险级别行", "> 风险级别：" not in draft_text, draft_text)
    check("不再单列责任主体行", "> 责任主体：" not in draft_text, draft_text)
    check("包含潜在危害：大促峰值期间接入层存在服务雪崩风险", "> 潜在危害：大促峰值期间接入层存在服务雪崩风险" in draft_text, draft_text)
    check("包含应对措施：周工本周内完成异步队列削峰改造并组织复测", "> 应对措施：周工本周内完成异步队列削峰改造并组织复测" in draft_text, draft_text)
    check("无应对措施时自适应隐去整行", "应对措施：无" not in draft_text and "应对措施：未提及" not in draft_text, draft_text)
    check("彻底去除原句引用", "张工说QPS一上两千就断流" not in draft_text, draft_text)
    check("无大标题分组", "## 一、高风险" not in draft_text and "## 二、中低风险" not in draft_text, draft_text)

    # 2. 空状态测试
    empty_state = {"lines": {"risks": {"draft": {}}}}
    empty_text = RiskRender.render_draft(empty_state)
    check("空风险输出暂无明确风险事项", empty_text == "暂无明确风险事项", empty_text)

    # 3. HTML 与解析测试
    parsed = _parse_risks_from_text(draft_text)
    check("文本能正确解析出 4 条风险", len(parsed) == 4, str(parsed))
    check("解析项 1 业务板块正确", parsed[0].get("category") == "核心网关压测流控与断流", str(parsed[0]))
    check("解析项 1 严重程度为 high", parsed[0].get("severity") == "high", str(parsed[0]))
    check("解析项 1 责任人为周工", parsed[0].get("owner") == "周工", str(parsed[0]))
    check("解析项 1 包含应对方案", "削峰改造" in str(parsed[0].get("mitigation")), str(parsed[0]))
    check("解析项 2 同属网关架构", parsed[1].get("category") == "核心网关压测流控与断流", str(parsed[1]))
    check("解析项 3 无责任人", not parsed[2].get("owner"), str(parsed[2]))
    check("解析项 4 严重程度为 low", parsed[3].get("severity") == "low", str(parsed[3]))
    html = render_risks_html("风险分析", draft_text)

    check("HTML 公文流渲染成功包含 ck-flow-item", "ck-flow-item" in html, html[:200])
    check("HTML 公文流不包含待认领", "待认领" not in html, html[:200])


def test_general_minutes_title_fixed() -> None:
    """通用纪要：模板与产物落盘顶部强制固定为 # 通用纪要，不被动态 headline 覆盖。"""
    from app.config import resolve_template_format, template_registry
    from domains.meeting.reports import MinutesReport
    from core.runner.context import load_domain
    from infra.exporters.outputs import save_report_artifacts

    # 1. 模板注册表 format 保留 # 通用纪要
    item = template_registry().get("daily_journal_general_minutes")
    check("模板注册表中通用纪要存在", item is not None, str(item))
    if item:
        fmt = str(item.get("format") or "")
        check("通用纪要模板 format 顶部保留 # 通用纪要", fmt.startswith("# 通用纪要"), fmt[:40])

    resolved = resolve_template_format("general_minutes")
    check("resolve_template_format 包含 # 通用纪要", "# 通用纪要" in resolved, resolved[:80])

    # 2. save_report_artifacts 落盘测试：即使 report.title 携带动态 headline，落盘正文与 HTML 均固定为 通用纪要
    ctx = load_domain("meeting", Path("."))
    report = MinutesReport(
        title="关于音视频与长文本优化的研讨",  # 模拟从草稿提取出的动态 headline
        personalized_minutes="# 通用纪要\n\n## 全文摘要\n本场会议围绕音视频SDK展开讨论。\n\n## 要点梳理\n1. **[音视频SDK]**\n   > 完成推流适配(张伟)",
    )
    with tempfile.TemporaryDirectory() as td:
        ctx.output_dir = Path(td)
        saved = save_report_artifacts(ctx, "minutes", report, gate_ok=True)
        md_path = saved.get("text")
        check("通用纪要产物保存成功", md_path is not None and md_path.is_file(), str(saved))
        if md_path and md_path.is_file():
            saved_md = md_path.read_text(encoding="utf-8")
            check("落盘 Markdown 顶部固定为 # 通用纪要", saved_md.startswith("# 通用纪要"), saved_md[:50])
            check("落盘 Markdown 不包含动态 headline H1", "# 关于音视频与长文本优化的研讨" not in saved_md, saved_md[:50])

        # 3. 补充测试：即使模型输出时偶然遗漏 # 通用纪要，outputs.py 仍强制补充 # 通用纪要 而非动态 headline
        report_no_h1 = MinutesReport(
            title="关于音视频与长文本优化的研讨",
            personalized_minutes="## 全文摘要\n本场会议围绕音视频SDK展开讨论。\n\n## 要点梳理\n1. **[音视频SDK]**\n   > 完成推流适配(张伟)",
        )
        saved_no_h1 = save_report_artifacts(ctx, "minutes", report_no_h1, gate_ok=True)
        md_no_h1 = saved_no_h1.get("text")
        if md_no_h1 and md_no_h1.is_file():
            saved_md_no_h1 = md_no_h1.read_text(encoding="utf-8")
            check("输出遗漏首行时强制补充 # 通用纪要", saved_md_no_h1.startswith("# 通用纪要"), saved_md_no_h1[:50])
            check("强制补充时未被动态 headline 覆盖", "# 关于音视频与长文本优化的研讨" not in saved_md_no_h1, saved_md_no_h1[:50])


from tests.integration.core.test_api_routes import (
    test_async_api_routes as _test_async_api_routes,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _test_user_profile_path_safety()
        _test_selection_matrix(tmp)
        _test_broken_user_profile(tmp)
        _test_sanitize_and_merge(tmp)
        _test_missing_role_template(tmp)
    _test_role_mapping()
    test_domain_hooks_registry()
    test_tasklines_registration()
    test_notes_review_and_quiz_tasklines()
    _test_agenda_minutes_input_assembly()
    test_request_schema_and_validation()
    test_catalog_output_artifacts_and_download()
    test_action_items_render()
    test_risk_items_render()
    test_general_minutes_title_fixed()
    _test_async_api_routes()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0



if __name__ == "__main__":
    sys.exit(main())
