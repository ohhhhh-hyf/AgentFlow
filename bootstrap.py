from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.knowledge_graph import (  # noqa: E402
    graphviz_available,
    render_knowledge_graph_bundle,
)
from tools.logging_config import setup_logging  # noqa: E402
from tools.mindmap import (  # noqa: E402
    markmap_available,
    mindmap_png_available,
    render_mindmap_html,
    render_mindmap_png,
)
from tools.template_router import maybe_compile_natural_template  # noqa: E402


logger = logging.getLogger(__name__)


# 各域预留的英文短名（线名/中文名永远可用；短名按域可选补充）
_SHORT_ALIASES: dict[str, dict[str, str]] = {
    "meeting": {
        "minutes": "minutes_generation",
        "actions": "action_items",
    },
}


@dataclass
class _DomainContext:
    """运行时解析的领域上下文（bootstrap 与具体 domain 解耦）。"""

    name: str
    module: object
    config: object
    models: object
    orchestrator: object
    system_cls: type
    samples_dir: Path
    line_cn_names: dict[str, str]
    task_lines: dict[str, dict]
    task_aliases: dict[str, str]
    env_prefix: str

    @property
    def default_file_dir(self) -> Path:
        # 保持实际样本目录名（samples/summary/），仅 CLI 参数名改为 --file
        return self.samples_dir / "summary"

    @property
    def default_profile_dir(self) -> Path:
        return self.samples_dir / "profile"


def _load_domain(name: str) -> _DomainContext:
    """按领域名加载 domain.<name> 各模块并解析别名 / 系统类名。"""
    module = importlib.import_module(f"domain.{name}")
    config = importlib.import_module(f"domain.{name}.domain_config")
    models = importlib.import_module(f"domain.{name}.models")
    orchestrator = importlib.import_module(f"domain.{name}.orchestrator")
    pascal = name[0].upper() + name[1:]
    system_cls = getattr(orchestrator, f"{pascal}AgentSystem")
    line_cn_names = getattr(config, "LINE_CN_NAMES", {})
    task_lines = getattr(orchestrator, "TASK_LINES", {})
    # 友好任务名 → 任务线名：线名本身 + 中文名自动构建（加线零改动），
    # 英文短名按域补充（未列出的名称原样透传，供 _normalize_tasks 报错）。
    aliases = dict(_SHORT_ALIASES.get(name, {}))
    aliases.update({line: line for line in task_lines})
    aliases.update({cn: line for line, cn in line_cn_names.items()})
    return _DomainContext(
        name=name,
        module=module,
        config=config,
        models=models,
        orchestrator=orchestrator,
        system_cls=system_cls,
        samples_dir=getattr(module, "SAMPLES_DIR"),
        line_cn_names=line_cn_names,
        task_lines=task_lines,
        task_aliases=aliases,
        env_prefix=name.upper(),
    )


def _normalize_tasks(
    ctx: _DomainContext, tasks: list[str], known_lines: set[str]
) -> list[str]:
    """把 --task 传入的任务名统一解析成线名；未知名称直接报错。"""
    result: list[str] = []
    for raw in tasks:
        name = raw.strip()
        line = ctx.task_aliases.get(name, name)
        if line not in known_lines:
            raise ValueError(
                f"未知任务线：{name}（可用：{sorted(known_lines)}）"
            )
        result.append(line)
    return result


def _env_path(ctx: _DomainContext, key: str, default: Path | None) -> Path | None:
    """从环境变量（.env）读取路径；未配置时返回默认值。"""
    value = os.getenv(f"{ctx.env_prefix}_{key}", "").strip()
    return Path(value) if value else default


