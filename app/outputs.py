"""任务产物输出保存：将 run() 产物落盘到 data/{user_id}/output/{request_id}/。

约定：
- 每次调用保存到独立目录，目录内文件名固定：``result.md``（标准 Markdown 链接
  文本，含溯源标注）与 ``result.html``（页面版，含记忆卡片对照）。
- 源文件仍在 ``output/`` 保留（CLI/Gradio 兼容），此处为副本。
- 未传 ``X-User-Id`` 时目录为 ``data/output/{request_id}/``。
"""
from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def output_dir(user_id: str, request_id: str) -> Path:
    """本次调用的产物目录。request_id 缺省可用 uuid4 或模拟值。"""
    root = PROJECT_ROOT / "data"
    if (user_id or "").strip():
        root = root / (user_id or "").strip()
    return (root / "output" / (request_id or "default")).resolve()


def _copy_as(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


def save_task_outputs(
    user_id: str,
    request_id: str,
    saved: dict[str, dict[str, Path]],
) -> dict[str, Path | None]:
    """把 run(collect_reports=True) 返回的 saved 复制到按请求隔离的目录。

    saved 结构：{线名: {"text": Path, "html": Path, ...}}（含 graph 的
    {"svg", "html", "text"}、mindmap 的 {"html", "png"}）。
    返回 {"dir", "md", "html"}：md/html 为复制后的固定名文件，缺失为 None。
    """
    out = output_dir(user_id, request_id)
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path | None] = {"dir": out, "md": None, "html": None}
    for _line, paths in saved.items():
        if not isinstance(paths, dict):
            continue
        if result["md"] is None and paths.get("text"):
            result["md"] = _copy_as(Path(paths["text"]), out / "result.md")
        if result["html"] is None and paths.get("html"):
            result["html"] = _copy_as(Path(paths["html"]), out / "result.html")
        if result["md"] and result["html"]:
            break
    return result


__all__ = ["output_dir", "save_task_outputs"]
