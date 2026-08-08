from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from llm_client.config import load_env
from domain.meeting import SAMPLES_DIR
from tools.logging_config import setup_logging
from domain.meeting.models import UserIdentity
from domain.meeting.orchestrator import MeetingAgentSystem, TASK_LINES


logger = logging.getLogger(__name__)


# 友好任务名 → 任务线名（未列出的名称原样透传，如 minutes_generation / action_items）
TASK_ALIASES: dict[str, str] = {
    "minutes": "minutes_generation",
    "纪要": "minutes_generation",
    "actions": "action_items",
    "待办": "action_items",
}


def _normalize_tasks(
    tasks: list[str], known_lines: set[str]
) -> list[str]:
    """把 --task 传入的任务名统一解析成线名；未知名称直接报错。"""
    result: list[str] = []
    for name in tasks:
        name = name.strip()
        line = TASK_ALIASES.get(name, name)
        if line not in known_lines:
            raise ValueError(
                f"未知任务线：{name}（可用：{sorted(known_lines)}）"
            )
        result.append(line)
    return result


DEFAULT_SUMMARY_PATH = SAMPLES_DIR / "summary"
DEFAULT_PROFILE_PATH = SAMPLES_DIR / "profile"

# .env 中可选的路径配置项（命令行显式参数优先于这些配置）
ENV_SUMMARY = "MEETING_SUMMARY"
ENV_PROFILE = "MEETING_PROFILE"
ENV_SUMMARY_TEMPLATE = "MEETING_SUMMARY_TEMPLATE"
ENV_ITEM_TEMPLATE = "MEETING_ITEM_TEMPLATE"


def _env_path(key: str, default: Path | None) -> Path | None:
    """从环境变量（.env）读取路径；未配置时返回默认值。"""
    value = os.getenv(key, "").strip()
    return Path(value) if value else default


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成会议纪要 / 待办事项（可用 --task 指定生成哪条线）",
    )
    parser.add_argument(
        "--summary",
        "--summary-dir",
        dest="summary",
        type=Path,
        default=_env_path(ENV_SUMMARY, DEFAULT_SUMMARY_PATH),
        help="会议文本文件或目录。传目录时，目录中需要包含一个 .txt 文件",
    )
    parser.add_argument(
        "--profile",
        "--profile-dir",
        dest="profile",
        type=Path,
        default=_env_path(ENV_PROFILE, DEFAULT_PROFILE_PATH),
        help="用户画像 JSON 文件或目录。传目录时，目录中需要包含一个 .json 文件",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="环境变量文件路径",
    )
    parser.add_argument(
        "--minutes_template",
        "--summary_template",
        dest="minutes_template",
        type=Path,
        default=_env_path(ENV_SUMMARY_TEMPLATE, None),
        help="最终纪要输出格式模板（.md 文件）。模板中用 [描述] 作为占位符，"
        "系统将自动填充会议内容。不指定则使用默认的自由段落格式",
    )
    parser.add_argument(
        "--item_template",
        dest="item_template",
        type=Path,
        default=_env_path(ENV_ITEM_TEMPLATE, None),
        help="最终待办输出格式模板（.md 文件）。模板中用 [描述] 作为占位符，"
        "系统将自动填充待办内容。不指定则使用默认的列表格式",
    )
    parser.add_argument(
        "--task",
        dest="tasks",
        action="append",
        required=True,
        metavar="任务",
        help="要生成的任务，可多次指定（如 --task minutes --task actions）。"
        f"可用：{' / '.join(sorted(TASK_LINES))}，也支持友好名 "
        f"{' / '.join(sorted(TASK_ALIASES))}",
    )
    return parser


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    root_candidate = (PROJECT_ROOT / path).resolve()
    if root_candidate.exists():
        return root_candidate
    # 回退：相对领域样例目录（SAMPLES_DIR）解析，省去 src/domain/meeting/samples 前缀
    return (SAMPLES_DIR / path).resolve()


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


def _resolve_input_file(path: Path, suffix: str, label: str) -> Path:
    path = _resolve_path(path)
    if not path.exists():
        raise FileNotFoundError(f"{label}路径不存在：{path}")

    if path.is_file():
        if path.suffix.lower() != suffix:
            raise ValueError(f"{label}文件必须是 {suffix}：{path}")
        return path

    if path.is_dir():
        return _pick_single_file(path, f"*{suffix}", label)

    raise ValueError(f"{label}路径既不是文件也不是目录：{path}")


def _section(title: str) -> None:
    logger.info("── %s ──", title)


def _load_transcript(summary_path: Path) -> str:
    meeting_file = _resolve_input_file(summary_path, ".txt", "会议文本")
    transcript = meeting_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{meeting_file} 是空文件，请写入会议内容")
    return transcript


def _load_user(profile_path: Path) -> UserIdentity:
    profile_file = _resolve_input_file(profile_path, ".json", "用户画像")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    return UserIdentity(**profile)


async def run(
    summary: Path,
    profile: Path,
    env_file: Path,
    minutes_template: Path | None,
    item_template: Path | None = None,
    tasks: list[str] | None = None,
) -> None:
    """流式并行输出（--task 必填，只跑选中的任务线）。

    ``tasks`` 指定要生成的任务（对应 run_streaming 的 lines 参数，已由
    ``_normalize_tasks`` 解析成线名）：未选中的线不运行、不产出事件。

    各线文本由 LLM 流式生成、逐块实时打印（多条输出流并行，互不等待）；
    消费完全按任务线维度通用（chunk 事件自带 line/title），新增任务线无需改此处。
    """
    setup_logging()
    load_env(_resolve_path(env_file))

    transcript = _load_transcript(summary)
    user = _load_user(profile)
    # 任务名 → 线名（未知名称在此报错，不进入运行）
    line_names = _normalize_tasks(tasks, set(TASK_LINES))
    # 模板按线统一收纳：纪要模板 → templates["minutes_generation"]，待办模板 → templates["action_items"]
    templates: dict[str, str] = {}
    if minutes_template is not None:
        template_text = (
            _resolve_path(minutes_template).read_text(encoding="utf-8").strip()
        )
        if not template_text:
            raise ValueError(f"纪要模板文件为空：{minutes_template}")
        templates["minutes_generation"] = template_text
    if item_template is not None:
        item_template_text = (
            _resolve_path(item_template).read_text(encoding="utf-8").strip()
        )
        if not item_template_text:
            raise ValueError(f"待办模板文件为空：{item_template}")
        templates["action_items"] = item_template_text

    system = MeetingAgentSystem()
    printed: dict[str, bool] = {}  # line → 是否已打标题
    any_output = False
    async for event in system.run_streaming(
        transcript,
        user,
        templates=templates,
        lines=line_names,
    ):
        etype = event["type"]
        if etype == "chunk":
            # 通用流式块：按 line 首次输出打标题，正文逐块追加
            line = event["line"]
            if not printed.get(line):
                logger.info("")
                _section(event["title"])
                printed[line] = True
            any_output = True
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif etype == "done":
            if event.get("quality_warning"):
                logger.warning("⚠ %s", event["quality_warning"])
    if any_output:
        sys.stdout.write("\n")
    else:
        logger.info("（暂无内容）")


def main() -> None:
    # 先加载默认 .env，使 parser 默认值可被 .env 中的 MEETING_* 配置覆盖
    load_env(PROJECT_ROOT / ".env")
    args = _parser().parse_args()
    try:
        asyncio.run(
            run(
                args.summary,
                args.profile,
                args.env,
                args.minutes_template,
                args.item_template,
                args.tasks,
            )
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