def _parser(ctx: _DomainContext) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"运行 {ctx.name} 域任务线（可用 --task 指定生成哪条线）",
    )
    parser.add_argument(
        "--domain",
        default=ctx.name,
        help=f"领域名（默认 {ctx.name}）",
    )
    parser.add_argument(
        "--file",
        dest="file",
        type=Path,
        default=_env_path(ctx, "FILE", ctx.default_file_dir),
        help="输入文本文件或目录。传目录时，目录中需要包含一个 .txt 文件",
    )
    parser.add_argument(
        "--profile",
        dest="profile",
        type=Path,
        default=_env_path(ctx, "PROFILE", ctx.default_profile_dir),
        help="用户画像 JSON 文件或目录。传目录时，目录中需要包含一个 .json 文件",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="环境变量文件路径",
    )
    # 每个任务线一个模板参数：--{线名}_template（如 --minutes_generation_template）
    for line in sorted(ctx.task_lines):
        cn = ctx.line_cn_names.get(line, line)
        parser.add_argument(
            f"--{line}_template",
            dest=f"{line}_template",
            type=Path,
            default=_env_path(ctx, f"{line.upper()}_TEMPLATE", None),
            help=f"{cn}线渲染模板（.md 文件）。模板中用 [描述] 作为占位符，"
            "系统将自动填充内容。不指定则使用默认格式",
        )
    parser.add_argument(
        "--task",
        dest="tasks",
        action="append",
        required=True,
        metavar="任务",
        help="要生成的任务，可多次指定。"
        f"可用：{' / '.join(sorted(ctx.task_lines))}，也支持友好名 "
            f"{' / '.join(sorted(ctx.task_aliases))}",
    )
    return parser


def _resolve_path(ctx: _DomainContext, path: Path) -> Path:
    if path.is_absolute():
        return path
    root_candidate = (PROJECT_ROOT / path).resolve()
    if root_candidate.exists():
        return root_candidate
    # 回退：相对领域样例目录（SAMPLES_DIR）解析，省去 domain/<name>/samples 前缀
    return (ctx.samples_dir / path).resolve()


def _pick_single_file(folder: Path, pattern: str, label: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"请在 {folder} 中放入一个{label}文件")
    if len(files) > 1:
        names = "\n".join(f"- {file.name}" for file in files)
        raise ValueError(
            f"{folder} 中发现多个{label}文件，请直接指定其中一个文件：\n{names}"
        )
    return files[0]


def _resolve_input_file(
    ctx: _DomainContext, path: Path, suffix: str, label: str
) -> Path:
    path = _resolve_path(ctx, path)
    if not path.exists():
        raise FileNotFoundError(f"{label}路径不存在：{path}")

    if path.is_file():
        if path.suffix.lower() != suffix:
            raise ValueError(f"{label}文件必须是 {suffix}：{path}")
        return path

    if path.is_dir():
        return _pick_single_file(path, f"*{suffix}", label)

    raise ValueError(f"{label}路径既不是文件也不是目录：{path}")


def _load_transcript(ctx: _DomainContext, file_path: Path) -> str:
    text_file = _resolve_input_file(ctx, file_path, ".txt", "输入文本")
    transcript = text_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{text_file} 是空文件，请写入内容")
    return transcript


def _load_user(ctx: _DomainContext, profile_path: Path):
    profile_file = _resolve_input_file(ctx, profile_path, ".json", "用户画像")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    return ctx.models.UserIdentity(**profile)


def _task_output_dir(ctx: _DomainContext, line_name: str) -> Path:
    out_dir = PROJECT_ROOT / "output" / ctx.name / line_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _report_to_dict(report: object) -> dict:
    if hasattr(report, "model_dump"):
        return report.model_dump()
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return report
    return {"value": str(report)}


