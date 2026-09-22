"""草稿/原文抽取：各线的 ``*_from_context`` 与共享实现（``domain_engine_text``）一致。

用法::

    python -m tests.test_draft_scrape

为什么值得单独一套（2026-09-21 收拢 10 处逐字重复实现时立的规矩）：这些函数按**中文字面
marker** 从渲染上下文里抠草稿 JSON——marker 错一个字符，那一栏就静默变空（不报错，只是没
内容），是线上最难发现的一类回归。所以既测共享实现本身，也逐个断言"调用点源码里写的
marker 确实能命中它自己的上下文"（marker 从 AST 读，避免测试与实现各抄一份）。
"""
from __future__ import annotations

import ast
import importlib
import inspect
import sys

from tools.core.domain_engine_text import scrape_draft, scrape_original

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


# (模块, 函数名, marker 数量) —— 与各线渲染/组装步骤里的委托调用一一对应
DRAFT_SITES = (
    ("domain.meeting.tasks.minutes_styles.steps.minutes_styles_render", "_draft_from_context", 1),
    ("domain.meeting.tasks.minutes_trace.steps.minutes_trace_render", "_draft_from_context", 1),
    ("domain.notes.tasks.catalog.display", "draft_from_context", 2),
    ("domain.notes.tasks.checklist.display", "draft_from_context", 2),
    ("domain.notes.tasks.quiz.display", "draft_from_context", 2),
    ("domain.notes.tasks.review.display", "draft_from_context", 2),
    ("domain.notes.tasks.graph.steps.graph_render", "_draft_from_context", 1),
    ("domain.notes.tasks.library.steps.library_render", "_draft_from_context", 2),
)
ORIG_SITES = (
    ("domain.notes.tasks.review.display", "original_from_context"),
    ("domain.notes.tasks.quiz.display", "original_from_context"),
)


def _markers_of(module: str, name: str) -> tuple[str, ...]:
    """从调用点源码里读回它传给共享实现的 marker（AST 求字面量，含转义也拿到真实值）。"""
    src = inspect.getsource(getattr(importlib.import_module(module), name))
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and (
            getattr(node.func, "attr", "") or getattr(node.func, "id", "")
        ) in ("scrape_draft", "scrape_original"):
            return tuple(ast.literal_eval(node.args[1]))
    raise AssertionError(f"{module}.{name} 未找到共享调用")


def test_shared_impl() -> None:
    payload = '{"a": 1, "b": [1, 2]}'
    check("共享实现：正常解析（marker 右侧取首个 JSON 对象）",
          scrape_draft(f"已批准X草稿：\n{payload}", ("已批准X草稿：",)) == {"a": 1, "b": [1, 2]}, "")
    check("共享实现：无 marker / 非对象 / 截断 JSON / 空串 → 空 dict",
          scrape_draft("无 marker", ("已批准X草稿：",)) == {}
          and scrape_draft("已批准X草稿：\n[1,2]", ("已批准X草稿：",)) == {}
          and scrape_draft('已批准X草稿：\n{"a":', ("已批准X草稿：",)) == {}
          and scrape_draft("", ("已批准X草稿：",)) == {}, "")
    check("共享实现：多 marker 按序命中第一个",
          scrape_draft('已批准一：\n{"x": 1}\n已批准二：\n{"y": 2}', ("已批准一：", "已批准二：")) == {"x": 1}, "")
    check("共享实现：原文档位（marker → 最近 stop 之前；第二条 marker 也认）",
          scrape_original("原文：\n内容X\n\n已批准", ("原文（最高事实来源）：", "原文："),
                          ("\n\n用户画像：", "\n\n已批准")) == "内容X", "")
    check("共享实现：原文档位无 marker → 空串", scrape_original("没有 marker", ("原文：",), ("\n\n已批准",)) == "", "")


def test_call_sites() -> None:
    payload = '{"a": 1, "b": [1, 2]}'
    for module, name, marker_count in DRAFT_SITES:
        func = getattr(importlib.import_module(module), name)
        short = f"{module.split('.')[-2]}.{name}"
        markers = _markers_of(module, name)
        check(f"{short}：marker 数量 {marker_count}", len(markers) == marker_count, str(markers))
        check(f"{short}：自身 marker 能命中（marker={markers[0] if markers else ''}）",
              func(f"{markers[0]}\n{payload}\n\n用户画像：\n{{}}") == {"a": 1, "b": [1, 2]}, str(markers))
        check(f"{short}：无 marker / 空串 → 空草稿",
              func("没有 marker") == {} and func("") == {}, "")

    original_ctx = "原文（最高事实来源）：\n第一行\n第二行\n\n用户画像：\n不该出现"
    for module, name in ORIG_SITES:
        func = getattr(importlib.import_module(module), name)
        short = f"{module.split('.')[-2]}.{name}"
        check(f"{short}：截到 stop 之前", func(original_ctx) == "第一行\n第二行", repr(func(original_ctx)))
        check(f"{short}：无 marker → 空串", func("没有 marker") == "", "")


def main() -> int:
    test_shared_impl()
    test_call_sites()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for item in FAIL:
        print("FAIL", item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
