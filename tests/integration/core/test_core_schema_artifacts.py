# 拆分自原大文件，保留：test_request_schema_and_validation, test_catalog_output_artifacts_and_download, test_general_minutes_title_fixed…

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

def test_request_schema_and_validation() -> None:
    """验证请求体字段重构（memory 顶层、extra.time、extra.catalog）与 14 任务前置校验。"""
    from app.config import PROJECT_ROOT
    from app.requirements import REQUIRED_FIELDS, check_required
    from app.schemas import Extra, TaskRequest
    from app.tasks import ApiError, _prepare

    # 1. 验证 TaskRequest 数据模型严格层级归位 (memory 仅在顶层，time 仅在 extra)
    # 1.1 memory 字段归位
    r1 = TaskRequest(memory=True)
    expect(r1.memory is True, "TaskRequest 顶层支持 memory=True", "")
    expect("memory" not in Extra.model_fields, "Extra 模型中不再包含 memory 字段", "")

    # 1.2 time 字段归位
    r2 = TaskRequest(extra=Extra(time="2026-06-15 10:00"))
    expect(r2.extra.time == "2026-06-15 10:00", "Extra 正确保存 time 字段", "")
    expect("time" not in TaskRequest.model_fields, "TaskRequest 模型中不再包含 time 字段", "")

    # 1.3 验证传错层级不会产生自动拷贝
    r3 = TaskRequest.model_validate({"extra": {"memory": True}})
    expect(r3.memory is False, "传在 extra 的 memory 不再自动提升", "")

    r4 = TaskRequest.model_validate({"time": "2026-06-15 10:00"})
    expect(r4.extra.time == "", "传在顶层的 time 不再自动同步到 extra", "")

    # 1.3 extra.catalog 显式指定及 docs 兼容提取
    r5 = TaskRequest(extra=Extra(catalog="20261001_100000.json"))
    expect(r5.extra.catalog == "20261001_100000.json", "Extra 支持 catalog 字段", "")

    r6 = TaskRequest.model_validate({"docs": ["phy_8b4dccc8.json", "teacher.txt"]})
    expect(r6.extra.catalog == "phy_8b4dccc8.json", "docs 中的 .json 自动移入 extra.catalog", "")
    expect(r6.docs == ["teacher.txt"], "docs 剥离 .json 仅保留真实附件", str(r6.docs))

    # 2. 验证 14 任务必填校验矩阵 (check_required)
    expect(len(REQUIRED_FIELDS) == 14, "REQUIRED_FIELDS 包含全量 14 个任务", str(len(REQUIRED_FIELDS)))

    # 2.1 mindmap 必传 transcript 与 user_id
    m_mindmap_empty = check_required("mindmap", TaskRequest(), "")
    expect(len(m_mindmap_empty) == 2, "mindmap 缺参时拦截 user_id 与 transcript", str(m_mindmap_empty))
    m_mindmap_ok = check_required("mindmap", TaskRequest(texts={"transcript": "会议记录"}), "u1")
    expect(len(m_mindmap_ok) == 0, "mindmap 传参完整时通过校验", str(m_mindmap_ok))

    # 2.2 graph 仅需 texts 或 docs 之一
    m_graph_empty = check_required("graph", TaskRequest(), "u1")
    expect(len(m_graph_empty) == 1, "graph 无输入时拦截 texts_or_docs", str(m_graph_empty))
    m_graph_text = check_required("graph", TaskRequest(texts={"notes": "概念A->概念B"}), "u1")
    expect(len(m_graph_text) == 0, "graph 仅传 notes 文本时通过校验", str(m_graph_text))
    m_graph_docs = check_required("graph", TaskRequest(docs=["notes.txt"]), "u1")
    expect(len(m_graph_docs) == 0, "graph 仅传 docs 文件时通过校验", str(m_graph_docs))

    # 2.3 checklist 仅需 extra.subject（docs 与 catalog 均为可选）
    m_chk_empty = check_required("checklist", TaskRequest(), "u1")
    expect(len(m_chk_empty) == 1 and "subject" in m_chk_empty[0], "checklist 缺 subject 时拦截", str(m_chk_empty))
    m_chk_ok = check_required("checklist", TaskRequest(extra=Extra(subject="physics")), "u1")
    expect(len(m_chk_ok) == 0, "checklist 仅传 subject 时即可通过必填校验", str(m_chk_ok))

    # 2.4 agenda_minutes 必传 user_id, transcript 与 docs（或 extra.agenda_txt 纯文本）
    m_agenda_empty = check_required("agenda_minutes", TaskRequest(), "")
    expect(len(m_agenda_empty) == 3, "agenda_minutes 缺参时拦截 user_id、transcript 与 docs", str(m_agenda_empty))
    m_agenda_no_docs = check_required("agenda_minutes", TaskRequest(texts={"transcript": "会议记录"}), "u1")
    expect(len(m_agenda_no_docs) == 1 and "docs" in m_agenda_no_docs[0], "agenda_minutes 缺少 docs 时拦截", str(m_agenda_no_docs))
    m_agenda_docs_ok = check_required("agenda_minutes", TaskRequest(texts={"transcript": "会议记录"}, docs=["agenda.txt"]), "u1")
    expect(len(m_agenda_docs_ok) == 0, "agenda_minutes 传 docs 时通过校验", str(m_agenda_docs_ok))
    m_agenda_txt_ok = check_required("agenda_minutes", TaskRequest(texts={"transcript": "会议记录"}, extra=Extra(agenda_txt="1. 议题A")), "u1")
    expect(len(m_agenda_txt_ok) == 0, "agenda_minutes 传 extra.agenda_txt 时通过校验", str(m_agenda_txt_ok))

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
    expect("【目录文件】20261001_100000.json" in chk_input, "checklist 正确注入 extra.catalog", chk_input)

    # 3.2 兼容老客户端 docs 传入 catalog.json
    req_chk_legacy = TaskRequest.model_validate({
        "docs": ["20261001_100000.json"],
        "extra": {"subject": "physics"},
    })
    prep_chk_legacy = _prepare("notes", "checklist", req_chk_legacy, "u_test_schema")
    chk_input_legacy = prep_chk_legacy.extra_line_inputs.get("checklist", "")
    expect("【目录文件】20261001_100000.json" in chk_input_legacy, "checklist 兼容老入参 docs 注入 catalog", chk_input_legacy)

    # 3.3 不存在的 catalog 报 404
    req_chk_notfound = TaskRequest(extra=Extra(subject="physics", catalog="not_exist.json"))
    try:
        _prepare("notes", "checklist", req_chk_notfound, "u_test_schema")
        expect(False, "不存在的 catalog 抛 404", "未抛出异常")
    except ApiError as exc:
        expect(exc.status == 404 and "not_exist.json" in exc.message, "不存在的 catalog 抛 404", exc.message)

    # 3.4 memory 与 time 正确传递到 _Prepared
    req_minutes = TaskRequest(
        texts={"transcript": "发言者1：开会讨论技术架构。"},
        memory=True,
        extra=Extra(time="2026-06-15 10:00", project="proj_alpha"),
    )
    prep_min = _prepare("meeting", "minutes", req_minutes, "u_test_schema")
    expect(prep_min.memory is True, "prep.memory 正确获取顶层 memory 开关", "")
    expect(prep_min.time == "2026-06-15 10:00", "prep.time 正确获取 extra.time", prep_min.time)

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
    expect("cat-doc" in html, "catalog HTML 包含根容器 cat-doc", "")
    expect("高中物理" in html, "catalog HTML 包含课程名", "")
    expect("目录层级树" in html, "catalog HTML 包含目录层级树", "")
    expect("参考系的选择" in html and "核心概念" in html, "catalog HTML 包含知识点卡片与标签", "")
    expect("★★★★☆" in html, "catalog HTML 包含星级评分", "")

    # 验证空 draft
    empty_html = build_catalog_html({})
    expect("cat-doc" in empty_html, "空 catalog HTML 仍包含 cat-doc 容器", "")
    expect("没有整理出可用目录" in empty_html, "空 catalog HTML 包含空提示", "")

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
    expect("text" in saved and saved["text"].name == "result.md", "save_report_artifacts 成功产出 text (result.md)", str(saved))
    expect("html" in saved and saved["html"].name == "catalog.html", "save_report_artifacts 成功产出 html (catalog.html)", str(saved))

    # 3. 验证 save_task_outputs 收拢到 output/{request_id}/
    collected = save_task_outputs(user_id, req_id, {"catalog": saved})
    expect(collected.get("md") is not None and collected["md"].name == "result.md", "collected 包含 md (result.md)", str(collected))
    expect(collected.get("html") is not None and collected["html"].name == "catalog.html", "collected 包含 html (catalog.html)", str(collected))
    expect(collected["html"].is_file(), "catalog.html 实际存在", "")
    expect(collected["md"].is_file(), "result.md 实际存在", "")

    # 4. 验证 _output_file_name 返回 catalog.html
    out_name = _output_file_name("catalog", user_id, "高中物理", collected)
    expect(out_name == "catalog.html", "_output_file_name 返回 catalog.html", out_name)

    # 5. 验证 resolve_output_file 可下载 catalog.html 与 result.md
    dl_html = resolve_output_file(user_id, req_id, "catalog.html")
    expect(dl_html is not None and dl_html.name == "catalog.html", "resolve_output_file 成功定位 catalog.html", str(dl_html))
    dl_md = resolve_output_file(user_id, req_id, "result.md")
    expect(dl_md is not None and dl_md.name == "result.md", "resolve_output_file 成功定位 result.md", str(dl_md))

    # 清理测试目录
    shutil.rmtree(PROJECT_ROOT / "data" / user_id, ignore_errors=True)


