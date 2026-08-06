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
from domain.meeting.models import UserIdentity, is_objective_perspective
from domain.meeting.orchestrator import MeetingAgentSystem


logger = logging.getLogger(__name__)


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
        description="生成用户视角会议纪要和待办事项",
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
        "--summary_template",
        dest="template",
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


def _format_action(index: int, item: dict) -> str:
    _prio = {"high": "高优先", "medium": "中优先", "low": "低优先"}
    meta = []
    prio = item.get("priority", "")
    if prio and prio in _prio:
        meta.append(_prio[prio])
    if item.get("owner"):
        meta.append(f"负责人：{item['owner']}")
    if item.get("deadline"):
        meta.append(f"截止：{item['deadline']}")
    suffix = f"（{'；'.join(meta)}）" if meta else ""
    return f"{index}. {item['task']}{suffix}"


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
    template: Path | None,
    item_template: Path | None = None,
) -> None:
    """默认启动方式：流式并行输出。

    待办确定性拼装（或按 item_template 模板渲染），纪要生成期间即完整显示；
    纪要正文由 LLM 流式生成、逐段实时打印（两条输出流并行，互不等待）。
    """
    setup_logging()
    load_env(_resolve_path(env_file))

    transcript = _load_transcript(summary)
    user = _load_user(profile)
    template_text = ""
    if template is not None:
        template_text = _resolve_path(template).read_text(encoding="utf-8").strip()
        if not template_text:
            raise ValueError(f"模板文件为空：{template}")
    item_template_text = ""
    if item_template is not None:
        item_template_text = (
            _resolve_path(item_template).read_text(encoding="utf-8").strip()
        )
        if not item_template_text:
            raise ValueError(f"待办模板文件为空：{item_template}")

    objective = is_objective_perspective(user)
    minutes_title = "客观会议纪要" if objective else f"{user.name or '用户'}视角会议纪要"
    actions_title = "客观待办事项（全员）" if objective else "待办事项"

    system = MeetingAgentSystem()
    minutes_started = False
    actions_streamed = False
    async for event in system.run_streaming(
        transcript,
        user,
        template=template_text,
        item_template=item_template_text,
    ):
        etype = event["type"]
        if etype == "actions":
            logger.info("")
            _section(actions_title)
            if item_template_text:
                # 有待办模板：文本由 actions_chunk 流式提供，这里只打标题
                continue
            items = event["items"]
            if not items:
                logger.info("暂无明确待办")
            else:
                for index, item in enumerate(items, start=1):
                    logger.info(_format_action(index, item))
        elif etype == "actions_chunk":
            # 待办模板渲染流：逐块实时打印（与纪要流对称）
            actions_streamed = True
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif etype == "minutes_chunk":
            if not minutes_started:
                logger.info("")
                _section(minutes_title)
                minutes_started = True
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif etype == "done":
            if event.get("quality_warning"):
                logger.warning("⚠ %s", event["quality_warning"])
    if minutes_started:
        sys.stdout.write("\n")
    elif actions_streamed:
        # 待办流式已输出但无纪要：补一个换行收尾
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
                args.template,
                args.item_template,
            )
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
