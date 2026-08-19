# -*- coding: utf-8 -*-
"""Python 3.10 语法兼容检查：全库 .py 用 ast.parse 编译。

目的：拦住 Python <=3.11 的语法回归（如 f-string 表达式含反斜杠、
PEP 701 新语法等）——这类错误在 3.12+ 不报、3.10 直接 SyntaxError，
且历史上造成过「任务无限卡死、无日志」的线上事故。

注意：跳过 demo/samples（数据）与 .tpl.py（生成器模板），模拟解释器
tokenize 行为（utf-8-sig 剥离 BOM）。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    "__pycache__", ".git", ".reasonix", "node_modules", "output",
    "demo", "samples", "test", "tests", "dist", "build",
}


def _python_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name.endswith(".tpl.py"):
            continue
        out.append(p)
    return out


def test_全库在_python310_下语法兼容():
    errors = []
    files = _python_files()
    assert files, "应扫描到业务 .py 文件"
    for p in files:
        src = p.read_text(encoding="utf-8-sig")
        try:
            ast.parse(src, filename=str(p))
        except SyntaxError as exc:  # pragma: no cover
            errors.append(f"{p.relative_to(ROOT)} L{exc.lineno}: {exc.msg}")
    assert not errors, f"以下文件在 Python 3.10 下语法错误（3.12+ 可能不报）：\n" + "\n".join(errors)
