"""tools/core 零 LLM 自测：画像选档（``profile=user`` → data/{uid}/user.json）、清洗、职业模板合并。

用法::

    python -m tests.test_core
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from tools.core.profiles import (
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
    dev_raw = json.loads((root / "assets" / "profiles" / "developer.json").read_text(encoding="utf-8"))
    check("职业文件仍按职业模板分类（清洗只作用 user.json）",
          classify_profile(resolve_role_template(dev_raw, root / "assets" / "profiles")) == "role_template", "")
    check("is_user_profile_file 只认 user.json",
          is_user_profile_file(ui) and not is_user_profile_file(root / "assets" / "profiles" / "developer.json"), "")

    # 画像字段必须真的被 UserIdentity 承载（不在 dataclass 里的键会被 filter_identity_fields 静默丢掉）
    from domain.meeting.models_base import UserIdentity as MeetingIdentity

    identity = MeetingIdentity(**filter_identity_fields(merged, MeetingIdentity))
    check("UserIdentity 承载 name_aliases/personality/preferences",
          identity.name == "赵衡"
          and identity.name_aliases == ["小赵", "赵工"]
          and identity.personality == "务实，讨厌含糊的截止日期"
          and identity.preferences == ["先写我的待办和接口依赖"],
          str(identity))

    # 选档的最终后果：模式判定（personal 会跑视角建模；objective 跳过）
    from tools.core.domain_engine import DomainNodes

    mode = DomainNodes._mode_label(
        {"user": identity.model_dump(), "objective_perspective": False}
    )
    check("有 user.json（真人）→ 视角模式 personal", mode == "personal", mode)
    obj_identity = MeetingIdentity(**filter_identity_fields(
        json.loads((root / "assets" / "profiles" / "object.json").read_text(encoding="utf-8")),
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
    from tools.core.domain_engine import DomainNodes
    from tools.core.domain_hooks import DomainHooks, clear, hooks_for, register, registered

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
    from domain.meeting.tasks.minutes.steps.minutes_render import compact_untemplated_minutes

    check("压缩钩子：纪要类线走域内压缩，其它线原样返回",
          hooks.compact_plain("minutes", "a\n\n\nb") == compact_untemplated_minutes("a\n\n\nb")
          and hooks.compact_plain("actions", "a\n\n\nb") == "a\n\n\nb",
          repr(hooks.compact_plain("minutes", "a\n\n\nb")))

    from domain.meeting.orchestrator import MeetingAgentSystem
    from domain.notes.orchestrator import NotesAgentSystem

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
        module = sys.modules.get(f"domain.{domain_name}.hooks")
        if module is None:
            importlib.import_module(f"domain.{domain_name}.hooks")
            module = sys.modules[f"domain.{domain_name}.hooks"]
        register(domain_name, importlib.reload(module).HOOKS)
    check("测试收尾：两域钩子已复位（避免影响同进程其它套件）",
          set(registered()) >= {"meeting", "notes"}, str(sorted(registered())))


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
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
