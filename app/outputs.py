"""任务产物输出保存：run() 产物落盘到 data/{user_id}/output/{request_id}/。

约定：
- 每次调用保存到独立目录，目录内文件名：``result.md``（标准 Markdown 链接
  文本，含溯源标注；actions/risks/minutes_styles 按线命名为 ``{task}.md``）
  与 ``{task}.html``（页面版，按本次请求任务线命名，如 checklist.html）。
- 运行期（runner）已直接把产物写入该目录，此处为幂等兜底：同文件跳过复制，
  仅补齐缺失文件并返回路径（CLI 无 request 时也走这里）。
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


def resolve_output_file(user_id: str, request_id: str, file_name: str) -> Path | None:
    """校验并定位产物文件 data/{user_id}/output/{request_id}/{file_name}。

    参数含路径分隔符/`.`/`..` 视为非法；文件不存在返回 None（路由层转 404）。
    """
    for part in (user_id, request_id, file_name):
        if not part or "/" in part or "\\" in part or part in {".", ".."}:
            return None
    out = output_dir(user_id, request_id)
    path = (out / file_name).resolve()
    data_root = (PROJECT_ROOT / "data").resolve()
    if path.is_file() and data_root in path.parents:
        return path
    return None


def _copy_as(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return dest
    shutil.copyfile(src, dest)
    return dest


def save_task_outputs(
    user_id: str,
    request_id: str,
    saved: dict[str, dict[str, Path]],
) -> dict[str, Path | None]:
    """把 run(collect_reports=True) 返回的 saved 收拢到按请求隔离的目录。

    saved 结构：{线名: {"text": Path, "html": Path, ...}}（含 graph 的
    {"svg", "html", "text"}、mindmap 的 {"html", "png"}）。
    返回 {"dir", "md", "html"}：md/html 为固定名文件，缺失为 None。
    """
    out = output_dir(user_id, request_id)
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path | None] = {"dir": out, "md": None, "html": None}
    for _line, paths in saved.items():
        if not isinstance(paths, dict):
            continue
        if result["md"] is None and paths.get("text"):
            # 保留源文件名（result.md 或按线命名的 {line}.md），不强行改名
            result["md"] = _copy_as(Path(paths["text"]), out / Path(paths["text"]).name)
        if result["html"] is None and paths.get("html"):
            result["html"] = _copy_as(Path(paths["html"]), out / f"{_line}.html")
        if result["md"] and result["html"]:
            break
    return result


__all__ = ["output_dir", "resolve_output_file", "save_task_outputs"]
