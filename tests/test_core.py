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


def test_user_profile_path_safety() -> None:
    root = Path("/repo")
    check("路径固定为 data/{safe_id}/user.json",
          user_profile_path("1", root) == root / "data" / "1" / "user.json",
          str(user_profile_path("1", root)))
    check("user_id 空 → 空 Path", user_profile_path("", root) == Path(""), "")
    traversal = user_profile_path("../../etc", root)
    check("user_id 不能穿越目录",
          ".." not in traversal.parts and traversal.parent.parent.name == "data",
          str(traversal))


def test_selection_matrix(tmp_path: Path) -> None:
    """extra.profile 选档：空=默认档（客观，不读 user.json）；user=真人；职业名/显式客观各自独立。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = root / "data" / "1" / "user.json"

    # ① 无档案 + 空值 → 客观
    obj = resolve_profile_file("", domain="meeting", user_id="1", project_root=root)
    check("空值 + 无 user.json → 客观全员", obj.name == "object.json", str(obj))

    # ② 有档案 + 空值 → 仍是客观（2026-09-21 改口径：真人要显式 profile=user）
    _write(ui, USER_OK)
    still_obj = resolve_profile_file("", domain="meeting", user_id="1", project_root=root)
    check("空值 + 有 user.json → 不再自动发现，仍走默认档",
          still_obj.name == "object.json", str(still_obj))

    # ③ profile="user" → 真人档案
    check("profile=user → user.json",
          resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == ui, "")

    # ④ 显式客观（与空值同档）
    for value in ("objective", "object"):
        path = resolve_profile_file(value, domain="meeting", user_id="1", project_root=root)
        check(f"profile={value} → 客观全员", path.name == "object.json", str(path))

    # ⑤ 职业模板
    dev = resolve_profile_file("developer", domain="meeting", user_id="1", project_root=root)
    check("profile=developer → 职业模板", dev.name == "developer.json", str(dev))

    # ⑥ 未知职业名 → 空 Path（调用方 400）
    check("未知职业名 → 空 Path（400）",
          resolve_profile_file("nope", domain="meeting", user_id="1", project_root=root) == Path(""), "")

    # ⑦ 无档案时 profile=user → 空 Path（400），不静默降级
    ui.unlink()
    check("无档案 + profile=user → 空 Path（400）",
          resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path(""), "")
    check("无档案 + 空值 → 客观",
          resolve_profile_file("", domain="meeting", user_id="1", project_root=root).name == "object.json", "")

    # ⑧ 其它用户的档案互不可见（profile=user 只看自己那份）
    _write(root / "data" / "2" / "user.json", USER_OK)
    check("按 user_id 隔离：1 号用户无档案 → profile=user 报 400",
          resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path(""), "")
    check("2 号用户 profile=user → 认自己那份",
          resolve_profile_file("user", domain="meeting", user_id="2", project_root=root)
          == root / "data" / "2" / "user.json", "")


def test_broken_user_profile(tmp_path: Path) -> None:
    """坏档案（非对象 / 缺 name / 坏 JSON）→ 当没有档案，不阻断请求。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = root / "data" / "1" / "user.json"
    cases = {
        "缺 name": {"name_aliases": ["小赵"]},
        "name 全空白": {"name": "   "},
        "坏 JSON": "{not json",
        "不是对象": ["赵衡"],
    }
    for label, payload in cases.items():
        _write(ui, payload)
        check(f"user.json {label} → 按无档案处理", read_user_profile(ui) is None, "")
        check(f"user.json {label} → profile=user 报 400（不静默降级）",
              resolve_profile_file("user", domain="meeting", user_id="1", project_root=root) == Path(""), "")
        check(f"user.json {label} → 空值仍走默认档（客观）",
              resolve_profile_file("", domain="meeting", user_id="1", project_root=root).name == "object.json", "")
    _write(ui, USER_OK)
    check("合法档案可读且必填项非空", (read_user_profile(ui) or {}).get("name") == "赵衡", "")