def _report_text(data: dict) -> str:
    for key in (
        "personalized_minutes",
        "personalized_text",
        "outline",
        "rendered",
        "text",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _save_report_artifacts(
    ctx: _DomainContext,
    line_name: str,
    report: object,
    timestamp: str,
) -> dict[str, Path]:
    out_dir = _task_output_dir(ctx, line_name)
    data = _report_to_dict(report)
    paths: dict[str, Path] = {}
    json_path = out_dir / f"report_{timestamp}.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["json"] = json_path
    text = _report_text(data)
    if text:
        md_path = out_dir / f"result_{timestamp}.md"
        md_path.write_text(text, encoding="utf-8")
        paths["text"] = md_path
    return paths


def _save_all_reports(
    ctx: _DomainContext,
    reports: dict,
    timestamp: str,
) -> dict[str, dict[str, Path]]:
    saved: dict[str, dict[str, Path]] = {}
    for line_name, report in reports.items():
        if line_name not in ctx.task_lines:
            continue
        if line_name == "knowledge_graph":
            continue
        saved[line_name] = _save_report_artifacts(ctx, line_name, report, timestamp)
    return saved


def _export_mindmap_html(reports: dict, out_dir: Path) -> Path | None:
    """从 done 事件的 reports 中提取 mindmap 大纲并导出 HTML。

    - 无 mindmap 线 / 大纲为空 → 返回 None
    - npx 不可用 / markmap 失败 → 记 warning，返回 None（不影响主流程）
    """
    mindmap_report = reports.get("mindmap")
    outline = getattr(mindmap_report, "outline", None) if mindmap_report else None
    if not outline or not outline.strip():
        return None
    if not markmap_available():
        logger.warning("未检测到 npx/node，跳过思维导图 HTML 生成")
        return None
    filename = f"mindmap_{datetime.now():%Y%m%d_%H%M%S}.html"
    return render_mindmap_html(outline, out_dir, filename)


async def _export_mindmap_png(
    reports: dict, out_dir: Path, html_path: Path | None = None
) -> Path | None:
    """从 done 事件的 reports 中提取 mindmap 大纲并导出 PNG。

    - 无 mindmap 线 / 大纲为空 → 返回 None
    - playwright 未安装 / chromium 缺失 / 截图失败 → 记 warning，返回 None
    - 传入 html_path 时复用该 HTML 截图
    """
    mindmap_report = reports.get("mindmap")
    outline = getattr(mindmap_report, "outline", None) if mindmap_report else None
    if not outline or not outline.strip():
        return None
    if not mindmap_png_available():
        logger.warning(
            "未安装 playwright，跳过思维导图 PNG 生成"
            "（安装：pip install playwright && playwright install chromium）"
        )
        return None
    filename = f"mindmap_{datetime.now():%Y%m%d_%H%M%S}.png"
    return await render_mindmap_png(outline, out_dir, filename, html_path=html_path)


def _export_knowledge_graph(reports: dict, out_dir: Path) -> dict[str, Path]:
    """从 done 事件的 reports 中提取 knowledge_graph 图数据并导出图谱文件。

    - 无 knowledge_graph 线 / nodes 为空 → 返回空 dict
    - graphviz（dot）不可用 / 渲染失败 → PNG/SVG 跳过，HTML 仍尽量生成
    """
    kg = reports.get("knowledge_graph")
    nodes = getattr(kg, "nodes", None) if kg else None
    if not nodes:
        return {}
    if not graphviz_available():
        logger.warning("未检测到 graphviz（dot），跳过知识图谱 PNG/SVG 生成")
    edges = getattr(kg, "edges", None) or []
    outline = getattr(kg, "outline", "") or ""
    title = str(getattr(kg, "title", "") or "").strip()
    for line in outline.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    stem = f"knowledge_graph_{datetime.now():%Y%m%d_%H%M%S}"
    return render_knowledge_graph_bundle(nodes, edges, out_dir, stem, title=title)


async def run(
    ctx: _DomainContext,
    file: Path,
    profile: Path,
    env_file: Path,
    templates: dict[str, Path] | None = None,
    tasks: list[str] | None = None,
) -> None:
    """流式并行输出（--task 必填，只跑选中的任务线）。

    ``tasks`` 指定要生成的任务（对应 run_streaming 的 lines 参数，已由
    ``_normalize_tasks`` 解析成线名）：未选中的线不运行、不产出事件。

    ``templates`` 按线名 → 模板文件路径（来自 ``--{线名}_template`` 参数）；
    未指定的线用默认渲染格式。

    各线文本由 LLM 流式生成、逐块实时打印（多条输出流并行，互不等待）；
    消费完全按任务线维度通用（chunk 事件自带 line/title），新增任务线无需改此处。
    """
    setup_logging()
    load_env(_resolve_path(ctx, env_file))

    transcript = _load_transcript(ctx, file)
    user = _load_user(ctx, profile)
    # 任务名 → 线名（未知名称在此报错，不进入运行）
    line_names = _normalize_tasks(ctx, tasks, set(ctx.task_lines))
    # 按线读取模板（--{线名}_template → 模板文本；自然语言描述先编译）
    template_texts: dict[str, str] = {}
    for line, path in (templates or {}).items():
        if path is None:
            continue
        text = _resolve_path(ctx, Path(path)).read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{line} 模板文件为空：{path}")
        # 自然语言描述模板 → 先编译为占位符模板（失败自动回退原文，不阻塞）
        template_texts[line] = await maybe_compile_natural_template(text)

    system = ctx.system_cls()
    any_output = False
    # 图类线静默：大纲不打印，只需图片产物（mindmap / knowledge_graph）
    silent_graph_lines = {"mindmap", "knowledge_graph"}
    graph_silent = any(line in silent_graph_lines for line in line_names)
    async for event in system.run_streaming(
        transcript,
        user,
        templates=template_texts,
        lines=line_names,
    ):
        etype = event["type"]
        if etype == "chunk":
            # 图类线静默：大纲不打印，只需图片产物（其余线照常流式输出）
            if event.get("line") in silent_graph_lines:
                continue
            # 通用流式块：不打印分节标题，正文逐块追加
            any_output = True
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif etype == "done":
            if event.get("quality_warning"):
                logger.warning("⚠ %s", event["quality_warning"])
            reports = event.get("reports") or {}
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_reports = _save_all_reports(ctx, reports, timestamp)
            for line_name, paths in saved_reports.items():
                if paths.get("json"):
                    sys.stdout.write(
                        f"[{ctx.line_cn_names.get(line_name, line_name)}] "
                        f"已保存 JSON：{paths['json']}\n"
                    )
                if paths.get("text"):
                    sys.stdout.write(
                        f"[{ctx.line_cn_names.get(line_name, line_name)}] "
                        f"已保存文本：{paths['text']}\n"
                    )
            # 思维导图固定导出 HTML + PNG；失败仅提示，不影响主流程
            if "mindmap" in reports:
                mindmap_dir = _task_output_dir(ctx, "mindmap")
                html_path = _export_mindmap_html(reports, mindmap_dir)
                if html_path:
                    sys.stdout.write(f"\n[思维导图] 已生成 HTML：{html_path}\n")
                png_path = await _export_mindmap_png(
                    reports, mindmap_dir, html_path=html_path
                )
                if png_path:
                    sys.stdout.write(f"[思维导图] 已生成 PNG：{png_path}\n")
            # 知识图谱导出（PNG/SVG/HTML；失败仅提示，不影响主流程）
            if "knowledge_graph" in reports:
                kg_dir = _task_output_dir(ctx, "knowledge_graph")
                kg_paths = _export_knowledge_graph(reports, kg_dir)
                if kg_paths.get("png"):
                    sys.stdout.write(f"[知识图谱] 已生成 PNG：{kg_paths['png']}\n")
                if kg_paths.get("svg"):
                    sys.stdout.write(f"[知识图谱] 已生成 SVG：{kg_paths['svg']}\n")
                if kg_paths.get("html"):
                    sys.stdout.write(f"[知识图谱] 已生成 HTML：{kg_paths['html']}\n")
    if any_output:
        sys.stdout.write("\n")
    elif not graph_silent:
        # 图类线静默输出，不触发「暂无内容」误报（图片产物另行提示）
        logger.info("（暂无内容）")


def main() -> None:
    # 先解析 --domain（在 --task 校验前拿到领域上下文）
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--domain", default="meeting")
    pre_args, _ = pre.parse_known_args()
    ctx = _load_domain(pre_args.domain)
    # 加载默认 .env，使 parser 默认值可被 .env 中的 {领域}_* 配置覆盖
    load_env(PROJECT_ROOT / ".env")
    args = _parser(ctx).parse_args()
    # 收集各线模板（--{线名}_template → 线名: 路径）
    templates: dict[str, Path] = {}
    for line in ctx.task_lines:
        path = getattr(args, f"{line}_template")
        if path is not None:
            templates[line] = path
    try:
        asyncio.run(
            run(
                ctx,
                args.file,
                args.profile,
                args.env,
                templates,
                args.tasks,
            )
        )
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        RuntimeError,
        ImportError,
        AttributeError,
        NameError,
    ) as exc:
        if isinstance(exc, (ImportError, AttributeError, NameError)):
            raise SystemExit(
                f"错误：领域装配不完整：{exc}\n"
                f"请先运行：python tools/scripts/sync_domain.py --domain {pre_args.domain}"
            ) from exc
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