def test_general_minutes_title_fixed() -> None:
    """通用纪要：模板 format 剥离 # 通用纪要 文件头，落盘时与全量模板统一使用真实会议标题作为 H1。"""
    from app.config import resolve_template_format, template_registry
    from domains.meeting.reports import MinutesReport
    from core.runner.context import load_domain
    from infra.exporters.outputs import save_report_artifacts

    # 1. 模板注册表 format 剥离文件头 # 通用纪要，与其他 28 套模板完全一致
    item = template_registry().get("daily_journal_general_minutes")
    expect(item is not None, "模板注册表中通用纪要存在", str(item))
    if item:
        fmt = str(item.get("format") or "")
        expect(not fmt.startswith("# 通用纪要"), "通用纪要模板 format 剥离 # 通用纪要", fmt[:40])
        expect("## [全文摘要]" in fmt, "通用纪要模板 format 从正文栏目开始", fmt[:40])

    resolved = resolve_template_format("general_minutes")
    expect("# 通用纪要" not in resolved, "resolve_template_format 不包含 # 通用纪要", resolved[:80])
    expect("## [全文摘要]" in resolved, "resolve_template_format 包含栏目 ## [全文摘要]", resolved[:80])

    # 2. save_report_artifacts 落盘测试：正文无 H1 标题时，落盘文件统一将动态 headline 作为 # 标题
    ctx = load_domain("meeting", Path("."))
    report = MinutesReport(
        title="关于音视频与长文本优化的研讨",  # 模拟从草稿提取出的动态 headline
        personalized_minutes="## 全文摘要\n本场会议围绕音视频SDK展开讨论。\n\n## 要点梳理\n1. **[音视频SDK]**\n   > 完成推流适配(张伟)",
    )
    with tempfile.TemporaryDirectory() as td:
        ctx.output_dir = Path(td)
        saved = save_report_artifacts(ctx, "minutes", report, gate_ok=True)
        md_path = saved.get("text")
        expect(md_path is not None and md_path.is_file(), "通用纪要产物保存成功", str(saved))
        if md_path and md_path.is_file():
            saved_md = md_path.read_text(encoding="utf-8")
            expect(saved_md.startswith("# 关于音视频与长文本优化的研讨"), "落盘 Markdown 顶部使用动态 headline", saved_md[:50])
            expect("# 通用纪要" not in saved_md, "落盘 Markdown 不包含死代码 # 通用纪要", saved_md[:50])

        # 3. 补充测试：若正文已有 # 标题（如自定义标题），则不再重复前缀叠加
        report_with_h1 = MinutesReport(
            title="关于音视频与长文本优化的研讨",
            personalized_minutes="# 自定义会议主标题\n\n## 全文摘要\n本场会议围绕音视频SDK展开讨论。\n\n## 要点梳理\n1. **[音视频SDK]**\n   > 完成推流适配(张伟)",
        )
        saved_with_h1 = save_report_artifacts(ctx, "minutes", report_with_h1, gate_ok=True)
        md_with_h1 = saved_with_h1.get("text")
        if md_with_h1 and md_with_h1.is_file():
            saved_md_with_h1 = md_with_h1.read_text(encoding="utf-8")
            expect(saved_md_with_h1.startswith("# 自定义会议主标题"), "正文已有 H1 时保留原标题", saved_md_with_h1[:50])