def test_sanitize_and_merge(tmp_path: Path) -> None:
    """清洗 + 挂职业底：perspective 忽略、persona_type 置空、模板作底、真人字段覆盖。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = _write(root / "data" / "1" / "user.json", dict(USER_OK, perspective="objective", persona_type="role_template"))
    raw = read_user_profile(ui) or {}
    cleaned = sanitize_user_profile(raw)
    check("清洗后忽略 perspective（有档案即真人）", "perspective" not in cleaned, str(cleaned))
    check("清洗后 persona_type 强制为空（姓名不被当职业通称）", cleaned.get("persona_type") is None, str(cleaned))

    merged = resolve_role_template(cleaned, ui.parent)
    check("挂职业底：name 用真名（不是模板的「开发人员」）", merged.get("name") == "赵衡", str(merged.get("name")))
    check("挂职业底：未写的 focus_areas 继承模板", bool(merged.get("focus_areas")), str(merged.get("focus_areas")))
    check("挂职业底：merged 仍是真人身份", merged.get("persona_type") is None, str(merged.get("persona_type")))
    check("挂职业底：保留引用来源 role_template=developer", merged.get("role_template") == "developer", "")
    check("分类：清洗后按真人（不是职业）", classify_profile(merged) == "person", classify_profile(merged))
    # 自写字段整段替换（列表不拼接）
    cleaned2 = dict(cleaned, focus_areas=["接口契约与依赖"])
    merged2 = resolve_role_template(cleaned2, ui.parent)
    check("自己写了 focus_areas → 整段替换（不拼接模板）",
          merged2.get("focus_areas") == ["接口契约与依赖"], str(merged2.get("focus_areas")))
    # 职业文件本身不受清洗影响
    prof_dir = (root / "resources" / "profiles") if (root / "resources" / "profiles").is_dir() else (root / "assets" / "profiles")
    dev_raw = json.loads((prof_dir / "developer.json").read_text(encoding="utf-8"))
    check("职业文件仍按职业模板分类（清洗只作用 user.json）",
          classify_profile(resolve_role_template(dev_raw, prof_dir)) == "role_template", "")
    check("is_user_profile_file 只认 user.json",
          is_user_profile_file(ui) and not is_user_profile_file(prof_dir / "developer.json"), "")

    # 画像字段必须真的被 UserIdentity 承载（不在 dataclass 里的键会被 filter_identity_fields 静默丢掉）
    from domains.meeting.models_base import UserIdentity as MeetingIdentity

    identity = MeetingIdentity(**filter_identity_fields(merged, MeetingIdentity))
    check("UserIdentity 承载 name_aliases/personality/preferences",
          identity.name == "赵衡"
          and identity.name_aliases == ["小赵", "赵工"]
          and identity.personality == "务实，讨厌含糊的截止日期"
          and identity.preferences == ["先写我的待办和接口依赖"],
          str(identity))

    # 选档的最终后果：模式判定（personal 会跑视角建模；objective 跳过）
    from core.graph.nodes import DomainNodes

    mode = DomainNodes._mode_label(
        {"user": identity.model_dump(), "objective_perspective": False}
    )
    check("有 user.json（真人）→ 视角模式 personal", mode == "personal", mode)
    obj_identity = MeetingIdentity(**filter_identity_fields(
        json.loads((prof_dir / "object.json").read_text(encoding="utf-8")),
        MeetingIdentity,
    ))
    check("无 user.json（客观）→ 视角模式 objective（跳过视角建模）",
          DomainNodes._mode_label(
              {"user": obj_identity.model_dump(),
               "objective_perspective": obj_identity.perspective == "objective"}
          )
          == "objective",
          "")


def test_missing_role_template(tmp_path: Path) -> None:
    """role_template 指向不存在的职业 → 明确报错（不静默降级成无底真人）。"""
    tmp = tmp_path
    root = _root(tmp)
    ui = _write(root / "data" / "1" / "user.json", dict(USER_OK, role_template="nobody"))
    cleaned = sanitize_user_profile(read_user_profile(ui) or {})
    try:
        resolve_role_template(cleaned, ui.parent)
        check("role_template 不存在 → 抛错", False, "没有抛错")
    except ValueError as exc:
        check("role_template 不存在 → 抛错并指名 key", "nobody" in str(exc), str(exc))
    # 名字写坏（含路径穿越）同样拒绝
    for bad in ("../developer", "a/b"):
        try:
            resolve_role_template(dict(cleaned, role_template=bad), ui.parent)
            check(f"role_template={bad!r} → 拒绝", False, "没有抛错")
        except ValueError:
            check(f"role_template={bad!r} → 拒绝", True, "")


def test_role_mapping() -> None:
    """验证 role 字段映射到已有的职业 profile（算法、开发、测试等）。"""
    mapping = load_role_mapping()
    check("映射表成功加载且条目非空", bool(mapping) and len(mapping) > 10, str(len(mapping)))

    # 1. 算法工程师同义词与英文测试
    algorithm_aliases = ["算法", "算法人员", "算法工程师", "algorithm_engineer", "algorithm", "algo"]
    for alias in algorithm_aliases:
        mapped = resolve_role_to_template_key(alias)
        check(f"role映射：{alias!r} → algorithm_engineer", mapped == "algorithm_engineer", str(mapped))

    # 2. 其它常见职业映射
    check("role映射：开发 → developer", resolve_role_to_template_key("开发") == "developer", "")
    check("role映射：测试工程师 → tester", resolve_role_to_template_key("测试工程师") == "tester", "")
    check("role映射：产品经理 → product_manager", resolve_role_to_template_key("产品经理") == "product_manager", "")

    # 3. 未知职业返回 None（不报错）
    check("role映射：未知职业返回 None", resolve_role_to_template_key("未知职业") is None, "")

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
    check("合并后保留本人角色名称 role=算法工程师", merged.get("role") == "算法工程师", str(merged.get("role")))
    check("合并后标记职业模板来源 role_template=algorithm_engineer", merged.get("role_template") == "algorithm_engineer", str(merged.get("role_template")))
    check("合并后成功继承职责 responsibilities", len(merged.get("responsibilities", [])) >= 4, str(merged.get("responsibilities")))
    check("合并后成功继承关注领域 focus_areas", len(merged.get("focus_areas", [])) >= 5, str(merged.get("focus_areas")))
    check("合并后保留 focus_person 列表", merged.get("focus_person") == ["徐玥", "张工", "李总"], str(merged.get("focus_person")))
    check("合并后保留 focus_thing 列表", merged.get("focus_thing") == ["风控决策引擎", "端到端P99时延", "Q3交付排期"], str(merged.get("focus_thing")))



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


def test_agenda_minutes_input_assembly() -> None:
    """验证 agenda_minutes 支持 extra.agenda_txt 纯文本传参，并兼容老字段 agenda。"""
    from app.schemas import Extra, TaskRequest
    from app.tasks import _prepare

    # 1. 验证 Extra 模型解析
    e1 = Extra(agenda_txt="1. 汇报A\n2. 汇报B")
    check("Extra 支持 agenda_txt", e1.agenda_txt == "1. 汇报A\n2. 汇报B", "")
    e2 = Extra.model_validate({"agenda": "1. 汇报A\n2. 汇报B"})
    check("Extra 兼容老入参 agenda 自动映射到 agenda_txt", e2.agenda_txt == "1. 汇报A\n2. 汇报B", "")

    # 2. 验证 _prepare 提取 extra.agenda_txt
    req = TaskRequest(
        texts={"transcript": "发言者1：大家早上好，开始今天的会议。"},
        extra=Extra(agenda_txt="1. 议题一：大模型发布\n2. 议题二：算法压测"),
    )
    prep = _prepare("meeting", "agenda_minutes", req, "u123")
    check("line 为 agenda_minutes", prep.line == "agenda_minutes", "")
    agenda_input = prep.extra_line_inputs.get("agenda_minutes", "")
    check("extra_line_inputs 注入了 agenda_txt 文本", "1. 议题一：大模型发布" in agenda_input, agenda_input)


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
    check("包含具体任务及括号责任主体张伟", "完成音视频推流协议适配与压测(张伟)" in draft_text, draft_text)
    check("同板块事项聚拢在[音视频SDK推流适配]下", "与基础架构团队联调鉴权网关(张伟)" in draft_text, draft_text)
    check("包含[数据看表口径梳理]业务板块主行", "2. **[数据看表口径梳理]**" in draft_text, draft_text)
    check("包含[预发布环境压测机申请]业务板块主行", "3. **[预发布环境压测机申请]**" in draft_text, draft_text)
    check("未分配待办括号内为待认领", "申请预发布压测机器(待认领)" in draft_text, draft_text)
    check("不再单列责任主体行", "> 责任主体：" not in draft_text, draft_text)
    check("包含交付时限：周五前", "> 交付时限：周五前" in draft_text, draft_text)
    check("包含交付成果：压测报告及文档", "> 交付成果：压测报告及文档" in draft_text, draft_text)
    check("包含前置依赖：需后端先提供鉴权Token", "> 前置依赖：需后端先提供鉴权Token" in draft_text, draft_text)
    check("包含交付成果：机器分配就绪", "> 交付成果：机器分配就绪" in draft_text, draft_text)
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
    check("解析项 4 责任人为待认领", parsed[3].get("owner") == "待认领", str(parsed[3]))
    html = render_actions_html("待办事项清单", draft_text)
    check("HTML 表格渲染成功包含 tr", "<tr>" in html, html[:200])


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
    check("未指定责任人时标注待认领", "跨团队联调所需的基础鉴权 Token 审批流程过长(高风险 · 待认领)" in draft_text, draft_text)
    check("包含[老旧机型暗黑模式对比度]业务板块主行", "3. **[老旧机型暗黑模式对比度]**" in draft_text, draft_text)
    check("不再单列风险级别行", "> 风险级别：" not in draft_text, draft_text)
    check("不再单列责任主体行", "> 责任主体：" not in draft_text, draft_text)
    check("包含潜在影响：大促峰值期间接入层存在服务雪崩风险", "> 潜在影响：大促峰值期间接入层存在服务雪崩风险" in draft_text, draft_text)
    check("包含应对方案：周工本周内完成异步队列削峰改造并组织复测", "> 应对方案：周工本周内完成异步队列削峰改造并组织复测" in draft_text, draft_text)
    check("无应对方案时自适应隐去整行", "应对方案：无" not in draft_text and "应对方案：未提及" not in draft_text, draft_text)
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
    check("解析项 3 责任人为待认领", parsed[2].get("owner") == "待认领", str(parsed[2]))
    check("解析项 4 严重程度为 low", parsed[3].get("severity") == "low", str(parsed[3]))
    html = render_risks_html("风险分析", draft_text)

    check("HTML 表格渲染成功包含 tr", "<tr>" in html, html[:200])
    check("HTML 表格包含责任主体列", "责任主体" in html, html[:200])


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



def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        test_user_profile_path_safety()
        test_selection_matrix(tmp)
        test_broken_user_profile(tmp)
        test_sanitize_and_merge(tmp)
        test_missing_role_template(tmp)
    test_role_mapping()
    test_domain_hooks_registry()
    test_tasklines_registration()
    test_action_items_render()
    test_risk_items_render()
    test_general_minutes_title_fixed()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
